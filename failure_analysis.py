"""Failure screening for combined gravity + wind shell-stress results.

What this module does
---------------------
The FEA model is linear and the wind load scales with V^2, so the stress in every
element and on each shell surface is

    sigma(V) = sigma_G + s * sigma_W_ref ,      s = (V / V_ref)^2 .

That makes the von Mises stress of each element an exact quadratic in s,

    vm^2(s) = a + b*s + c*s^2 ,   a = q(G,G),  b = 2 q(G,W),  c = q(W,W),

where q is the von Mises quadratic form.  The wind speed at which any element
reaches a stress limit is therefore found in closed form (no sampling, no search).
On top of the single-point check at the operating speed this gives:

  * V_fail   - lowest wind speed at which any element reaches first yield (SF = 1),
  * V_allow  - lowest wind speed at which any element reaches yield / safety_factor,
  * the governing element, surface, component group and location,
  * a per-component-group breakdown and a ranked list of critical elements,
  * the utilisation-versus-wind-speed curve,
  * an optional shell-buckling screening of the tower (classical axial-compression
    elastic critical stress reduced by a knock-down factor).

Scope / honesty
---------------
This is a SCREENING tool.  Yield uses one user-selected yield strength (not per
element).  The buckling check is the classical cylinder formula with a placeholder
knock-down factor, applied to the tower groups only - it is not an EN 1993-1-6
assessment.  No fatigue, fracture, composite or design-code checks.

The module has no GUI / plotting dependency so the command line workflow, the
tests and the PySide6 interface all share exactly the same code.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

SCHEMA_VERSION = 2
CLASSICAL_AXIAL_BUCKLING_COEFF = 0.605      # sigma_cr = 0.605 * E * t / R  (perfect cylinder, axial compression)

# von Mises quadratic form for (xx, yy, zz, xy, xz, yz) with TENSORIAL shear:
#   vm^2 = xx^2+yy^2+zz^2 - xx*yy - yy*zz - zz*xx + 3*(xy^2+xz^2+yz^2)
_Q = np.array([[1.0, -0.5, -0.5, 0, 0, 0],
               [-0.5, 1.0, -0.5, 0, 0, 0],
               [-0.5, -0.5, 1.0, 0, 0, 0],
               [0, 0, 0, 3.0, 0, 0],
               [0, 0, 0, 0, 3.0, 0],
               [0, 0, 0, 0, 0, 3.0]])

LIMITATIONS = [
    "Uniform yield strength is an explicit screening input, not recovered per element from the current .inp.",
    "No fatigue, fracture, composite failure, or design-code checks are included.",
    "Stress superposition assumes linear response and wind load proportional to V^2 (single wind direction).",
]
BUCKLING_LIMITATIONS = [
    "Buckling screening uses the classical perfect-cylinder axial formula sigma_cr = 0.605*E*t/R with a "
    "knock-down factor; the default knock-down (0.2) is a project placeholder, not an EN 1993-1-6 value.",
    "Only the Tower_* groups are checked. The most compressive principal membrane stress (mean of outer and "
    "inner surface) is used as the compression: conservative and independent of local shell axes. Local peaks "
    "at the clamped base are boundary effects and are not buckling-relevant.",
    "External wind pressure, ring stiffeners and geometric imperfections are not modelled.",
]


# ----------------------------------------------------------------------------------------------------------
# Pure numeric helpers
# ----------------------------------------------------------------------------------------------------------
def _quad(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Bilinear von Mises form  x^T Q y  for (E,6) arrays -> (E,)."""
    return np.einsum("ei,ij,ej->e", x, _Q, y)


def von_mises(s6: np.ndarray) -> np.ndarray:
    """Von Mises stress of (E,6) stress rows (STRESS_ORDER, tensorial shear)."""
    s6 = np.asarray(s6, float)
    return np.sqrt(np.maximum(_quad(s6, s6), 0.0))


def vm_coefficients(gravity: np.ndarray, wind_ref: np.ndarray):
    """(a, b, c) with vm^2(s) = a + b*s + c*s^2 for every element."""
    return _quad(gravity, gravity), 2.0 * _quad(gravity, wind_ref), _quad(wind_ref, wind_ref)


