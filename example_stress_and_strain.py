"""
example_stress_and_strain.py - how to use StressAndStrain.py.   Run from the repository root:

    python example_stress_and_strain.py

Example 1: ACTUAL gravity result (out/res_G.pkl) + zero wind, v = 0   -> gravity-only numbers.
Example 2: ACTUAL gravity result + SYNTHETIC wind (test data), v = 7 m/s -> exercises the wind path.
Example 3: what changes when Member 2's real wind result is ready (nothing in StressAndStrain.py).
Example 4: export EVERY element's stress and strain (outer + inner) to Excel (needs: pip install openpyxl).
"""
import numpy as np

import StressAndStrain as SS
from synthetic_wind_data import make_synthetic_wind_result

# ---- common inputs ------------------------------------------------------------------------------
gravity = SS.load_solve_result("out/res_G.pkl")                       # Member 2's actual SolveResult, case G
n = gravity.stress_outer.shape[0]
material = SS.MaterialProps.from_inp("out/G.inp", n)                  # per-element E, nu, thickness from the CalculiX input
mesh = SS.load_mesh("out/full_mesh.pkl")                              # optional: gives group names

# ---- Example 1: zero wind, v = 0 (same combined code path as always) ---------------------------------
zero_wind = SS.make_zero_wind_result(gravity)                         # zero stresses, same layout as gravity
res0 = SS.calculate_stress_and_strain(gravity, zero_wind, wind_speed=0.0, material=material, mesh=mesh)
print(res0.report())
assert np.array_equal(res0.outer.stress, gravity.stress_outer)        # total == gravity when v = 0

# ---- Example 2: synthetic nonzero wind (NOT physical; only verifies the maths) ----------------------
synthetic_wind = make_synthetic_wind_result(gravity, v_ref=10.0)      # labelled SYNTHETIC TEST DATA
res7 = SS.calculate_stress_and_strain(gravity, synthetic_wind, wind_speed=7.0, material=material, mesh=mesh)
print("\n\n" + res7.report())

# Per-element arrays (one row per element; rows = mesh element index; CalculiX id = row + 1)
o = res7.outer
e = res7.critical.element_index
print(f"\nElement {e}: outer total stress [Pa] (xx,yy,zz,xy,xz,yz) = {o.stress[e]}")
print(f"           principal stresses [Pa] = {o.principal[e]},  von Mises = {o.von_mises[e]:.4g} Pa")
print(f"           strain (tensorial) = {o.strain[e]},  engineering shear (gxy,gxz,gyz) = {o.engineering_shear[e]}")

# Strain model sensitivity (plane_stress is the default; full_3d also uses szz)
res7_3d = SS.calculate_stress_and_strain(gravity, synthetic_wind, 7.0, material, strain_model="full_3d", mesh=mesh)
print(f"\nmax equivalent strain: plane_stress {res7.extremes['equivalent_strain'].value:.5g}   "
      f"full_3d {res7_3d.extremes['equivalent_strain'].value:.5g}")

# ---- Example 3: real wind from Member 2 later -------------------------------------------------------
#   wind = SS.load_solve_result("out/res_W.pkl")        # a SolveResult with case='W' and v_ref set by the solver
#   res  = SS.calculate_stress_and_strain(gravity, wind, wind_speed=25.0, material=material, mesh=mesh)
# ---- Example 4: element-wise Excel export (the max/min summary above is still printed) ------------------
#   Gravity + zero wind -> results/element_stress_results.xlsx and results/element_strain_results.xlsx
paths = SS.export_element_results(res0, "results", mesh=mesh)
print(f"\nExported {res0.n_elems} elements (outer + inner):\n  {paths['stress']}\n  {paths['strain']}")