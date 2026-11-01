
import pickle
import numpy as np
import pyvista as pv

from visualization.mesh_builder import build_turbine_mesh
from visualization.contour_plots import (
    plot_von_mises,
    enable_element_selection,
)

# Load the original mesh
with open("out/full_mesh.pkl", "rb") as f:
    mesh, group_properties = pickle.load(f)

# Load saved stress results
loaded = np.load("out/stress_strain_results.npz")
results = dict(loaded)

# Build the PyVista mesh
grid = build_turbine_mesh(mesh)
print("Grid type:", type(grid))
print("Cell type:", grid.celltypes[0])
print("Number of cells:", grid.n_cells)
print("Number of points:", grid.n_points)
print("First cell:", grid.get_cell(0))

# Create the plotter
plotter = pv.Plotter()

# Display the outer-surface von Mises contour
plot_von_mises(
    plotter,
    grid,
    results,
    surface="outer",
)

# Enable element selection
enable_element_selection(
    plotter,
    grid,
)

# Display the plot
plotter.show()
