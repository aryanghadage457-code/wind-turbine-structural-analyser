
import numpy as np
import pyvista as pv

# ============================================================
# COMMON VALIDATION
# ============================================================

def _validate_surface(surface):
    if surface not in ("outer", "inner"):
        raise ValueError("Surface must be 'outer' or 'inner'.")


def _get_result(results, key):
    if key not in results:
        raise KeyError(f"Result '{key}' not found in saved results.")

    values = np.asarray(results[key], dtype=float)

    if not np.all(np.isfinite(values)):
        raise ValueError(f"Result '{key}' contains invalid values.")

    return values


def _add_element_contour(
    plotter,
    grid,
    values,
    title,
    unit,
):
    """Display element-wise scalar data on a copy of the mesh."""

    values = np.asarray(values, dtype=float)

    if values.shape != (grid.n_cells,):
        raise ValueError(
            f"Expected {grid.n_cells} element values, "
            f"received shape {values.shape}."
        )

    if not np.all(np.isfinite(values)):
        raise ValueError("Contour data contains invalid values.")

    contour_grid = grid.copy(deep=True)

    scalar_name = "contour_values"
    contour_grid.cell_data[scalar_name] = values

    # Preserve the original cell index for element selection.
    contour_grid.cell_data["original_cell_id"] = np.arange(
        grid.n_cells, dtype=np.int64
    )

    actor = plotter.add_mesh(
        contour_grid,
        scalars=scalar_name,
        cmap="jet",
        show_edges=True,
        edge_color="black",
        line_width=0.5,
        pickable=True,
        scalar_bar_args={
            "title": f"{title} ({unit})",
            "vertical": True,
            "title_font_size": 16,
            "label_font_size": 12,
        },
    )

    return actor


def _plot_surface_quantity(
    plotter,
    grid,
    results,
    surface,
    quantity,
    title,
    unit,
    conversion=1.0,
):
    _validate_surface(surface)

    key = f"{surface}_{quantity}"
    values = _get_result(results, key)

    return _add_element_contour(
        plotter,
        grid,
        values * conversion,
        title,
        unit,
    )


# ============================================================
# STRESS CONTOURS
# ============================================================

def plot_von_mises(
    plotter,
    grid,
    results,
    surface="outer",
):
    """Von Mises stress in MPa."""

    return _plot_surface_quantity(
        plotter, grid, results, surface,
        "von_mises",
        "Von Mises Stress",
        "MPa",
        1e-6,
    )


def plot_principal_stress(
    plotter,
    grid,
    results,
    component="max",
    surface="outer",
):
    """
    Principal stress contour in MPa.

    component: max, intermediate or min
    """

    _validate_surface(surface)

    indices = {
        "min": 0,
        "intermediate": 1,
        "max": 2,
    }

    if component not in indices:
        raise ValueError(
            "component must be 'max', 'intermediate' or 'min'."
        )

    principal = _get_result(
        results, f"{surface}_principal"
    )

    if principal.shape != (grid.n_cells, 3):
        raise ValueError(
            "Principal stress must have shape (elements, 3)."
        )

    # Ensure minimum, intermediate and maximum ordering.
    principal = np.sort(principal, axis=1)

    values = principal[:, indices[component]] / 1e6

    return _add_element_contour(
        plotter,
        grid,
        values,
        f"{component.capitalize()} Principal Stress",
        "MPa",
    )


def plot_stress_component(
    plotter,
    grid,
    results,
    component="xx",
    surface="outer",
):
    """
    Individual stress component in MPa.

    xx, yy, zz, xy, yz, zx
    """

    _validate_surface(surface)

    components = {
        "xx": (0, "Stress XX"),
        "yy": (1, "Stress YY"),
        "zz": (2, "Stress ZZ"),
        "xy": (3, "Shear Stress XY"),
        "yz": (4, "Shear Stress YZ"),
        "zx": (5, "Shear Stress ZX"),
    }

    if component not in components:
        raise ValueError(
            "component must be xx, yy, zz, xy, yz or zx."
        )

    stress = _get_result(
        results, f"{surface}_stress"
    )

    if stress.shape != (grid.n_cells, 6):
        raise ValueError(
            "Stress array must have shape (elements, 6)."
        )

    index, title = components[component]

    return _add_element_contour(
        plotter,
        grid,
        stress[:, index] / 1e6,
        title,
        "MPa",
    )


def plot_max_shear_stress(
    plotter,
    grid,
    results,
    surface="outer",
):
    """Maximum shear stress in MPa."""

    return _plot_surface_quantity(
        plotter, grid, results, surface,
        "max_shear",
        "Maximum Shear Stress",
        "MPa",
        1e-6,
    )


def plot_mean_stress(
    plotter,
    grid,
    results,
    surface="outer",
):
    """Mean (hydrostatic) stress in MPa."""

    return _plot_surface_quantity(
        plotter, grid, results, surface,
        "mean_stress",
        "Mean Stress",
        "MPa",
        1e-6,
    )


# ============================================================
# STRAIN CONTOURS
# ============================================================

def plot_equivalent_strain(
    plotter,
    grid,
    results,
    surface="outer",
):
    """Equivalent strain (dimensionless)."""

    return _plot_surface_quantity(
        plotter, grid, results, surface,
        "equivalent_strain",
        "Equivalent Strain",
        "m/m",
    )


