"""Incremental end-to-end turbine analysis orchestrator.

Examples (Windows PowerShell):
  python run_analysis.py --wind-speed 25 --wind-direction 90
  python run_analysis.py --config data/default_turbine.json --mesh-size 0.8 --wind-speed 35 --wind-direction 180

Gravity and reference-wind solves are cached only when provenance matches. The
reference wind solution is always generated at 50 m/s; operating speed is applied
in post-processing using the project's v^2 linear-response convention.
"""
from __future__ import annotations
import argparse, json, os, pickle, subprocess, sys
from pathlib import Path
import numpy as np
from analysis_metadata import geometry_fingerprint, mesh_fingerprint, file_fingerprint, metadata_matches
from contracts import SolveResult, Mesh, Settings
from failure_analysis import assess_npz

ROOT = Path(__file__).resolve().parent
V_REF = 50.0


def _load_pickle(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def _load_mesh_and_result(mesh_path, result_path, case):
    if not mesh_path.is_file() or not result_path.is_file():
        return None, None
    mesh_obj = _load_pickle(mesh_path)
    mesh = mesh_obj[0] if isinstance(mesh_obj, tuple) else mesh_obj
    result = _load_pickle(result_path)
    if not isinstance(mesh, Mesh) or not isinstance(result, SolveResult):
        return None, None
    if result.case != case:
        return None, None
    return mesh, result


def _run(command, env, label):
    print(f"\n=== {label} ===", flush=True)
    completed = subprocess.run(command, cwd=ROOT, env=env, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}; downstream stages were not run")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run/reuse gravity and reference-wind FEA, then combine results.")
    ap.add_argument("--config", default="data/default_turbine.json")
    ap.add_argument("--mesh-size", type=float, default=1.0, help="global maximum surface mesh size [m]")
    ap.add_argument("--mesh-base-size", type=float, default=0.5, help="base-region mesh size [m]")
    ap.add_argument("--mesh-refine-distance", type=float, default=6.0, help="near-base refinement distance [m]")
    ap.add_argument("--mesh-order", type=int, choices=(2,), default=2, help="S6 quadratic shell elements are required by the CalculiX writer")
    ap.add_argument("--wind-speed", type=float, required=True, help="operating wind speed [m/s]")
    ap.add_argument("--wind-direction", type=float, default=0.0, help="bearing wind comes FROM: 0=N, 90=E, 180=S, 270=W")
    ap.add_argument("--output", default="out")
    ap.add_argument("--ccx", default=os.environ.get("CCX_PATH"))
    ap.add_argument("--yield-strength", type=float, default=345e6, help="uniform screening yield strength [Pa]; default is project placeholder")
    ap.add_argument("--safety-factor", type=float, default=1.5)
    args = ap.parse_args(argv)

    if not np.isfinite(args.wind_speed) or args.wind_speed < 0:
        ap.error("--wind-speed must be finite and >= 0")
    if not np.isfinite(args.wind_direction):
        ap.error("--wind-direction must be finite")
    for name in ("mesh_size", "mesh_base_size", "mesh_refine_distance"):
        value = getattr(args, name)
        if not np.isfinite(value) or value <= 0:
            ap.error(f"--{name.replace('_', '-')} must be finite and > 0")
    config = (ROOT / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    if not config.is_file():
        ap.error(f"geometry configuration not found: {config}")
    # Validate that configuration is parseable before launching Gmsh.
    with config.open(encoding="utf-8") as f:
        json.load(f)
    out = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    config_hash = geometry_fingerprint(config)
    config_data = json.loads(config.read_text(encoding="utf-8"))
    settings = Settings()
    settings.mesh_size = args.mesh_size
    settings.z_hub = float(config_data["tower"]["sections"][-1]["z1"]) + float(config_data["nacelle"]["height"]) / 2.0
    settings.validate()
    expected_gravity_settings = {"mesh_size_m": args.mesh_size, "mesh_base_size_m": args.mesh_base_size,
                                 "mesh_refine_distance_m": args.mesh_refine_distance, "mesh_order": args.mesh_order,
                                 "load_case": settings.load_case, "extra_mass_kg": 243885.0}
    expected_material = {"E_Pa": settings.E, "nu": settings.nu, "rho_kg_m3": settings.rho,
                         "yield_strength_Pa": settings.yield_strength}
    expected_solver = args.ccx or os.environ.get("CCX_PATH") or "PATH lookup"
    expected_wind_settings = {"mesh_size_m": args.mesh_size, "mesh_base_size_m": args.mesh_base_size,
                              "mesh_refine_distance_m": args.mesh_refine_distance, "mesh_order": args.mesh_order,
                              "shear_alpha": settings.shear_alpha, "Cd_tower": settings.Cd_tower,
                              "Cd_blade": settings.Cd_blade, "air_pressure_Pa": settings.air_pressure,
                              "air_temp_K": settings.air_temp}
    env = dict(os.environ)
    env.update({"TURBINE_CONFIG": str(config), "TURBINE_OUT": str(out),
                "TURBINE_MESH_SIZE": str(args.mesh_size),
                "TURBINE_MESH_BASE_SIZE": str(args.mesh_base_size),
                "TURBINE_MESH_REFINE_DISTANCE": str(args.mesh_refine_distance),
                "TURBINE_MESH_ORDER": str(args.mesh_order)})
    if args.ccx:
        env["CCX_PATH"] = args.ccx

    g_mesh_path, g_result_path = out / "full_mesh.pkl", out / "res_G.pkl"
    w_mesh_path, w_result_path = out / "wind_mesh.pkl", out / "res_W.pkl"
    npz_path = out / "stress_strain_results.npz"
    g_mesh, g_result = _load_mesh_and_result(g_mesh_path, g_result_path, "G")
    g_valid = False
    if g_mesh is not None:
        g_hash = mesh_fingerprint(g_mesh)
        gm = getattr(g_result, "metadata", {}) or {}
        g_valid = (metadata_matches(gm, case="G", geometry_hash=config_hash, mesh_hash=g_hash)
                   and all(gm.get("settings", {}).get(k) == v for k, v in expected_gravity_settings.items())
                   and all(gm.get("material", {}).get(k) == v for k, v in expected_material.items())
                   and gm.get("solver", {}).get("executable") == expected_solver
                   and (out / "G.inp").is_file()
                   and gm.get("solver", {}).get("input_file_sha256") == file_fingerprint(out / "G.inp"))
    if g_valid:
        print("[cache] Reusing gravity solution: geometry, mesh and mesh settings match.")
    else:
        _run([sys.executable, str(ROOT / "run_gravity.py")], env, "Gravity CalculiX analysis")
        g_mesh, g_result = _load_mesh_and_result(g_mesh_path, g_result_path, "G")
        if g_mesh is None or not metadata_matches(getattr(g_result, "metadata", {}), case="G",
                                                   geometry_hash=config_hash, mesh_hash=mesh_fingerprint(g_mesh)):
            raise RuntimeError("Gravity run returned, but its saved mesh/result provenance is missing or inconsistent")

    mesh_hash = mesh_fingerprint(g_mesh)
    w_mesh, w_result = _load_mesh_and_result(w_mesh_path, w_result_path, "W")
    wind_valid = False
    if w_mesh is not None:
        wm = getattr(w_result, "metadata", {}) or {}
        wind_valid = (mesh_fingerprint(w_mesh) == mesh_hash
                      and metadata_matches(wm, case="W", geometry_hash=config_hash, mesh_hash=mesh_hash,
                                           wind_direction_deg=args.wind_direction, v_ref=V_REF)
                      and all(wm.get("settings", {}).get(k) == v for k, v in expected_wind_settings.items())
                      and all(wm.get("material", {}).get(k) == v for k, v in {
                          "E_Pa": settings.E, "nu": settings.nu, "rho_kg_m3": settings.rho}.items())
                      and wm.get("solver", {}).get("executable") == expected_solver
                      and (out / "W.inp").is_file()
                      and wm.get("solver", {}).get("input_file_sha256") == file_fingerprint(out / "W.inp"))
    if wind_valid:
        print("[cache] Reusing reference-wind solution: geometry, mesh, direction and 50 m/s reference match.")
    else:
        wind_env = dict(env)
        wind_env["TURBINE_REUSE_MESH"] = str(g_mesh_path)
        _run([sys.executable, str(ROOT / "run_winds.py"), "--direction", str(args.wind_direction % 360.0)], wind_env,
             "Reference-wind CalculiX analysis")
        w_mesh, w_result = _load_mesh_and_result(w_mesh_path, w_result_path, "W")
        if w_mesh is None or mesh_fingerprint(w_mesh) != mesh_hash:
            raise RuntimeError("Wind analysis mesh differs from gravity mesh; refusing to combine results")
        if not metadata_matches(getattr(w_result, "metadata", {}), case="W", geometry_hash=config_hash,
                                mesh_hash=mesh_hash, wind_direction_deg=args.wind_direction, v_ref=V_REF):
            raise RuntimeError("Wind run returned, but its saved provenance does not match requested conditions")

    # Explicit exact checks: row order, connectivity and component grouping must match.
    if not (np.array_equal(g_mesh.nodes, w_mesh.nodes) and np.array_equal(g_mesh.elems, w_mesh.elems)
            and np.array_equal(g_mesh.elem_group, w_mesh.elem_group) and g_mesh.group_names == w_mesh.group_names):
        raise RuntimeError("Gravity and wind meshes are not identical in coordinates/connectivity/order")

    _run([sys.executable, str(ROOT / "StressAndStrain.py"),
          "--gravity", str(g_result_path), "--wind", str(w_result_path),
          "--mesh", str(g_mesh_path), "--wind-mesh", str(w_mesh_path),
          "--inp", str(out / "G.inp"), "--speed", str(args.wind_speed),
          "--wind-direction", str(args.wind_direction % 360.0),
          "--save-npz", str(npz_path), "--no-export", "--no-display"], env,
         "Combined stress/strain post-processing")
    g_mesh_obj = _load_pickle(g_mesh_path)
    group_thickness = g_mesh_obj[1] if isinstance(g_mesh_obj, tuple) and len(g_mesh_obj) > 1 else None
    failure = assess_npz(npz_path, yield_strength_pa=args.yield_strength,
                         safety_factor=args.safety_factor, output_path=out / "failure_assessment.json",
                         mesh=g_mesh, group_thickness=group_thickness)
    print("\n=== Analysis complete ===")
    print(f"Operating wind speed: {args.wind_speed:g} m/s | reference: {V_REF:g} m/s | direction FROM: {args.wind_direction % 360:g} deg")
    print(f"Geometry fingerprint: {config_hash}")
    print(f"Mesh fingerprint: {mesh_hash}")
    print(f"Failure screening: {failure['status']} | utilisation={failure['utilization']:.4g} | governing element={failure['governing_calculix_element_id_1_based']}")
    print(f"Combined results: {npz_path}")
    print(f"Failure assessment: {out / 'failure_assessment.json'}")


if __name__ == "__main__":
    main()