def vm_at_scale(a, b, c, s):
    """Von Mises stress at wind scale s. Broadcasts: a,b,c (E,) with s scalar or (S,1)."""
    return np.sqrt(np.maximum(a + b * s + c * s * s, 0.0))


def scale_at_limit(a, b, c, limit: float) -> np.ndarray:
    """Smallest s >= 0 with vm(s) = limit, per element. 0 if already at/above the limit, inf if never reached.

    vm^2 is a convex quadratic in s that is >= 0, so for a < limit^2 there is exactly one positive root of
    c*s^2 + b*s - d = 0 with d = limit^2 - a > 0; it is evaluated as 2d / (b + sqrt(b^2 + 4cd)), which is
    numerically stable for tiny c and for b < 0.
    """
    a, b, c = (np.asarray(x, float) for x in (a, b, c))
    d = limit * limit - a
    out = np.full(a.shape, np.inf)
    out[d <= 0.0] = 0.0
    pos = d > 0.0
    den = b[pos] + np.sqrt(b[pos] ** 2 + 4.0 * c[pos] * d[pos])
    with np.errstate(divide="ignore", invalid="ignore"):
        root = np.where(den > 0.0, 2.0 * d[pos] / den, np.inf)
    out[pos] = root
    return out


def _speed_from_scale(s, v_ref: float):
    s = np.asarray(s, float)
    return np.where(np.isfinite(s), v_ref * np.sqrt(np.maximum(s, 0.0)), np.inf)


def _finite_or_none(x):
    x = float(x)
    return x if math.isfinite(x) else None


def _min_eig(t6: np.ndarray) -> np.ndarray:
    """Smallest eigenvalue (most compressive principal stress) of (E,6) stress rows."""
    t = np.empty((t6.shape[0], 3, 3))
    t[:, 0, 0], t[:, 1, 1], t[:, 2, 2] = t6[:, 0], t6[:, 1], t6[:, 2]
    t[:, 0, 1] = t[:, 1, 0] = t6[:, 3]
    t[:, 0, 2] = t[:, 2, 0] = t6[:, 4]
    t[:, 1, 2] = t[:, 2, 1] = t6[:, 5]
    return np.linalg.eigvalsh(t)[:, 0]


def _compression_scale_at_limit(g6: np.ndarray, w6: np.ndarray, limit: np.ndarray) -> np.ndarray:
    """Smallest s>=0 where -lambda_min(g + s*w) = limit (per element).

    -lambda_min of an affine matrix family is convex in s, so once it is above the level it stays above:
    a bracket plus bisection finds the single crossing. 0 if already above, inf if never reached.
    """
    out = np.full(g6.shape[0], np.inf)
    already = -_min_eig(g6) >= limit
    out[already] = 0.0
    todo = ~already
    if not todo.any():
        return out
    gi, wi, li = g6[todo], w6[todo], limit[todo]
    hi = np.ones(len(gi))
    reached = np.zeros(len(gi), bool)
    for _ in range(40):                                    # grow the bracket up to 2**40
        reached = (-_min_eig(gi + hi[:, None] * wi)) >= li
        if reached.all():
            break
        hi = np.where(reached, hi, hi * 2.0)
    lo = np.zeros(len(gi))
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        up = (-_min_eig(gi + mid[:, None] * wi)) >= li
        hi = np.where(up, mid, hi)
        lo = np.where(up, lo, mid)
    out[todo] = np.where(reached, hi, np.inf)
    return out


# ----------------------------------------------------------------------------------------------------------
# Core assessment on stress fields
# ----------------------------------------------------------------------------------------------------------
def _as_surfaces(d, name):
    out = {}
    for surf in ("outer", "inner"):
        arr = None if d is None else d.get(surf)
        if arr is None:
            continue
        arr = np.asarray(arr, float)
        if arr.ndim != 2 or arr.shape[1] != 6 or not np.isfinite(arr).all():
            raise ValueError(f"{name}[{surf!r}] must be a finite (E, 6) array")
        out[surf] = arr
    if "outer" not in out:
        raise ValueError(f"{name} needs at least the 'outer' surface")
    return out


