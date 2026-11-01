"""
synthetic_wind_data.py - SYNTHETIC TEST DATA for the wind case (Member 3).

!!! THIS IS NOT A WIND SIMULATION. The numbers are invented, deterministic patterns that exist only so
!!! the mathematics of StressAndStrain.py can be verified before Member 2's wind solver is finished.
!!! They must never be reported as physical wind-turbine stresses.

The generated object is a genuine contracts.SolveResult (case "W", nonzero v_ref = 10 m/s by default) with
 * the same number of elements and nodes as the gravity result passed in (nothing is hard-coded),
 * the same component order (xx, yy, zz, xy, xz, yz) and the same inner/outer convention,
 * all six components nonzero on every element,
 * DIFFERENT, uncorrelated patterns on the outer and inner surface (so mixing the two up is detectable).
It carries the attribute `data_label` = "SYNTHETIC TEST DATA - NOT PHYSICAL", which StressAndStrain copies
into its report and notes.

Run `python synthetic_wind_data.py` to write test_data/res_W_SYNTHETIC_TEST_DATA.pkl. The real result in
out/res_G.pkl is only read, never modified.
"""
import os
import pickle

import numpy as np

from contracts import STRESS_ORDER, SolveResult

SYNTHETIC_LABEL = "SYNTHETIC TEST DATA - NOT PHYSICAL"

# amplitudes in Pa for (xx, yy, zz, xy, xz, yz) - chosen to look shell-like (small zz, small transverse shear)
_AMP_OUTER = np.array([20e6, -12e6, 1.0e6, 6e6, 0.8e6, -0.5e6])
_AMP_INNER = np.array([-7e6, 15e6, -0.6e6, -4e6, -0.3e6, 0.9e6])


def _pattern(n_elems: int, amp: np.ndarray, phase: float) -> np.ndarray:
    """Deterministic (n_elems, 6) pattern: amp_k * (1 + 0.5 sin(0.013 e + k + phase)); never exactly zero."""
    e = np.arange(n_elems, dtype=float)[:, None]
    k = np.arange(6, dtype=float)[None, :]
    return amp[None, :] * (1.0 + 0.5 * np.sin(0.013 * e + k + phase))


def make_synthetic_wind_result(gravity_result: SolveResult, v_ref: float = 10.0) -> SolveResult:
    """Synthetic wind SolveResult with the same layout as `gravity_result` (see module docstring)."""
    if not v_ref > 0:
        raise ValueError("v_ref must be positive")
    n_e = gravity_result.stress_outer.shape[0]
    has_inner = gravity_result.stress_inner is not None
    w = SolveResult(
        case="W",
        stress_outer=_pattern(n_e, _AMP_OUTER, 0.0),
        stress_inner=_pattern(n_e, _AMP_INNER, 2.0) if has_inner else None,
        displacements=np.zeros_like(gravity_result.displacements),   # not meaningful for synthetic data
        base_reaction_force=np.zeros(3), base_reaction_moment=np.zeros(3), applied_force=np.zeros(3),
        v_ref=float(v_ref))
    w.data_label = SYNTHETIC_LABEL
    return w


def is_synthetic(result) -> bool:
    return getattr(result, "data_label", None) == SYNTHETIC_LABEL


if __name__ == "__main__":
    with open("out/res_G.pkl", "rb") as fh:
        g = pickle.load(fh)
    w = make_synthetic_wind_result(g)
    os.makedirs("test_data", exist_ok=True)
    path = "test_data/res_W_SYNTHETIC_TEST_DATA.pkl"
    with open(path, "wb") as fh:
        pickle.dump(w, fh)
    print(f"wrote {path}  ({w.stress_outer.shape[0]} elements, v_ref = {w.v_ref} m/s)  [{SYNTHETIC_LABEL}]")
    print("stress order:", STRESS_ORDER)