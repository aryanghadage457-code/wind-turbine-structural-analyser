
import pickle
import numpy as np
import pyvista as pv
import matplotlib.pyplot as plt


from visualization.mesh_builder import build_turbine_mesh
from visualization.contour_plots import (
    plot_von_mises,
    enable_element_selection,
)
from visualization.element_details import get_element_details

# Load the original mesh
with open("out/full_mesh.pkl", "rb") as f:
    mesh, group_properties = pickle.load(f)

# Load saved stress results
loaded = np.load("out/stress_strain_results.npz")
results = dict(loaded)

# Display details of the selected element

# Reusable Element Details window
details_fig = None
details_text_ax = None
mohr_ax = None


def update_element_window(details):
    global details_fig, details_text_ax, mohr_ax

    # Create the window only once
    if details_fig is None or not plt.fignum_exists(details_fig.number):

        details_fig = plt.figure(
            "Wind Turbine - Element Details",
            figsize=(14, 8)
        )

        layout = details_fig.add_gridspec(
            1, 2,
            width_ratios=[1.1, 1.4]
        )

        details_text_ax = details_fig.add_subplot(layout[0, 0])
        mohr_ax = details_fig.add_subplot(layout[0, 1])

    # Clear previous element information
    details_text_ax.clear()
    mohr_ax.clear()

    stress = details["stress"]
    strain = details["strain"]

    # ---------------- ELEMENT INFORMATION ----------------

    lines = []

    lines.append(f"ELEMENT ID: {details['element_id']}")
    lines.append(f"COMPONENT: {details['group_name']}")
    lines.append(f"SURFACE: {details['surface']}")

    lines.append("")
    lines.append("STRESS COMPONENTS (MPa)")

    for name, value in stress["components"].items():
        lines.append(f"{name}: {value / 1e6:.4f}")

    lines.append("")
    lines.append("PRINCIPAL STRESSES (MPa)")

    for name, value in stress["principal"].items():
        lines.append(f"{name}: {value / 1e6:.4f}")

    lines.append("")
    lines.append(
        f"Von Mises: {stress['von_mises'] / 1e6:.4f} MPa"
    )

    lines.append(
        f"Maximum shear: {stress['maximum_shear'] / 1e6:.4f} MPa"
    )

    lines.append("")
    lines.append("STRAIN COMPONENTS")

    for name, value in strain["tensorial_components"].items():
        lines.append(f"{name}: {value:.6e}")

    lines.append("")
    lines.append("ENGINEERING SHEAR STRAINS")

    for name, value in strain["engineering_shear"].items():
        lines.append(f"{name}: {value:.6e}")

    lines.append("")
    lines.append("PRINCIPAL STRAINS")

    for name, value in strain["principal"].items():
        lines.append(f"{name}: {value:.6e}")

    lines.append("")
    lines.append(
        f"Equivalent strain: {strain['equivalent']:.6e}"
    )

    lines.append(
        f"Maximum shear strain: {strain['maximum_shear']:.6e}"
    )

    details_text_ax.text(
        0.02, 0.98,
        "\n".join(lines),
        transform=details_text_ax.transAxes,
        verticalalignment="top",
        horizontalalignment="left",
        fontsize=9,
        family="monospace"
    )

    details_text_ax.set_title("ELEMENT ANALYSIS")
    details_text_ax.axis("off")

    # ---------------- MOHR'S CIRCLES ----------------

    circles = details["mohr"]["circles"]

    for name, circle in circles.items():

        sigma = np.asarray(circle["sigma"]) / 1e6
        tau = np.asarray(circle["tau"]) / 1e6
        tau_negative = np.asarray(circle["tau_negative"]) / 1e6

        mohr_ax.plot(sigma, tau, label=name)
        mohr_ax.plot(sigma, tau_negative)

    mohr_ax.axhline(0, color="black", linewidth=0.7)
    mohr_ax.axvline(0, color="black", linewidth=0.7)

    mohr_ax.set_xlabel("Normal Stress (MPa)")
    mohr_ax.set_ylabel("Shear Stress (MPa)")

    mohr_ax.set_title(
        f"Mohr's Circles - Element {details['element_id']}"
    )

    mohr_ax.grid(True)
    mohr_ax.axis("equal")
    mohr_ax.legend(fontsize=8)

    details_fig.suptitle(
        f"Element {details['element_id']} - "
        f"{details['group_name']}",
        fontsize=14
    )

    details_fig.tight_layout()

    # Refresh the same window
    details_fig.canvas.draw_idle()
    details_fig.canvas.flush_events()

    plt.show(block=False)
    plt.pause(0.001)    

def show_element_details(original_cell_id, element_id):

    details = get_element_details(
        results,
        mesh,
        original_cell_id,
        surface="outer"
    )

    update_element_window(details)
    
    

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
# Enable element selection
enable_element_selection(
    plotter,
    grid,
    on_element_selected=show_element_details,
)

# Display the plot
plotter.show()