def assess_stress_fields(*, gravity, wind_ref, v_ref, v_operating, yield_strength_pa=345e6, safety_factor=1.5,
                         mesh=None, group_thickness=None, young_modulus_pa=210e9, buckling_knockdown=0.2,
                         enable_buckling=True, top_n=20, n_curve_points=101, wind_reference_loads=None,
                         metadata=None):
    """Full failure screening from gravity and reference-wind stress arrays.

    gravity, wind_ref : {"outer": (E,6), "inner": (E,6) or None} in Pa. wind_ref is the UNSCALED stress of the
                        reference-wind solve (speed v_ref).
    wind_reference_loads : optional {"applied_force": (3,), "base_moment": (3,)} of the reference-wind solve,
                        used to report the loads at failure.
    mesh               : optional contracts.Mesh; enables groups, locations and the buckling check.
    group_thickness    : optional {group_name: shell thickness [m]}, needed for buckling.

    Returns (result_dict [JSON-serialisable], fields_dict [per-element numpy arrays]).
    """
    if not (np.isfinite(yield_strength_pa) and yield_strength_pa > 0):
        raise ValueError("yield_strength_pa must be finite and positive")
    if not (np.isfinite(safety_factor) and safety_factor >= 1):
        raise ValueError("safety_factor must be finite and >= 1")
    if not (np.isfinite(v_ref) and v_ref > 0):
        raise ValueError("v_ref must be finite and positive")
    if not (np.isfinite(v_operating) and v_operating >= 0):
        raise ValueError("v_operating must be finite and >= 0")
    if not (np.isfinite(buckling_knockdown) and 0 < buckling_knockdown <= 1):
        raise ValueError("buckling_knockdown must be in (0, 1]")

    g_s, w_s = _as_surfaces(gravity, "gravity"), _as_surfaces(wind_ref, "wind_ref")
    surfaces = [s for s in ("outer", "inner") if s in g_s and s in w_s]
    n_el = g_s["outer"].shape[0]
    for s in surfaces:
        if g_s[s].shape != w_s[s].shape or g_s[s].shape[0] != n_el:
            raise ValueError("gravity and wind stress arrays must have identical shapes")
    if mesh is not None and mesh.n_elems != n_el:
        raise ValueError(f"mesh has {mesh.n_elems} elements but stress arrays have {n_el}")

    allowable = yield_strength_pa / safety_factor
    s_op = (v_operating / v_ref) ** 2
    coeff = {s: vm_coefficients(g_s[s], w_s[s]) for s in surfaces}

    # --- single point at the operating speed ---------------------------------------------------------------
    vm_surf = np.stack([vm_at_scale(*coeff[s], s_op) for s in surfaces])          # (S, E)
    vm_el = vm_surf.max(axis=0)
    surf_of_el = vm_surf.argmax(axis=0)
    gov = int(np.argmax(vm_el))
    vm_max = float(vm_el[gov])
    utilisation = vm_max / allowable
    vm_grav = np.stack([np.sqrt(np.maximum(coeff[s][0], 0.0)) for s in surfaces]).max(axis=0)

    # --- closed-form limit speeds per element --------------------------------------------------------------
    s_yield_surf = np.stack([scale_at_limit(*coeff[s], yield_strength_pa) for s in surfaces])
    s_allow = np.stack([scale_at_limit(*coeff[s], allowable) for s in surfaces]).min(axis=0)
    s_yield = s_yield_surf.min(axis=0)
    v_yield_el = _speed_from_scale(s_yield, v_ref)
    v_allow_el = _speed_from_scale(s_allow, v_ref)
    i_fail, i_allow = int(np.argmin(s_yield)), int(np.argmin(s_allow))
    v_fail, v_allow = float(v_yield_el[i_fail]), float(v_allow_el[i_allow])
    fail_surface = surfaces[int(np.argmin(s_yield_surf[:, i_fail]))]

    mesh_ok = mesh is not None
    centroids = np.mean(np.asarray(mesh.nodes)[np.asarray(mesh.elems)], axis=1) if mesh_ok else None
    group_names = [str(n) for n in mesh.group_names] if mesh_ok else None
    groups_idx = np.asarray(mesh.elem_group) if mesh_ok else None

    def group_of(i):
        return group_names[int(groups_idx[i])] if mesh_ok else None

    def loc_of(i):
        return [float(v) for v in centroids[i]] if mesh_ok else None

    finite_fail = math.isfinite(v_fail)
    result = {
        "schema_version": SCHEMA_VERSION,
        "method": "elastic von-Mises yield screening",
        "yield_strength_pa": float(yield_strength_pa),
        "safety_factor": float(safety_factor),
        "allowable_stress_pa": float(allowable),
        "operating_wind_speed_m_s": float(v_operating),
        "reference_wind_speed_m_s": float(v_ref),
        "maximum_von_mises_pa": vm_max,
        "utilization": float(utilisation),
        "reserve_factor": float(allowable / vm_max) if vm_max > 0 else None,
        "governing_element_index_0_based": gov,
        "governing_calculix_element_id_1_based": gov + 1,
        "governing_surface": surfaces[int(surf_of_el[gov])],
        "governing_group": group_of(gov),
        "governing_location_m": loc_of(gov),
        "status": "EXCEEDS_ALLOWABLE" if utilisation > 1 else "WITHIN_ALLOWABLE",
        "gravity_only": {"maximum_von_mises_pa": float(vm_grav.max()),
                         "utilization": float(vm_grav.max() / allowable),
                         "governing_element_index_0_based": int(np.argmax(vm_grav))},
        "failure_speed": {
            "v_fail_m_s": _finite_or_none(v_fail),
            "v_allow_m_s": _finite_or_none(v_allow),
            "operating_margin_to_allowable_m_s": _finite_or_none(v_allow - v_operating),
            "governing_element_index_0_based": i_fail if finite_fail else None,
            "governing_calculix_element_id_1_based": i_fail + 1 if finite_fail else None,
            "governing_surface": fail_surface if finite_fail else None,
            "governing_group": group_of(i_fail) if finite_fail else None,
            "governing_location_m": loc_of(i_fail) if finite_fail else None,
            "allowable_governing_element_index_0_based": i_allow if math.isfinite(v_allow) else None,
            "allowable_governing_group": group_of(i_allow) if math.isfinite(v_allow) else None,
            "message": _failure_message(v_fail, v_allow, v_operating,
                                        s_yield[i_fail] == 0.0, s_allow[i_allow] == 0.0),
        },
        "metadata": dict(metadata or {}),
        "limitations": list(LIMITATIONS),
    }

    # --- loads at failure ----------------------------------------------------------------------------------
    if wind_reference_loads and finite_fail:
        k = (v_fail / v_ref) ** 2
        force = np.asarray(wind_reference_loads.get("applied_force", np.zeros(3)), float)
        moment = np.asarray(wind_reference_loads.get("base_moment", np.zeros(3)), float)
        result["failure_speed"]["wind_force_at_failure_n"] = [float(x) for x in k * force]
        result["failure_speed"]["wind_base_moment_at_failure_nm"] = [float(x) for x in k * moment]

    # --- per-group table -----------------------------------------------------------------------------------
    result["groups"] = []
    if mesh_ok:
        for gi, name in enumerate(group_names):
            mask = groups_idx == gi
            if not mask.any():
                continue
            ids = np.flatnonzero(mask)
            loc = int(ids[np.argmax(vm_el[mask])])
            result["groups"].append({
                "group": name, "n_elements": int(mask.sum()),
                "maximum_von_mises_pa": float(vm_el[loc]), "utilization": float(vm_el[loc] / allowable),
                "governing_element_index_0_based": loc,
                "governing_calculix_element_id_1_based": loc + 1,
                "governing_surface": surfaces[int(surf_of_el[loc])],
                "v_fail_m_s": _finite_or_none(v_yield_el[mask].min()),
                "v_allow_m_s": _finite_or_none(v_allow_el[mask].min()),
                "status": "EXCEEDS_ALLOWABLE" if vm_el[loc] / allowable > 1 else "WITHIN_ALLOWABLE",
                "thickness_m": (float(group_thickness[name]) if group_thickness and name in group_thickness
                                else None),
            })

    # --- ranked critical elements --------------------------------------------------------------------------
    order = np.argsort(-vm_el, kind="stable")[:int(max(0, min(top_n, n_el)))]
    result["top_elements"] = [{
        "rank": r + 1, "element_index_0_based": int(i), "calculix_element_id_1_based": int(i) + 1,
        "group": group_of(int(i)), "surface": surfaces[int(surf_of_el[i])],
        "von_mises_pa": float(vm_el[i]), "utilization": float(vm_el[i] / allowable),
        "v_fail_m_s": _finite_or_none(v_yield_el[i]), "location_m": loc_of(int(i)),
    } for r, i in enumerate(order)]

    fields = {"utilisation_von_mises": vm_el / allowable, "von_mises_pa": vm_el,
              "failure_speed_m_s": v_yield_el, "allowable_speed_m_s": v_allow_el,
              "von_mises_gravity_only_pa": vm_grav}

    # --- buckling screening --------------------------------------------------------------------------------
    buck = _buckling(g_s, w_s, surfaces, mesh, group_thickness, young_modulus_pa, buckling_knockdown,
                     safety_factor, v_ref, v_operating, enable_buckling, centroids, group_names, groups_idx)
    result["buckling"] = buck["summary"]
    performed = bool(buck["summary"].get("performed"))
    if performed:
        fields["buckling_utilisation"] = buck["util_el"]
        result["limitations"] += BUCKLING_LIMITATIONS

    # --- utilisation curve ---------------------------------------------------------------------------------
    cands = [1.25 * v_operating, 10.0]
    for v in (v_fail, (buck["summary"].get("v_fail_m_s") if performed else None) or math.inf):
        if math.isfinite(v):
            cands.append(1.3 * v)
    if len(cands) == 2:
        cands.append(1.5 * v_ref)
    v_axis = np.linspace(0.0, math.ceil(max(cands) / 5.0) * 5.0, int(max(11, n_curve_points)))
    s_axis = (v_axis / v_ref) ** 2
    vm_curve = np.stack([vm_at_scale(*coeff[s], s_axis[:, None]).max(axis=1) for s in surfaces]).max(axis=0)
    result["curve"] = {
        "wind_speed_m_s": [float(x) for x in v_axis],
        "max_von_mises_pa": [float(x) for x in vm_curve],
        "utilization": [float(x) for x in vm_curve / allowable],
        "buckling_utilization": [float(x) for x in buck["curve_fn"](s_axis)] if performed else None,
    }
    return result, fields


