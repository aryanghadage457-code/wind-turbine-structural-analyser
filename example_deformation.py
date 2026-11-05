"""Validated PyVista view of combined gravity + reference-wind deformation.

All operating conditions and mesh identities are read from saved result metadata.
No wind speed or direction is hardcoded here.
"""
from __future__ import annotations
import json
import pickle
from pathlib import Path
import numpy as np
from analysis_metadata import mesh_fingerprint
from contracts import Mesh, SolveResult

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "out"
MESH_FILE = OUT_DIR / "full_mesh.pkl"
WIND_MESH_FILE = OUT_DIR / "wind_mesh.pkl"
GRAVITY_RESULT_FILE = OUT_DIR / "res_G.pkl"
WIND_RESULT_FILE = OUT_DIR / "res_W.pkl"
STRESS_RESULT_FILE = OUT_DIR / "stress_strain_results.npz"


def _load_pickle(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def load_validated_results(mesh_file=MESH_FILE, wind_mesh_file=WIND_MESH_FILE,
                           gravity_file=GRAVITY_RESULT_FILE, wind_file=WIND_RESULT_FILE,
                           stress_file=STRESS_RESULT_FILE):
    """Load and cross-check all result provenance before returning arrays for plotting."""
    if not Path(stress_file).is_file():
        raise FileNotFoundError(f"Combined stress results not found: {stress_file}. Run run_analysis.py first.")
    mesh_obj = _load_pickle(mesh_file)
    mesh = mesh_obj[0] if isinstance(mesh_obj, tuple) else mesh_obj
    wind_mesh_obj = _load_pickle(wind_mesh_file)
    wind_mesh = wind_mesh_obj[0] if isinstance(wind_mesh_obj, tuple) else wind_mesh_obj
    gravity = _load_pickle(gravity_file)
    wind = _load_pickle(wind_file)
    if not isinstance(mesh, Mesh) or not isinstance(wind_mesh, Mesh):
        raise TypeError("Saved mesh files must contain contracts.Mesh objects")
    if not isinstance(gravity, SolveResult) or not isinstance(wind, SolveResult):
        raise TypeError("Saved solver results must contain contracts.SolveResult objects")
    if gravity.case != "G" or wind.case != "W":
        raise ValueError("Expected gravity case G and wind case W results")

    # Exact mesh identity, including connectivity and row order (not just dimensions).
    mesh_id = mesh_fingerprint(mesh)
    if mesh_id != mesh_fingerprint(wind_mesh):
        raise ValueError("Gravity and wind meshes differ in coordinates, connectivity, groups or ordering")
    if not (np.array_equal(mesh.nodes, wind_mesh.nodes) and np.array_equal(mesh.elems, wind_mesh.elems)
            and np.array_equal(mesh.elem_group, wind_mesh.elem_group)
            and mesh.group_names == wind_mesh.group_names):
        raise ValueError("Gravity and wind mesh arrays are not identical")

    gm = getattr(gravity, "metadata", {}) or {}
    wm = getattr(wind, "metadata", {}) or {}
    for key, label in (("geometry_fingerprint", "geometry"), ("mesh_fingerprint", "mesh")):
        if not gm.get(key) or not wm.get(key):
            raise ValueError(f"Missing {label} identity in solver-result metadata; rerun run_analysis.py")
        if gm[key] != wm[key]:
            raise ValueError(f"Gravity and wind {label} identities differ")
    if gm["mesh_fingerprint"] != mesh_id:
        raise ValueError("Saved solver metadata does not identify the displayed mesh")

    with np.load(stress_file, allow_pickle=False) as loaded:
        stress = {k: loaded[k].copy() for k in loaded.files}
    if "metadata_json" not in stress:
        raise ValueError("Stress/strain export has no metadata_json; regenerate with run_analysis.py")
    try:
        sm = json.loads(str(stress["metadata_json"].item()))
    except Exception as exc:
        raise ValueError(f"Could not parse stress/strain metadata: {exc}") from exc
    for key, label in (("geometry_fingerprint", "geometry"), ("mesh_fingerprint", "mesh")):
        if sm.get(key) != wm.get(key):
            raise ValueError(f"Stress/strain {label} identity does not match solver results")
    if "wind_direction_deg" not in wm or wm["wind_direction_deg"] is None:
        raise ValueError("Wind solver result has no saved wind direction")
    direction = float(wm["wind_direction_deg"]) % 360.0
    if not np.isclose(float(sm.get("wind_direction_deg", np.nan)) % 360.0, direction):
        raise ValueError("Stress/strain wind direction does not match the wind solver case")
    v_ref = float(wm.get("reference_wind_speed_m_s", np.nan))
    if not np.isfinite(v_ref) or v_ref <= 0:
        raise ValueError("Wind result has an invalid/missing reference wind speed")
    if not np.isclose(float(sm.get("reference_wind_speed_m_s", np.nan)), v_ref):
        raise ValueError("Stress/strain reference wind speed differs from the wind solver result")
    wind_speed = float(sm.get("operating_wind_speed_m_s", np.nan))
    if not np.isfinite(wind_speed) or wind_speed < 0:
        raise ValueError("Stress/strain metadata has an invalid operating wind speed")

    if gravity.displacements.shape != (mesh.n_nodes, 3) or wind.displacements.shape != (mesh.n_nodes, 3):
        raise ValueError("Gravity/wind displacement dimensions do not match mesh node count")
    if gravity.stress_outer.shape != (mesh.n_elems, 6) or wind.stress_outer.shape != (mesh.n_elems, 6):
        raise ValueError("Gravity/wind stress dimensions do not match mesh element count")
    if stress.get("outer_principal", np.empty((0,))).shape != (mesh.n_elems, 3):
        raise ValueError("Combined outer principal-stress array does not match mesh element count")
    for key in ("outer_von_mises", "outer_max_shear", "outer_principal"):
        if key not in stress:
            raise ValueError(f"Missing required combined stress array '{key}'")
    if stress["outer_von_mises"].shape != (mesh.n_elems,) or stress["outer_max_shear"].shape != (mesh.n_elems,):
        raise ValueError("Combined stress element arrays have incompatible dimensions")

    scale = (wind_speed / v_ref) ** 2
    displacement = gravity.displacements + scale * wind.displacements
    if displacement.shape != (mesh.n_nodes, 3) or not np.isfinite(displacement).all():
        raise ValueError("Combined displacement array is invalid")
    return mesh, gravity, wind, stress, displacement, {
        "wind_speed": wind_speed, "v_ref": v_ref, "wind_direction": direction,
        "wind_scale": scale, "geometry_fingerprint": gm["geometry_fingerprint"],
        "mesh_fingerprint": mesh_id,
    }


def main():
    mesh, gravity_result, wind_result, stress_results, total_displacements, conditions = load_validated_results()
    # Import optional visualization dependencies only after data validation.
    try:
        import pyvista as pv
    except ImportError as exc:
        raise ImportError("PyVista is required for the interactive viewer. Install with: python -m pip install pyvista") from exc
    from visualization.mesh_builder import build_turbine_mesh
    from visualization.deformation import apply_deformation
    from visualization.contour_plots import plot_principal_stress

    original_grid = build_turbine_mesh(mesh)
    if original_grid.n_points != mesh.n_nodes or original_grid.n_cells != mesh.n_elems:
        raise ValueError("PyVista mesh builder changed node/element count or ordering")
    deformed_grid = apply_deformation(original_grid, total_displacements, scale=1.0)
    # Principal values are sorted sigma1 >= sigma2 >= sigma3; column 0 is maximum.
    max_principal_mpa = stress_results["outer_principal"][:, 0] / 1e6
    print("\nSimulation conditions")
    print(f"Operating wind speed: {conditions['wind_speed']:.2f} m/s")
    print(f"Reference wind speed: {conditions['v_ref']:.2f} m/s")
    print(f"Wind direction FROM: {conditions['wind_direction']:.1f} degrees")
    print(f"Wind displacement scale: {conditions['wind_scale']:.4f}")
    print("Maximum principal stress [MPa]: min={:.3g}, max={:.3g}, mean={:.3g}".format(
        np.min(max_principal_mpa), np.max(max_principal_mpa), np.mean(max_principal_mpa)))

    plotter = pv.Plotter(window_size=[1200, 800])
    plotter.set_background("#20252B")
    original_actor = plotter.add_mesh(original_grid, color="lightgrey", style="wireframe",
                                      opacity=0.35, line_width=1, label="Original Turbine")
    plot_principal_stress(plotter, deformed_grid, stress_results, component="max", surface="outer")

    def toggle_original(checked):
        original_actor.SetVisibility(checked)
        plotter.render()

    plotter.add_checkbox_button_widget(toggle_original, value=True, position=(20, 20), size=30,
                                       color_on="green", color_off="grey")
    plotter.add_text("Show Original Turbine", position=(60, 25), font_size=12, color="white")
    plotter.add_axes()
    plotter.show_grid(color="white", xlabel="X", ylabel="Y", zlabel="Z")
    plotter.add_text(
        f"Maximum Principal Stress | Wind: {conditions['wind_speed']:.1f} m/s | Direction: {conditions['wind_direction']:.0f} deg",
        position="upper_edge", font_size=14, color="white")
    plotter.camera_position = "iso"
    plotter.show()


if __name__ == "__main__":
    main()
