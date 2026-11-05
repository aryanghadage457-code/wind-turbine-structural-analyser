"""
Prepare all precomputed results for one selected turbine element.

This module is a presentation/data-access layer:
- it reads values already calculated by StressAndStrain.py;
- it identifies the mesh element and component/group;
- it attaches Mohr-circle data from visualization.mohr_circle;
- it does not rerun FEA or recalculate stress/strain quantities.

NPZ keys use the convention: outer_stress, outer_principal, inner_strain, etc.
Element index is zero-based; CalculiX element ID = element index + 1.
"""

from __future__ import annotations

import numpy as np

from contracts import STRESS_ORDER
from visualization.mohr_circle import calculate_mohr_circles_from_results


STRESS_UNITS = "Pa"
STRAIN_UNITS = "m/m"

# Engineering shear array order from StressAndStrain.py
ENGINEERING_SHEAR_ORDER = ("xy", "xz", "yz")


def _get_row(results, key, element_index, expected_width=None):
    """Fetch one element row and validate its shape and values."""
    if key not in results:
        return None

    array = np.asarray(results[key], dtype=float)
    if array.ndim == 1:
        if expected_width is not None:
            raise ValueError(f"{key} should have shape (E, {expected_width}), got {array.shape}")
    elif array.ndim == 2:
        if expected_width is not None and array.shape[1] != expected_width:
            raise ValueError(f"{key} should have {expected_width} columns, got {array.shape}")
    else:
        raise ValueError(f"{key} should be a 1D or 2D per-element array, got {array.shape}")

    if element_index >= array.shape[0]:
        raise IndexError(
            f"Element index {element_index} is outside {key}'s range "
            f"0..{array.shape[0] - 1}"
        )

    row = np.asarray(array[element_index], dtype=float)
    if not np.all(np.isfinite(row)):
        raise ValueError(f"{key}[{element_index}] contains NaN or infinity")
    return row


def _require_row(results, key, element_index, expected_width=None):
    row = _get_row(results, key, element_index, expected_width)
    if row is None:
        raise KeyError(f"Required results array '{key}' is missing from the NPZ data")
    return row


def get_element_details(results, mesh, element_index, surface="outer"):
    """
    Build a dictionary of details for one selected element.

    Parameters
    ----------
    results:
        Dict made from np.load("out/stress_strain_results.npz"), or an NpzFile.
        Keep the NPZ file open while calling this function.
    mesh:
        contracts.Mesh loaded from out/full_mesh.pkl.
    element_index:
        Zero-based index passed by the PyVista cell-selection callback.
    surface:
        "outer" or "inner".

    Returns
    -------
    dict:
        Identity, group, centroid, stress/strain components, derived results,
        and three Mohr circles. Stress values remain in Pa; strain is dimensionless.
    """
    if surface not in ("outer", "inner"):
        raise ValueError("surface must be 'outer' or 'inner'")
    if isinstance(element_index, bool) or not isinstance(element_index, (int, np.integer)):
        raise TypeError("element_index must be an integer")
    if element_index < 0:
        raise IndexError("element_index cannot be negative")
    if element_index >= mesh.n_elems:
        raise IndexError(
            f"Element index {element_index} is outside the mesh range 0..{mesh.n_elems - 1}"
        )

    prefix = f"{surface}_"
    stress = _require_row(results, prefix + "stress", element_index, 6)
    principal_stress = _require_row(results, prefix + "principal", element_index, 3)
    strain = _require_row(results, prefix + "strain", element_index, 6)
    engineering_shear = _require_row(results, prefix + "engineering_shear", element_index, 3)
    principal_strain = _require_row(results, prefix + "principal_strain", element_index, 3)

    group_index = int(mesh.elem_group[element_index])
    if group_index < 0 or group_index >= len(mesh.group_names):
        raise ValueError(f"Invalid group index {group_index} for element {element_index}")
    group_name = str(mesh.group_names[group_index])

    node_indices = np.asarray(mesh.elems[element_index], dtype=int)
    centroid = np.mean(mesh.nodes[node_indices], axis=0)

    # The order below is exactly contracts.STRESS_ORDER:
    # xx, yy, zz, xy, xz, yz.
    stress_components = {
        name: float(value) for name, value in zip(STRESS_ORDER, stress)
    }
    strain_components = {
        name: float(value) for name, value in zip(STRESS_ORDER, strain)
    }
    engineering_shear_components = {
        name: float(value)
        for name, value in zip(ENGINEERING_SHEAR_ORDER, engineering_shear)
    }

    # Values are read from existing NPZ arrays, not recalculated here.
    von_mises = float(_require_row(results, prefix + "von_mises", element_index))
    max_shear_stress = float(_require_row(results, prefix + "max_shear", element_index))
    equivalent_strain = float(_require_row(results, prefix + "equivalent_strain", element_index))
    max_shear_strain = float(_require_row(results, prefix + "max_shear_strain", element_index))

    # Mohr circles use the same stored six-component stress row.
    mohr = calculate_mohr_circles_from_results(
        results, element_index, surface=surface
    )

    return {
        "element_index": int(element_index),       # zero-based mesh row
        "element_id": int(element_index + 1),      # CalculiX ID convention
        "surface": surface,
        "group_index": group_index,
        "group_name": group_name,
        "centroid_m": centroid,
        "stress_units": STRESS_UNITS,
        "strain_units": STRAIN_UNITS,
        "stress_axes": "element-local shell axes (axis 3 = element normal)",
        "outer_surface_convention": "outer = +normal side; inner = opposite side",
        "stress": {
            "components": stress_components,
            "principal": {
                "sigma1": float(principal_stress[0]),
                "sigma2": float(principal_stress[1]),
                "sigma3": float(principal_stress[2]),
            },
            "von_mises": von_mises,
            "maximum_shear": max_shear_stress,
        },
        "strain": {
            "tensorial_components": strain_components,
            "engineering_shear": engineering_shear_components,
            "principal": {
                "epsilon1": float(principal_strain[0]),
                "epsilon2": float(principal_strain[1]),
                "epsilon3": float(principal_strain[2]),
            },
            "equivalent": equivalent_strain,
            "maximum_shear": max_shear_strain,
        },
        "mohr": mohr,
    }