def _failure_message(v_fail, v_allow, v_op, fails_at_zero, allow_at_zero):
    if fails_at_zero:
        return "First yield is reached under gravity alone (V_fail = 0 m/s)."
    if not math.isfinite(v_fail):
        return "No element reaches yield at any wind speed (the wind load does not raise the stress)."
    if allow_at_zero:
        return "The allowable stress (yield / safety factor) is exceeded under gravity alone."
    state = "above" if v_op > v_allow else "below"
    return (f"First yield at {v_fail:.1f} m/s; allowable stress reached at {v_allow:.1f} m/s. "
            f"The operating speed ({v_op:.1f} m/s) is {state} the allowable wind speed.")


def _buckling(g_s, w_s, surfaces, mesh, thickness, E, kappa, sf, v_ref, v_op, enabled,
              centroids, group_names, groups_idx):
    def skip(why):
        return {"summary": {"performed": False, "reason": why}, "util_el": None, "curve_fn": None}

    if not enabled:
        return skip("disabled")
    if mesh is None:
        return skip("no mesh supplied")
    if not thickness:
        return skip("no shell thicknesses supplied")
    tower_ids = [i for i, n in enumerate(group_names) if n.startswith("Tower_") and n in thickness]
    if not tower_ids:
        return skip("no Tower_* group with a known thickness")
    idx = np.flatnonzero(np.isin(groups_idx, tower_ids))
    if idx.size == 0:
        return skip("tower groups contain no elements")
    t = np.array([float(thickness[group_names[int(groups_idx[i])]]) for i in idx])
    r = np.hypot(centroids[idx, 0], centroids[idx, 1])
    if not (np.all(t > 0) and np.all(r > 0)):
        return skip("invalid thickness or radius on a tower element")

    sigma_cr = kappa * CLASSICAL_AXIAL_BUCKLING_COEFF * E * t / r      # design critical stress per element [Pa]
    limit_allow = sigma_cr / sf

    def membrane(d):                                                    # mean of the outer and inner surface
        return np.mean([d[s][idx] for s in surfaces], axis=0)

    gm, wm = membrane(g_s), membrane(w_s)
    comp_op = np.maximum(-_min_eig(gm + ((v_op / v_ref) ** 2) * wm), 0.0)      # tension -> 0
    util_t = comp_op / limit_allow                                      # > 1 -> exceeds allowable
    util_el = np.full(g_s["outer"].shape[0], np.nan)
    util_el[idx] = util_t
    k = int(np.argmax(util_t))
    ge = int(idx[k])

    s_fail = _compression_scale_at_limit(gm, wm, sigma_cr)              # SF = 1
    s_allow = _compression_scale_at_limit(gm, wm, limit_allow)
    v_fail = float(_speed_from_scale(s_fail.min(), v_ref))
    v_allow = float(_speed_from_scale(s_allow.min(), v_ref))

    def curve_fn(s_axis):
        return [float((np.maximum(-_min_eig(gm + s * wm), 0.0) / limit_allow).max()) for s in s_axis]

    groups = []
    for gi in tower_ids:
        gmask = groups_idx[idx] == gi
        if not gmask.any():
            continue
        kk = int(np.flatnonzero(gmask)[np.argmax(util_t[gmask])])
        groups.append({"group": group_names[gi], "thickness_m": float(thickness[group_names[gi]]),
                       "maximum_compression_pa": float(comp_op[kk]),
                       "critical_stress_pa": float(sigma_cr[kk]),
                       "utilization": float(util_t[kk]),
                       "governing_element_index_0_based": int(idx[kk]),
                       "v_fail_m_s": _finite_or_none(_speed_from_scale(s_fail[gmask].min(), v_ref)),
                       "v_allow_m_s": _finite_or_none(_speed_from_scale(s_allow[gmask].min(), v_ref))})
    summary = {
        "performed": True,
        "method": "classical axial-compression shell buckling screening (tower only)",
        "formula": "sigma_cr = knockdown * 0.605 * E * t / R",
        "young_modulus_pa": float(E), "knockdown": float(kappa), "safety_factor": float(sf),
        "maximum_compression_pa": float(comp_op[k]),
        "critical_stress_pa": float(sigma_cr[k]),
        "utilization": float(util_t[k]),
        "status": "EXCEEDS_ALLOWABLE" if util_t[k] > 1 else "WITHIN_ALLOWABLE",
        "governing_element_index_0_based": ge, "governing_calculix_element_id_1_based": ge + 1,
        "governing_group": group_names[int(groups_idx[ge])],
        "governing_location_m": [float(x) for x in centroids[ge]],
        "v_fail_m_s": _finite_or_none(v_fail), "v_allow_m_s": _finite_or_none(v_allow),
        "n_elements_checked": int(idx.size),
        "groups": groups,
    }
    return {"summary": summary, "util_el": util_el, "curve_fn": curve_fn}


