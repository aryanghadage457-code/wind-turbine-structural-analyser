
"""Step: Full-turbine static wind case W.

Run:
    python run_wind.py

Run after confirming that the mesh generation and gravity case work.
"""

import os
import pickle
import argparse
from pathlib import Path

import gmsh
import numpy as np

from contracts import Settings
from solver import bcs
from solver.ccx_writer import write_inp
from solver.ccx_runner import run_ccx
from solver import ccx_reader as R

from solver.loads import orient_turbine, orientation_report, wind_loadset
from analysis_metadata import geometry_fingerprint, mesh_fingerprint, file_fingerprint, make_metadata, atomic_pickle


# -------------------------------------------------
# CONFIGURATION
# -------------------------------------------------

# Replace with the actual path to your CalculiX executable.
CCX_EXE = r"C:\CalculiX\CalculiX-2.23.0-win-x64\CalculiX-2.23.0-win-x64\bin\ccx.exe"
OUT_DIR = Path(os.environ.get("TURBINE_OUT", "out")).resolve()
CONFIG_PATH = Path(os.environ.get("TURBINE_CONFIG", "data/default_turbine.json")).resolve()

BLADE_TABLE = "data/NRELOffshrBsline5MW_Blade.dat"

BLADE_KW = dict(
    blade_ei_file=BLADE_TABLE,
    blade_mass_match=True,
    blade_mass_factor=1.04536
)
# -------------------------------------------------
# BUILD FULL TURBINE MESH
# -------------------------------------------------

def build_full_mesh(S, config_path=None):

    # The orchestrator supplies the exact, already-oriented gravity mesh so the
    # two load cases cannot drift in node/element order due to a second meshing pass.
    shared_mesh = os.environ.get("TURBINE_REUSE_MESH")
    if shared_mesh:
        with open(shared_mesh, "rb") as fh:
            obj = pickle.load(fh)
        if not isinstance(obj, tuple) or len(obj) < 2:
            raise ValueError(f"Shared mesh file has an unexpected format: {shared_mesh}")
        mesh, thickness = obj[0], obj[1]
        if not hasattr(mesh, "nodes") or not isinstance(thickness, dict):
            raise TypeError("Shared gravity mesh file must contain (contracts.Mesh, thickness_dict)")
        return mesh, thickness

    from geometry.default_generator import load_params, build_default
    from solver.mesh import build_mesh

    gmsh.initialize()
    gmsh.model.add("wind_turbine")

    try:
        groups, thickness = build_default(
            load_params(config_path or CONFIG_PATH)
        )

        mesh = build_mesh(
            groups,
            h=S.mesh_size,
            h_base=float(os.environ.get("TURBINE_MESH_BASE_SIZE", 0.5)),
            d_refine=float(os.environ.get("TURBINE_MESH_REFINE_DISTANCE", 6.0)),
            order=int(os.environ.get("TURBINE_MESH_ORDER", 2)),
            thickness=thickness
        )

    finally:
        gmsh.finalize()

    return mesh, thickness


# -------------------------------------------------
# MAIN WIND ANALYSIS
# -------------------------------------------------

