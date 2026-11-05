
import pickle
import numpy as np
import pyvista as pv
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons

from visualization.mesh_builder import build_turbine_mesh
from visualization.contour_plots import (
    plot_von_mises,
    enable_element_selection,
)
from visualization.element_details import get_element_details


# --------------------------------------------------
# LOAD MESH AND STRESS RESULTS
# --------------------------------------------------

with open("out/full_mesh.pkl", "rb") as f:
    mesh, group_properties = pickle.load(f)

loaded = np.load("out/stress_strain_results.npz")
results = dict(loaded)


# --------------------------------------------------
# ELEMENT DETAILS WINDOW VARIABLES
# --------------------------------------------------

details_fig = None
details_text_ax = None
mohr_ax = None

surface_ax = None
surface_radio = None

selected_cell_id = None
selected_element_id = None

active_surface = "outer"


# --------------------------------------------------
# UPDATE ELEMENT DETAILS WINDOW
# --------------------------------------------------

def update_element_window(details):

    global details_fig
    global details_text_ax, mohr_ax
    global surface_ax, surface_radio

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

        # Surface selection buttons
        surface_ax = details_fig.add_axes(
            [0.43, 0.02, 0.18, 0.12]
        )

        surface_radio = RadioButtons(
            surface_ax,
            ("outer", "inner"),
            active=0 if active_surface == "outer" else 1
        )

        surface_ax.set_title(
            "Select Surface",
            fontsize=10
        )

        # Register callback only once
        surface_radio.on_clicked(change_surface)

    # Clear previous information
    details_text_ax.clear()
    mohr_ax.clear()

    stress = details["stress"]
    strain = details["strain"]

    # --------------------------------------------------
    # ELEMENT INFORMATION
    # --------------------------------------------------

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
        0.02,
        0.98,
        "\n".join(lines),
        transform=details_text_ax.transAxes,
        verticalalignment="top",
        horizontalalignment="left",
        fontsize=9,
        family="monospace"
    )

    details_text_ax.set_title("ELEMENT ANALYSIS")
    details_text_ax.axis("off")

    # --------------------------------------------------
    # MOHR'S CIRCLES
    # --------------------------------------------------

    circles = details["mohr"]["circles"]

    for name, circle in circles.items():

        sigma = np.asarray(circle["sigma"]) / 1e6
        tau = np.asarray(circle["tau"]) / 1e6
        tau_negative = np.asarray(circle["tau_negative"]) / 1e6

        mohr_ax.plot(
            sigma,
            tau,
            label=name
        )

        mohr_ax.plot(
            sigma,
            tau_negative
        )

    mohr_ax.axhline(
        0,
        color="black",
        linewidth=0.7
    )

    mohr_ax.axvline(
        0,
        color="black",
        linewidth=0.7
    )

    mohr_ax.set_xlabel("Normal Stress (MPa)")
    mohr_ax.set_ylabel("Shear Stress (MPa)")

    mohr_ax.set_title(
        f"Mohr's Circles - Element {details['element_id']}"
    )

    mohr_ax.grid(True)
    mohr_ax.axis("equal")
    mohr_ax.legend(fontsize=8)

    # --------------------------------------------------
    # WINDOW FORMATTING
    # --------------------------------------------------

    details_fig.suptitle(
        f"Element {details['element_id']} - "
        f"{details['group_name']}",
        fontsize=14
    )

    # Reserve bottom space for surface selector
    details_fig.tight_layout(
        rect=[0, 0.16, 1, 0.95]
    )

    details_fig.canvas.draw_idle()
    details_fig.canvas.flush_events()

    plt.show(block=False)
    plt.pause(0.001)


# --------------------------------------------------
# CHANGE BETWEEN OUTER AND INNER SURFACES
# --------------------------------------------------

def change_surface(label):

    global active_surface

    active_surface = label

    if selected_cell_id is None:
        return

    details = get_element_details(
        results,
        mesh,
        selected_cell_id,
        surface=active_surface
    )

    update_element_window(details)


# --------------------------------------------------
# SELECTED ELEMENT CALLBACK
# --------------------------------------------------

def show_element_details(original_cell_id, element_id):

    global selected_cell_id
    global selected_element_id

    selected_cell_id = original_cell_id
    selected_element_id = element_id

    details = get_element_details(
        results,
        mesh,
        original_cell_id,
        surface=active_surface
    )

    update_element_window(details)


# --------------------------------------------------
# BUILD PYVISTA MESH
# --------------------------------------------------

grid = build_turbine_mesh(mesh)

print("Grid type:", type(grid))
print("Cell type:", grid.celltypes[0])
print("Number of cells:", grid.n_cells)
print("Number of points:", grid.n_points)
print("First cell:", grid.get_cell(0))


# --------------------------------------------------
# CREATE PLOTTER
# --------------------------------------------------

plotter = pv.Plotter()

# Display outer-surface von Mises contour
plot_von_mises(
    plotter,
    grid,
    results,
    surface="outer",
)


# --------------------------------------------------
# ENABLE ELEMENT SELECTION
# --------------------------------------------------

enable_element_selection(
    plotter,
    grid,
    on_element_selected=show_element_details,
)


# --------------------------------------------------
# DISPLAY VISUALIZATION
# --------------------------------------------------

plotter.show()