# ----------------------------------------------------------------------------------------------------------
# Legacy single-point check (used when no separate gravity / wind stress arrays are available)
# ----------------------------------------------------------------------------------------------------------
def _assess_legacy(data, yield_strength_pa, safety_factor, metadata, reason):
    candidates = []
    for surface in ("outer", "inner"):
        key = f"{surface}_von_mises"
        if key in data.files:
            arr = np.asarray(data[key], dtype=float)
            if arr.ndim != 1 or not np.isfinite(arr).all():
                raise ValueError(f"{key} must be a finite 1-D element array")
            if arr.size:
                i = int(np.argmax(arr))
                candidates.append((float(arr[i]), i, surface))
    if not candidates:
        raise ValueError("No von Mises stress arrays found in stress/strain NPZ")
    stress, element_index, surface = max(candidates)
    utilization = stress / (yield_strength_pa / safety_factor)
    return {
        "schema_version": SCHEMA_VERSION,
        "method": "elastic von-Mises yield screening",
        "yield_strength_pa": float(yield_strength_pa), "safety_factor": float(safety_factor),
        "allowable_stress_pa": float(yield_strength_pa / safety_factor),
        "maximum_von_mises_pa": stress, "utilization": float(utilization),
        "governing_element_index_0_based": element_index,
        "governing_calculix_element_id_1_based": element_index + 1,
        "governing_surface": surface,
        "status": "EXCEEDS_ALLOWABLE" if utilization > 1 else "WITHIN_ALLOWABLE",
        "metadata": metadata,
        "limitations": list(LIMITATIONS[:1]) + [
            f"Single operating point only ({reason}): no failure wind speed, groups or utilisation curve."],
    }