def plot_principal_strain(
    plotter,
    grid,
    results,
    component="max",
    surface="outer",
):
    """
    Principal strain contour.

    component: max, intermediate or min
    """

    _validate_surface(surface)

    indices = {
        "min": 0,
        "intermediate": 1,
        "max": 2,
    }

    if component not in indices:
        raise ValueError(
            "component must be 'max', 'intermediate' or 'min'."
        )

    principal = _get_result(
        results, f"{surface}_principal_strain"
    )

    if principal.shape != (grid.n_cells, 3):
        raise ValueError(
            "Principal strain must have shape (elements, 3)."
        )

    principal = np.sort(principal, axis=1)

    values = principal[:, indices[component]]

    return _add_element_contour(
        plotter,
        grid,
        values,
        f"{component.capitalize()} Principal Strain",
        "m/m",
    )


def plot_strain_component(
    plotter,
    grid,
    results,
    component="xx",
    surface="outer",
):
    """
    Individual strain component.

    Normal: xx, yy, zz
    Engineering shear: xy, yz, zx
    """

    _validate_surface(surface)

    normal_components = {
        "xx": (0, "Normal Strain XX"),
        "yy": (1, "Normal Strain YY"),
        "zz": (2, "Normal Strain ZZ"),
    }

    shear_components = {
        "xy": (0, "Engineering Shear Strain XY"),
        "yz": (1, "Engineering Shear Strain YZ"),
        "zx": (2, "Engineering Shear Strain ZX"),
    }

    if component in normal_components:
        strain = _get_result(
            results, f"{surface}_strain"
        )

        if strain.shape != (grid.n_cells, 6):
            raise ValueError(
                "Strain array must have shape (elements, 6)."
            )

        index, title = normal_components[component]
        values = strain[:, index]

    elif component in shear_components:
        shear = _get_result(
            results, f"{surface}_engineering_shear"
        )

        if shear.shape != (grid.n_cells, 3):
            raise ValueError(
                "Engineering shear must have shape (elements, 3)."
            )

        index, title = shear_components[component]
        values = shear[:, index]

    else:
        raise ValueError(
            "component must be xx, yy, zz, xy, yz or zx."
        )

    return _add_element_contour(
        plotter,
        grid,
        values,
        title,
        "m/m",
    )


def plot_max_shear_strain(
    plotter,
    grid,
    results,
    surface="outer",
):
    """Maximum shear strain (dimensionless)."""

    return _plot_surface_quantity(
        plotter, grid, results, surface,
        "max_shear_strain",
        "Maximum Shear Strain",
        "m/m",
    )


# ============================================================
# DISPLACEMENT CONTOURS
# ============================================================

def plot_displacement(
    plotter,
    grid,
    displacements,
    component="magnitude",
):
    """
    Nodal displacement contour in metres.

    component: magnitude, x, y or z
    """

    displacements = np.asarray(
        displacements, dtype=float
    )

    if displacements.shape != (grid.n_points, 3):
        raise ValueError(
            f"Expected displacement shape "
            f"({grid.n_points}, 3), "
            f"received {displacements.shape}."
        )

    if not np.all(np.isfinite(displacements)):
        raise ValueError(
            "Displacement data contains invalid values."
        )

    components = {
        "x": (0, "Displacement X"),
        "y": (1, "Displacement Y"),
        "z": (2, "Displacement Z"),
    }

    if component == "magnitude":
        values = np.linalg.norm(
            displacements, axis=1
        )
        title = "Displacement Magnitude"

    elif component in components:
        index, title = components[component]
        values = displacements[:, index]

    else:
        raise ValueError(
            "component must be magnitude, x, y or z."
        )

    contour_grid = grid.copy(deep=True)

    contour_grid.point_data[
        "displacement_values"
    ] = values

    actor = plotter.add_mesh(
        contour_grid,
        scalars="displacement_values",
        cmap="jet",
        show_edges=False,
        scalar_bar_args={
            "title": f"{title} (m)",
            "vertical": True,
            "title_font_size": 16,
            "label_font_size": 12,
        },
    )

    return actor


def enable_element_selection(plotter, grid, on_element_selected=None):

    selected = {
        "actor": None,
        "grid": None,
        "element_id": None,
    }

    def handle_selection(picked_mesh):
        print("PICKING CALLBACK ACTIVATED", flush=True)

        if picked_mesh is None or picked_mesh.n_cells != 1:
            return

        if "original_cell_id" not in picked_mesh.cell_data:
            print("Original cell ID not found.", flush=True)
            return

        cell_id = int(picked_mesh.cell_data["original_cell_id"][0])

        print("Cells received:", picked_mesh.n_cells, flush=True)

        if not (0 <= cell_id < grid.n_cells):
            return

        element_id = cell_id + 1

        # Ignore repeated clicks on the same element.
        if selected["element_id"] == element_id:
            return

        # Extract only the selected element.
        selected_grid = grid.extract_cells([cell_id])

        # Create the highlight actor only once.
        if selected["actor"] is None:

            selected["grid"] = selected_grid

            selected["actor"] = plotter.add_mesh(
                selected["grid"],
                color="yellow",
                show_edges=True,
                edge_color="black",
                line_width=2,
                pickable=False,
                reset_camera=False,
                name="selected_element",
            )

        else:
            # Update the existing highlight actor.
            selected["grid"].shallow_copy(selected_grid)

        selected["element_id"] = element_id

        print(f"Selected element ID: {element_id}", flush=True)

        if on_element_selected is not None:
            on_element_selected(element_id)

        plotter.render()

    print("Element picker enabled", flush=True)
    plotter.enable_element_picking(
        callback=handle_selection,
        mode="cell",
        picker="cell",
        left_clicking=True,
        show=False,
        show_message=False,
    )