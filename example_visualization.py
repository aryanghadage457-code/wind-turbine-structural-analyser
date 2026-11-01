import pickle
import pyvista as pv

from visualization.mesh_builder import build_turbine_mesh
from visualization.contour_plots import enable_element_selection

# Load existing mesh
with open("out/full_mesh.pkl", "rb") as f:
    mesh, group_properties = pickle.load(f)

# Build PyVista mesh
grid = build_turbine_mesh(mesh)

print("3D mesh created successfully")
print("Points:", grid.n_points)
print("Elements:", grid.n_cells)
print("Bounds:", grid.bounds)

# Create plotter
plotter = pv.Plotter(window_size=(1200, 800))

# Add original turbine mesh
plotter.add_mesh(
    grid,
    show_edges=True,
    color="lightgrey",
    edge_color="black",
    line_width=0.5
)

# Enable element selection
enable_element_selection(plotter, grid)

# Display mesh
plotter.set_background("white")
plotter.show()