# ----------------------------------------------------------------------------------------------------------
# File-level entry points
# ----------------------------------------------------------------------------------------------------------
def _json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"not JSON serialisable: {type(o)}")


def _split_stress(data, gravity_result, wind_result, v_op, v_ref):
    """Return (gravity, wind_ref, v_ref, reason). gravity is None when no split can be built."""
    if gravity_result is not None and wind_result is not None:
        if wind_result.v_ref is not None:
            v_ref = float(wind_result.v_ref)
        return ({"outer": gravity_result.stress_outer, "inner": gravity_result.stress_inner},
                {"outer": wind_result.stress_outer, "inner": wind_result.stress_inner}, v_ref, "")
    if "outer_stress_gravity" not in data.files or "outer_stress_wind_scaled" not in data.files:
        return None, None, v_ref, "NPZ has no separate gravity / wind stress arrays"
    scale = (v_op / v_ref) ** 2 if (np.isfinite(v_op) and np.isfinite(v_ref) and v_ref > 0) else 0.0
    if not scale > 0:
        return None, None, v_ref, "operating wind speed is 0 m/s and no reference-wind result was supplied"
    gravity, wind = {}, {}
    for surf in ("outer", "inner"):
        if f"{surf}_stress_gravity" in data.files:
            gravity[surf] = np.asarray(data[f"{surf}_stress_gravity"], float)
            wind[surf] = np.asarray(data[f"{surf}_stress_wind_scaled"], float) / scale
    return gravity, wind, v_ref, ""


