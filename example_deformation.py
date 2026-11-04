
import pickle
from pathlib import Path

import numpy as np
import pyvista as pv

from visualization.mesh_builder import build_turbine_mesh
from visualization.deformation import apply_deformation
from visualization.contour_plots import plot_principal_stress


# --------------------------------------------------
# File paths
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

MESH_FILE = BASE_DIR / "out" / "full_mesh.pkl"
GRAVITY_RESULT_FILE = BASE_DIR / "out" / "res_G.pkl"
STRESS_RESULT_FILE = BASE_DIR / "out" / "stress_strain_results.npz"
WIND_RESULT_FILE = BASE_DIR / "out" / "res_W.pkl"


# --------------------------------------------------
# Load mesh and solver results
# --------------------------------------------------

print("Loading mesh...")

with open(MESH_FILE, "rb") as file:
    mesh, group_properties = pickle.load(file)

print("Loading displacement results...")

with open(GRAVITY_RESULT_FILE, "rb") as file:
    gravity_result = pickle.load(file)

with open(WIND_RESULT_FILE, "rb") as file:
    wind_result = pickle.load(file)

print("Loading stress and strain results...")

if not STRESS_RESULT_FILE.exists():
    raise FileNotFoundError(
        "Stress results not found. Run StressAndStrain.py first."
    )

stress_results = np.load(STRESS_RESULT_FILE, allow_pickle=False)


# --------------------------------------------------
# Read wind condition from saved results
# --------------------------------------------------

required_metadata = [
    "wind_speed",
    "v_ref",
    "wind_direction"
]

missing_metadata = [
    key for key in required_metadata
    if key not in stress_results.files
]

if missing_metadata:
    raise ValueError(
        f"Missing metadata in stress_strain_results.npz: "
        f"{missing_metadata}\n"
        "Update StressAndStrain.py to save these metadata values "
        "and regenerate the results."
    )

wind_speed = float(stress_results["wind_speed"])
v_ref = float(stress_results["v_ref"])
wind_direction = float(stress_results["wind_direction"])

if not np.isfinite(wind_speed) or wind_speed < 0:
    raise ValueError("Invalid wind speed in saved results.")

if not np.isfinite(v_ref) or v_ref <= 0:
    raise ValueError("Invalid reference wind speed in saved results.")

if not np.isfinite(wind_direction):
    raise ValueError("Invalid wind direction in saved results.")

# Check reference speed against the wind solver result
if wind_result.v_ref is None or not np.isclose(
    v_ref, wind_result.v_ref
):
    raise ValueError(
        "Reference wind speed in stress results does not match "
        "the wind solver result."
    )

wind_scale = (wind_speed / v_ref) ** 2

print("\nWind condition used for visualization")
print(f"Operating wind speed: {wind_speed:.2f} m/s")
print(f"Reference wind speed: {v_ref:.2f} m/s")
print(f"Wind direction: {wind_direction:.1f} degrees")
print(f"Wind scale factor: {wind_scale:.4f}")


# --------------------------------------------------
# Maximum principal stress statistics
# --------------------------------------------------

stress = stress_results["outer_principal"][:, 2] / 1e6

print("\nMaximum Principal Stress Statistics (MPa)")
print("Minimum:", np.min(stress))
print("Maximum:", np.max(stress))
print("Mean:", np.mean(stress))


# --------------------------------------------------
# Build original turbine mesh
# --------------------------------------------------

original_grid = build_turbine_mesh(mesh)

print("\nMesh created successfully.")
print(f"Nodes: {original_grid.n_points}")
print(f"Elements: {original_grid.n_cells}")


# --------------------------------------------------
# Validate result dimensions
# --------------------------------------------------

if gravity_result.displacements.shape != (
    original_grid.n_points, 3
):
    raise ValueError(
        "Gravity displacement dimensions do not match the mesh."
    )

if wind_result.displacements.shape != (
    original_grid.n_points, 3
):
    raise ValueError(
        "Wind displacement dimensions do not match the mesh."
    )

if len(stress) != original_grid.n_cells:
    raise ValueError(
        "Stress result element count does not match the mesh."
    )


# --------------------------------------------------
# Apply combined gravity + wind deformation
# --------------------------------------------------

total_displacements = (
    gravity_result.displacements
    + wind_scale * wind_result.displacements
)

deformation_scale = 1.0

deformed_grid = apply_deformation(
    original_grid,
    total_displacements,
    scale=deformation_scale
)

print("\nCombined deformation applied.")
print(f"Wind speed: {wind_speed:.2f} m/s")
print(f"Wind direction: {wind_direction:.1f} degrees")
print(f"Wind displacement scale: {wind_scale:.4f}")


# --------------------------------------------------
# Create visualisation window
# --------------------------------------------------

plotter = pv.Plotter(window_size=[1200, 800])

plotter.set_background("#20252B")


# --------------------------------------------------
# Display original turbine
# --------------------------------------------------

original_actor = plotter.add_mesh(
    original_grid,
    color="lightgrey",
    style="wireframe",
    opacity=0.35,
    line_width=1,
    label="Original Turbine"
)


# --------------------------------------------------
# Display Maximum Principal Stress contour
# --------------------------------------------------

contour_actor = plot_principal_stress(
    plotter,
    deformed_grid,
    stress_results,
    component="max",
    surface="outer"
)


# --------------------------------------------------
# Checkbox: Show / hide original turbine
# --------------------------------------------------

def toggle_original(checked):
    original_actor.SetVisibility(checked)
    plotter.render()


plotter.add_checkbox_button_widget(
    toggle_original,
    value=True,
    position=(20, 20),
    size=30,
    color_on="green",
    color_off="grey"
)

plotter.add_text(
    "Show Original Turbine",
    position=(60, 25),
    font_size=12,
    color="white"
)


# --------------------------------------------------
# Additional visualisation settings
# --------------------------------------------------

plotter.add_axes()

plotter.show_grid(
    color="white",
    xlabel="X",
    ylabel="Y",
    zlabel="Z"
)

plotter.add_text(
    f"Maximum Principal Stress | Wind: {wind_speed:.1f} m/s "
    f"| Direction: {wind_direction:.0f} deg",
    position="upper_edge",
    font_size=14,
    color="white"
)

plotter.camera_position = "iso"

plotter.show()

stress_results.close()
