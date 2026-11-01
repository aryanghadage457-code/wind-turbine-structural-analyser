
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


# --------------------------------------------------
# Load mesh and solver results
# --------------------------------------------------

print("Loading mesh...")

with open(MESH_FILE, "rb") as file:
    mesh, group_properties = pickle.load(file)

print("Loading displacement results...")

with open(GRAVITY_RESULT_FILE, "rb") as file:
    gravity_result = pickle.load(file)

print("Loading stress and strain results...")

if not STRESS_RESULT_FILE.exists():
    raise FileNotFoundError(
        "Stress results not found. Run StressAndStrain.py first."
    )

stress_results = np.load(STRESS_RESULT_FILE)

# Maximum principal stress statistics
stress = stress_results["outer_principal"][:, 2] / 1e6

print("\nMaximum Principal Stress Statistics (MPa)")
print("Minimum:", np.min(stress))
print("Maximum:", np.max(stress))
print("Mean:", np.mean(stress))


# --------------------------------------------------
# Build original turbine mesh
# --------------------------------------------------

original_grid = build_turbine_mesh(mesh)

print("Mesh created successfully.")
print(f"Nodes: {original_grid.n_points}")
print(f"Elements: {original_grid.n_cells}")


# --------------------------------------------------
# Apply deformation
# --------------------------------------------------

deformation_scale = 1.0

deformed_grid = apply_deformation(
    original_grid,
    gravity_result.displacements,
    scale=deformation_scale
)

print("Deformation applied.")


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
    "Wind Turbine - Maximum Principal Stress",
    position="upper_edge",
    font_size=14,
    color="white"
)

plotter.camera_position = "iso"

plotter.show()