def assess_npz(npz_path, *, yield_strength_pa=345e6, safety_factor=1.5, output_path=None,
               mesh=None, group_thickness=None, gravity_result=None, wind_result=None,
               young_modulus_pa=None, buckling_knockdown=0.2, enable_buckling=True,
               top_n=20, fields_path=None):
    """Assess the combined stress/strain NPZ written by StressAndStrain.py.

    Optional `gravity_result` / `wind_result` (contracts.SolveResult) supply the unscaled reference-wind stress;
    without them it is recovered from the NPZ (`*_stress_wind_scaled` / (V/V_ref)^2), which is impossible for an
    operating speed of exactly 0 m/s. If neither works the old single-point check is returned instead.
    Every key of the earlier version (status, utilization, governing_* ...) is kept.
    """
    if not np.isfinite(yield_strength_pa) or yield_strength_pa <= 0:
        raise ValueError("yield_strength_pa must be finite and positive")
    if not np.isfinite(safety_factor) or safety_factor < 1:
        raise ValueError("safety_factor must be finite and >= 1")
    fields = None
    with np.load(npz_path, allow_pickle=False) as data:
        metadata = json.loads(str(data["metadata_json"].item())) if "metadata_json" in data.files else {}
        v_op = float(data["wind_speed"]) if "wind_speed" in data.files else float(
            metadata.get("operating_wind_speed_m_s", np.nan))
        v_ref = float(data["v_ref"]) if "v_ref" in data.files else float(
            metadata.get("reference_wind_speed_m_s", np.nan))
        gravity, wind, v_ref, reason = _split_stress(data, gravity_result, wind_result, v_op, v_ref)
        if gravity is None:
            result = _assess_legacy(data, yield_strength_pa, safety_factor, metadata, reason)
        else:
            if young_modulus_pa is None:
                young_modulus_pa = float(metadata.get("material", {}).get("E_Pa", 210e9))
            loads = None
            if wind_result is not None:
                loads = {"applied_force": wind_result.applied_force,
                         "base_moment": wind_result.base_reaction_moment}
            result, fields = assess_stress_fields(
                gravity=gravity, wind_ref=wind, v_ref=v_ref, v_operating=v_op,
                yield_strength_pa=yield_strength_pa, safety_factor=safety_factor, mesh=mesh,
                group_thickness=group_thickness, young_modulus_pa=young_modulus_pa,
                buckling_knockdown=buckling_knockdown, enable_buckling=enable_buckling,
                top_n=top_n, wind_reference_loads=loads, metadata=metadata)
            _crosscheck_saved_vm(result, data)
    buckling = result.get("buckling") or {}
    result["overall_status"] = ("EXCEEDS_ALLOWABLE" if "EXCEEDS_ALLOWABLE" in (result["status"],
                                buckling.get("status")) else "WITHIN_ALLOWABLE")
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, default=_json_default), encoding="utf-8")
    if fields_path and fields:
        Path(fields_path).parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(fields_path, **fields)
    return result