if __name__ == "__main__":

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # USER WIND INPUTS
    parser = argparse.ArgumentParser()

    parser.add_argument("--direction", type=float, default=0.0,
                        help="Wind direction in degrees")

    

    args = parser.parse_args()

    # Apply user inputs
    S = Settings()
    S.mesh_size = float(os.environ.get("TURBINE_MESH_SIZE", S.mesh_size))
    S.wind_bearing_deg = args.direction
    S.v_ref = 50
    from geometry.default_generator import load_params
    params = load_params(CONFIG_PATH)
    S.z_hub = float(params["tower"]["sections"][-1]["z1"]) + float(params["nacelle"]["height"]) / 2.0
    S.validate()
    mesh, thickness = build_full_mesh(S, CONFIG_PATH)

    

    # IMPORTANT:
    # Apply the same element orientation procedure
    # in run_gravity.py and run_wind.py.
    orient_turbine(mesh)
    print("\n--- ELEMENT ORIENTATION REPORT ---")
    report = orientation_report(mesh)

    for group, result in report.items():
        print(group, result)
    bcs.assign_node_sets(mesh)

    # -------------------------------------------------
    # COMPONENT NODE HELPER
    # -------------------------------------------------

    def component_nodes(mesh, group):

        group_id = mesh.group_names.index(group)

        elements = mesh.elems[
            mesh.elem_group == group_id
        ]

        return np.unique(elements)

    # -------------------------------------------------
    # HUB - NACELLE RIGID LINK
    # Coordinate-based patch selection
    # -------------------------------------------------

    # Hub: select nodes near the rear pole.
    # hub_nodes = component_nodes(mesh, "Hub")

    z_top = float(params["tower"]["sections"][-1]["z1"])
    nac = params["nacelle"]
    # hub_cfg = params["hub"]
    # hub_target = np.array([0.0, float(hub_cfg["overhang"]) - float(hub_cfg["diameter"]) / 2.0, z_top + float(nac["height"]) / 2.0])

    # hub_distance = np.linalg.norm(
    #     mesh.nodes[hub_nodes] - hub_target,
    #     axis=1
    # )

    # pa = hub_nodes[hub_distance <= 1.0]

    # # Nacelle: select nodes near the centre of its front plate.
    # nacelle_nodes = component_nodes(mesh, "Nacelle")

    # nacelle_xyz = mesh.nodes[nacelle_nodes]

    # pb = nacelle_nodes[
    #     (np.abs(nacelle_xyz[:, 1] - float(nac["y_front"])) < 1e-5) &
    #     (np.abs(nacelle_xyz[:, 0]) <= float(nac["width"]) / 2.0) &
    #     (np.abs(nacelle_xyz[:, 2] - (z_top + float(nac["height"]) / 2.0)) <= float(nac["height"]) / 2.0)
    # ]

    # print("\n--- INITIAL PATCH SELECTION ---")
    # print("Hub patch nodes:", len(pa))
    # print("Nacelle patch nodes:", len(pb))

    # if len(pa) == 0 or len(pb) == 0:
    #     raise RuntimeError(
    #         "Hub or Nacelle rigid-link patch selection failed."
    #     )

    # # Expand each patch by one element row.
    # pa = links.add_rows(mesh, pa, 1, "Hub")
    # pb = links.add_rows(mesh, pb, 1, "Nacelle")

    # print("\n--- EXPANDED PATCHES ---")
    # print("Hub patch nodes:", len(pa))
    # print("Nacelle patch nodes:", len(pb))

    # # Create the rigid link.
    # LINKS = [
    #     links.make_link(
    #         mesh,
    #         "HUB_NACELLE",
    #         "Hub",
    #         pa,
    #         "Nacelle",
    #         pb
    #     )
    # ]

    # print("\nHub-Nacelle rigid link created successfully.")

    # -------------------------------------------------
    # COMPONENT CONNECTION CHECK
    # -------------------------------------------------

    print("\n--- COMPONENT CONNECTION CHECK ---")

    group_nodes = {}

    for gi, name in enumerate(mesh.group_names):

        elems = mesh.elems[
            mesh.elem_group == gi
        ]

        group_nodes[name] = set(elems.flatten())

    for i, name1 in enumerate(mesh.group_names):

        for name2 in mesh.group_names[i + 1:]:

            shared = group_nodes[name1] & group_nodes[name2]

            if shared:
                print(
                    f"{name1:10s} <-> {name2:10s}: "
                    f"{len(shared)} shared nodes"
                )
            else:
                print(
                    f"{name1:10s} <-> {name2:10s}: "
                    "NO shared nodes"
                )

    # -------------------------------------------------
    # TOWER TOP RING CONNECTION CHECK
    # -------------------------------------------------

    print("\n--- TOWER TOP RING CONNECTION CHECK ---")

    tower_group = f"Tower_{len(params['tower']['sections'])}"
    tower_top_nodes = component_nodes(mesh, tower_group)
    ring_nodes = component_nodes(mesh, "TowerTopRing")
    nacelle_nodes = component_nodes(mesh, "Nacelle")

    shared_tower_ring = np.intersect1d(
        tower_top_nodes,
        ring_nodes
    )

    shared_ring_nacelle = np.intersect1d(
        ring_nodes,
        nacelle_nodes
    )

    print(
        f"{tower_group} <-> TowerTopRing shared nodes:",
        len(shared_tower_ring)
    )

    print(
        "TowerTopRing <-> Nacelle shared nodes:",
        len(shared_ring_nacelle)
    )

    if len(shared_tower_ring) == 0:
        raise RuntimeError(
            f"{tower_group} and TowerTopRing are not connected."
        )

    if len(shared_ring_nacelle) == 0:
        raise RuntimeError(
            "TowerTopRing and Nacelle are not connected."
        )

    # -------------------------------------------------
    # PREFLIGHT CHECKS
    # -------------------------------------------------

    bcs.preflight(
        mesh,
        thickness,
        expected_base_radius=float(params["tower"]["sections"][0]["d0"]) / 2.0
    )

    # -------------------------------------------------
    # ELEMENT NORMAL CHECK
    # -------------------------------------------------

    n_out, n_in = R.check_outward(mesh)

    print(
        f"\ntower element normals: "
        f"{n_out} outward, {n_in} inward"
    )

    if n_in != 0:
        raise RuntimeError(
            "Inward tower element normals detected. "
            "Check orient_turbine() and the mesh."
        )

    # -------------------------------------------------
    # GENERATE WIND LOADS
    # -------------------------------------------------

    print("\n--- WIND LOAD GENERATION ---")

    wind_loads, component_report = wind_loadset(
        mesh,
        S,
        info=True
    )

    print("\n--- COMPONENT WIND LOAD REPORT ---")
    print(component_report)

    print("\n--- TOTAL WIND LOAD ---")

    print(
        "Total Fx:",
        wind_loads.total_force[0],
        "N"
    )

    print(
        "Total Fy:",
        wind_loads.total_force[1],
        "N"
    )

    print(
        "Total Fz:",
        wind_loads.total_force[2],
        "N"
    )

    print(
        "Base moment:",
        wind_loads.base_moment,
        "N m"
    )

    print(
        "Reference wind speed:",
        wind_loads.v_ref,
        "m/s"
    )

    # -------------------------------------------------
    # WRITE CALCULIX INPUT FILE
    # -------------------------------------------------

    inp = write_inp(
        str(OUT_DIR / "W.inp"),
        mesh,
        thickness,
        S,
        case="W",
        loads=wind_loads,
        rigid_head_groups=("Nacelle", "Hub"),
        **BLADE_KW
    )

    # -------------------------------------------------
    # RUN CALCULIX
    # -------------------------------------------------

    dat = run_ccx(
        inp,
        ccx=CCX_EXE
    )

    # -------------------------------------------------
    # READ RESULTS
    # -------------------------------------------------

    res = R.read_result(
        dat,
        mesh,
        "W",
        applied_force=wind_loads.total_force,
        v_ref=S.v_ref
    )

    # Record provenance only after a successful solver run and successful result read.
    res.metadata = make_metadata(
        case="W", geometry_hash=geometry_fingerprint(CONFIG_PATH),
        mesh_hash=mesh_fingerprint(mesh), v_ref=S.v_ref,
        wind_direction_deg=S.wind_bearing_deg,
        solver={"executable": CCX_EXE or os.environ.get("CCX_PATH") or "PATH lookup",
                "input_file_sha256": file_fingerprint(inp), "solver_version": "see CalculiX .log"},
        material={"E_Pa": S.E, "nu": S.nu, "rho_kg_m3": S.rho},
        settings={"mesh_size_m": S.mesh_size,
                  "blade_mass_match": True,
                  "blade_mass_factor": 1.04536,
                  "blade_ei_file": BLADE_TABLE,
                  "mesh_base_size_m": float(os.environ.get("TURBINE_MESH_BASE_SIZE", 0.5)),
                  "mesh_refine_distance_m": float(os.environ.get("TURBINE_MESH_REFINE_DISTANCE", 6.0)),
                  "mesh_order": int(os.environ.get("TURBINE_MESH_ORDER", 2)),
                  "shear_alpha": S.shear_alpha,
                  "Cd_tower": S.Cd_tower, "Cd_blade": S.Cd_blade,
                  "air_pressure_Pa": S.air_pressure, "air_temp_K": S.air_temp}
    )

    # -------------------------------------------------
    # BASE REACTION CHECK
    # -------------------------------------------------

    print("\n--- BASE REACTION CHECK ---")

    print(
        "Applied force:",
        np.round(wind_loads.total_force, 2),
        "N"
    )

    print(
        "Base reaction force:",
        np.round(res.base_reaction_force, 2),
        "N"
    )

    print(
        "Base reaction moment:",
        np.round(res.base_reaction_moment, 2),
        "N m"
    )

    force_balance = (
        wind_loads.total_force
        + res.base_reaction_force
    )

    print(
        "Force balance (should be near zero):",
        np.round(force_balance, 2),
        "N"
    )

    # -------------------------------------------------
    # VON MISES STRESS
    # -------------------------------------------------

    vm = R.von_mises(
        np.stack([
            res.stress_outer,
            res.stress_inner
        ])
    )

    print(
        "\n--- WIND ONLY: MAX VON MISES PER GROUP "
        "(MPa), OUTER / INNER ---"
    )

    for gi, name in enumerate(mesh.group_names):

        m = mesh.elem_group == gi

        print(
            f"{name:12s} "
            f"outer {vm[0][m].max() / 1e6:8.2f}  "
            f"inner {vm[1][m].max() / 1e6:8.2f}"
        )

    # -------------------------------------------------
    # DISPLACEMENTS
    # -------------------------------------------------

    u = res.displacements

    disp = np.linalg.norm(u, axis=1)

    imax = np.argmax(disp)

    print(
        f"\nMaximum displacement: "
        f"{disp[imax]:.4f} m "
        f"at z = {mesh.nodes[imax, 2]:.2f} m"
    )

    print("\n--- MAX DISPLACEMENT LOCATION ---")

    print("Node index:", imax)
    print("Original coordinates:", mesh.nodes[imax])
    print("Displacement vector:", u[imax])

    # -------------------------------------------------
    # MAXIMUM DISPLACEMENT BY COMPONENT
    # -------------------------------------------------

    print("\n--- MAX DISPLACEMENT BY COMPONENT ---")

    for gi, name in enumerate(mesh.group_names):

        element_ids = np.where(
            mesh.elem_group == gi
        )[0]

        node_ids = np.unique(
            mesh.elems[element_ids].flatten()
        )

        component_disp = np.linalg.norm(
            u[node_ids],
            axis=1
        )

        local_max = np.argmax(component_disp)

        node_id = node_ids[local_max]

        print(
            f"{name:12s}: "
            f"{component_disp[local_max]:.4f} m "
            f"at {mesh.nodes[node_id]}"
        )

    # -------------------------------------------------
    # SAVE RESULTS
    # -------------------------------------------------

    atomic_pickle(OUT_DIR / "res_W.pkl", res)

    # Save the mesh used for this wind analysis.
    with open(str(OUT_DIR / "wind_mesh.pkl"), "wb") as f:
        pickle.dump(mesh, f)

    print("\nWind analysis completed.")
    print("Results saved to out/res_W.pkl")
    print("Mesh saved to out/wind_mesh.pkl")