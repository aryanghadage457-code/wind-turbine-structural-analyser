"""
Mohr's circles for one selected 3D stress state.

Input order: [sigma_xx, sigma_yy, sigma_zz, tau_xy, tau_xz, tau_yz].
Shear entries are tensor stress components. The module reads an already-computed
stress vector; it does not run FEA or recalculate the stress field.
"""

from __future__ import annotations

import numpy as np


def stress_vector_to_tensor(stress):
    """Convert one six-component stress vector into a symmetric 3x3 tensor."""
    s = np.asarray(stress, dtype=float)
    if s.shape != (6,):
        raise ValueError("Expected 6 components in order (xx, yy, zz, xy, xz, yz).")
    if not np.all(np.isfinite(s)):
        raise ValueError("Stress components must all be finite.")

    sxx, syy, szz, txy, txz, tyz = s
    return np.array([
        [sxx, txy, txz],
        [txy, syy, tyz],
        [txz, tyz, szz],
    ], dtype=float)


def calculate_mohr_circles(stress, n_points=181):
    """
    Calculate all three Mohr circles for one 3D stress state.

    Returns principal stresses (sigma1 >= sigma2 >= sigma3), circle centres,
    radii and plotting coordinates. Output stress units match the input.
    """
    if isinstance(n_points, bool) or not isinstance(n_points, (int, np.integer)):
        raise TypeError("n_points must be an integer.")
    if n_points < 2:
        raise ValueError("n_points must be at least 2.")

    tensor = stress_vector_to_tensor(stress)
    principal = np.linalg.eigvalsh(tensor)[::-1]
    sigma1, sigma2, sigma3 = map(float, principal)

    angles = np.linspace(0.0, np.pi, n_points)
    pairs = (
        ("sigma1_sigma2", sigma1, sigma2),
        ("sigma2_sigma3", sigma2, sigma3),
        ("sigma1_sigma3", sigma1, sigma3),
    )

    circles = {}
    for name, sa, sb in pairs:
        center = 0.5 * (sa + sb)
        radius = 0.5 * abs(sa - sb)
        x = center + radius * np.cos(angles)
        y = radius * np.sin(angles)
        circles[name] = {
            "principal_pair": (sa, sb),
            "center": float(center),
            "radius": float(radius),
            "sigma": x,
            "tau": y,
            "tau_negative": -y,
        }

    return {
        "principal_stresses": principal,
        "sigma1": sigma1,
        "sigma2": sigma2,
        "sigma3": sigma3,
        "maximum_shear_stress": 0.5 * (sigma1 - sigma3),
        "circles": circles,
        "stress_tensor": tensor,
    }


def calculate_mohr_circles_from_results(results, element_index, surface="outer", n_points=181):
    """
    Read one element's stress row from the NPZ results and calculate its circles.

    element_index is zero-based (mesh/result row); returned element_id is 1-based.
    `results` can be a dict or the NpzFile returned by np.load().
    """
    if surface not in ("outer", "inner"):
        raise ValueError("surface must be 'outer' or 'inner'.")
    if isinstance(element_index, bool) or not isinstance(element_index, (int, np.integer)):
        raise TypeError("element_index must be an integer.")
    if element_index < 0:
        raise IndexError("element_index cannot be negative.")

    key = f"{surface}_stress"
    if key not in results:
        raise KeyError(f"'{key}' is missing from the supplied results.")
    stress_array = np.asarray(results[key], dtype=float)
    if stress_array.ndim != 2 or stress_array.shape[1] != 6:
        raise ValueError(f"'{key}' must have shape (number_of_elements, 6).")
    if element_index >= stress_array.shape[0]:
        raise IndexError(f"element_index {element_index} is outside the available range.")

    output = calculate_mohr_circles(stress_array[element_index], n_points)
    output.update({
        "element_index": int(element_index),
        "element_id": int(element_index + 1),
        "surface": surface,
    })
    return output