def _crosscheck_saved_vm(result, data):
    """Flag in the result if the recomputed von Mises disagrees with the NPZ's own saved arrays."""
    saved = [float(np.max(data[k])) for k in ("outer_von_mises", "inner_von_mises") if k in data.files]
    if not saved:
        return
    saved, mine = max(saved), result["maximum_von_mises_pa"]
    if saved > 0 and abs(saved - mine) > 1e-6 * saved:
        result["limitations"].append(
            f"WARNING: recomputed max von Mises ({mine:.6g} Pa) differs from the saved NPZ value ({saved:.6g} Pa).")


def load_assessment(path):
    """Read a failure_assessment.json written by assess_npz."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def to_failure_result(result):
    """Convert the assessment dict to the frozen contracts.FailureResult dataclass."""
    from contracts import FailureResult
    fs = result.get("failure_speed") or {}
    loc = fs.get("governing_location_m")
    curve = result.get("curve") or {}
    return FailureResult(
        v_fail=fs.get("v_fail_m_s"), v_allow=fs.get("v_allow_m_s"),
        governing_element=fs.get("governing_element_index_0_based"),
        governing_surface=fs.get("governing_surface"),
        governing_location=None if loc is None else np.asarray(loc, float),
        governing_group=fs.get("governing_group"),
        force_at_failure=(np.asarray(fs["wind_force_at_failure_n"]) if "wind_force_at_failure_n" in fs else None),
        base_moment_at_failure=(np.asarray(fs["wind_base_moment_at_failure_nm"])
                                if "wind_base_moment_at_failure_nm" in fs else None),
        utilisation_curve=(np.asarray(curve.get("wind_speed_m_s", [])), np.asarray(curve.get("utilization", []))),
        message=fs.get("message", ""))


def format_report(result):
    """Human-readable multi-line summary (console and GUI log)."""
    mpa = 1e6
    lines = [
        f"Failure screening ({result['method']})",
        f"  Yield {result['yield_strength_pa'] / mpa:.0f} MPa, SF {result['safety_factor']:g} "
        f"-> allowable {result['allowable_stress_pa'] / mpa:.1f} MPa",
        f"  Max von Mises {result['maximum_von_mises_pa'] / mpa:.1f} MPa | utilisation {result['utilization']:.3f} "
        f"| {result['status']}",
        f"  Governing element {result['governing_calculix_element_id_1_based']} "
        f"({result.get('governing_group') or 'group n/a'}, {result['governing_surface']} surface)",
    ]
    fs = result.get("failure_speed")
    if fs:
        lines.append(f"  {fs['message']}")
    b = result.get("buckling")
    if b and b.get("performed"):
        lines.append(f"  Tower buckling screening: utilisation {b['utilization']:.3f} | {b['status']} | "
                     f"{b['governing_group']} element {b['governing_calculix_element_id_1_based']}")
    elif b:
        lines.append(f"  Tower buckling screening not performed ({b.get('reason')}).")
    lines.append(f"  Overall: {result.get('overall_status', result['status'])}")
    return "\n".join(lines)