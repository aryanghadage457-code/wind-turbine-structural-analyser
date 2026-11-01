"""
Tests for StressAndStrain.py (Member 3).   Run from the repository root:

    python -m unittest tests.test_stress_and_strain -v        (stdlib only)
    python tests/test_stress_and_strain.py                    (same)
    pytest tests/test_stress_and_strain.py                    (if pytest is installed)

Tests that need Member 2's files (out/res_G.pkl, out/G.inp, out/full_mesh.pkl) are SKIPPED, not failed,
when those files are absent. Wind data used here is either a zero placeholder or SYNTHETIC TEST DATA.
"""
import hashlib
import os
import pickle
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from contracts import STRESS_ORDER, Mesh, Settings, SolveResult               # noqa: E402
import StressAndStrain as SS                                                  # noqa: E402
from synthetic_wind_data import SYNTHETIC_LABEL, is_synthetic, make_synthetic_wind_result   # noqa: E402

GRAV_PKL = os.path.join(ROOT, "out", "res_G.pkl")
INP = os.path.join(ROOT, "out", "G.inp")
DAT = os.path.join(ROOT, "out", "G.dat")
MESH_PKL = os.path.join(ROOT, "out", "full_mesh.pkl")
HAVE_REAL = all(os.path.isfile(p) for p in (GRAV_PKL, INP))
real = unittest.skipUnless(HAVE_REAL, "Member 2 files out/res_G.pkl and out/G.inp not available")

MPa = 1e6
E_STEEL, NU = 210e9, 0.3
_cache = {}


def _real():
    """Load the actual gravity result, per-element material and (optionally) mesh once."""
    if not _cache:
        g = SS.load_solve_result(GRAV_PKL)
        n = g.stress_outer.shape[0]
        _cache["g"] = g
        _cache["mat"] = SS.MaterialProps.from_inp(INP, n)
        _cache["mesh"] = SS.load_mesh(MESH_PKL) if os.path.isfile(MESH_PKL) else None
    return _cache["g"], _cache["mat"], _cache["mesh"]


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _tiny(case, outer, inner="same", v_ref=None, n_nodes=5):
    """Small hand-made SolveResult for analytical tests."""
    outer = np.atleast_2d(np.asarray(outer, float))
    inner = outer.copy() if isinstance(inner, str) else (None if inner is None else np.atleast_2d(np.asarray(inner, float)))
    return SolveResult(case=case, stress_outer=outer, stress_inner=inner, displacements=np.zeros((n_nodes, 3)),
                       base_reaction_force=np.zeros(3), base_reaction_moment=np.zeros(3), applied_force=np.zeros(3),
                       v_ref=v_ref)


def _tiny_zero_wind(g, v_ref=10.0):
    return SS.make_zero_wind_result(g, v_ref=v_ref)


# =============================================================================================
class TestInspectionFacts(unittest.TestCase):
    """Pin down the facts about Member 2's data that the module relies on."""

    def test_contract_component_order(self):
        self.assertEqual(STRESS_ORDER, ("xx", "yy", "zz", "xy", "xz", "yz"))

    @real
    def test_solveresult_structure(self):
        g, _, mesh = _real()
        self.assertIsInstance(g, SolveResult)
        self.assertEqual(g.case, "G")
        self.assertEqual(g.stress_outer.ndim, 2)
        self.assertEqual(g.stress_outer.shape[1], 6)
        self.assertEqual(g.stress_inner.shape, g.stress_outer.shape)
        self.assertIsNone(g.v_ref)
        if mesh is not None:
            self.assertEqual(mesh.n_elems, g.stress_outer.shape[0])
            self.assertEqual(mesh.n_nodes, g.displacements.shape[0])

    @real
    def test_pkl_matches_raw_dat_extrapolation(self):
        """res_G.pkl must equal Member 2's own reduction of the raw .dat integration-point values."""
        if not (os.path.isfile(DAT) and os.path.isfile(MESH_PKL)):
            self.skipTest("out/G.dat or out/full_mesh.pkl missing")
        from solver import ccx_reader as R
        g, _, mesh = _real()
        d = R.read_dat(DAT, mesh.n_nodes, mesh.n_elems)
        plus, minus, _ = R.surface_stresses(d["S"])
        np.testing.assert_allclose(g.stress_outer, plus, rtol=1e-12, atol=1e-6)
        np.testing.assert_allclose(g.stress_inner, minus, rtol=1e-12, atol=1e-6)

    @real
    def test_local_axes_rule_on_tower(self):
        """Stresses are element-local: rotating with the CalculiX rule gives the physical axial stress on the
        tower (vertical, compressive, ~ W/(pi D t)) and ~0 horizontal normal stress."""
        g, _, mesh = _real()
        if mesh is None:
            self.skipTest("mesh pickle missing")
        axes, amb = SS.element_local_axes(mesh)
        tower = np.isin(mesh.elem_group, [i for i, n in enumerate(mesh.group_names) if n.startswith("Tower_1")]) & ~amb
        Tg = SS.stress_to_global(g.stress_outer, axes)[tower]
        self.assertTrue(-13e6 < np.median(Tg[:, 2, 2]) < -11e6)           # ~ -11.8 MPa axial
        self.assertLess(abs(np.median(Tg[:, 0, 0])), 0.5e6)
        self.assertLess(abs(np.median(Tg[:, 1, 1])), 0.5e6)
        # rotation preserves invariants
        np.testing.assert_allclose(np.trace(Tg, axis1=1, axis2=2),
                                   SS.stress_invariants(g.stress_outer[tower])[0], rtol=1e-9, atol=1.0)

    @real
    def test_material_recovered_from_inp(self):
        g, mat, mesh = _real()
        self.assertEqual(mat.n_elems, g.stress_outer.shape[0])
        np.testing.assert_allclose(mat.nu, 0.3)
        self.assertAlmostEqual(mat.E.max() / 1e9, 210.0)           # steel
        self.assertLess(mat.E.min(), 5e9)                          # outboard blade equivalent E
        self.assertTrue(np.isfinite(mat.thickness).all())
        if mesh is not None:
            i = mesh.group_names.index("Tower_1")
            self.assertTrue(np.all(mat.E[mesh.elem_group == i] == 210e9))
            self.assertTrue(np.allclose(mat.thickness[mesh.elem_group == i], 0.026))


# =============================================================================================
@real
class TestCombinedLoadingOnRealData(unittest.TestCase):

    def test1_zero_wind_total_equals_gravity(self):
        g, mat, mesh = _real()
        for v_ref in (1.0, 10.0, 37.5):                                 # placeholder v_ref is irrelevant
            w0 = SS.make_zero_wind_result(g, v_ref=v_ref)
            res = SS.calculate_stress_and_strain(g, w0, 0.0, mat, mesh=mesh)
            np.testing.assert_array_equal(res.outer.stress, g.stress_outer)
            np.testing.assert_array_equal(res.inner.stress, g.stress_inner)
            self.assertFalse(np.any(res.outer.stress_wind_scaled))
            self.assertFalse(np.any(res.inner.stress_wind_scaled))
        # a nonzero speed with the ZERO placeholder is still gravity only (and the report says so)
        res = SS.calculate_stress_and_strain(g, SS.make_zero_wind_result(g), 25.0, mat)
        np.testing.assert_array_equal(res.outer.stress, g.stress_outer)
        self.assertTrue(any("zero placeholder" in n for n in res.notes))

    def test2_synthetic_combined_loading(self):
        g, mat, mesh = _real()
        w = make_synthetic_wind_result(g, v_ref=10.0)
        self.assertTrue(is_synthetic(w))
        res = SS.calculate_stress_and_strain(g, w, 7.0, mat, mesh=mesh)
        s = (7.0 / 10.0) ** 2
        np.testing.assert_allclose(res.outer.stress, g.stress_outer + s * w.stress_outer, rtol=1e-13, atol=1e-6)
        np.testing.assert_allclose(res.inner.stress, g.stress_inner + s * w.stress_inner, rtol=1e-13, atol=1e-6)
        self.assertFalse(np.allclose(res.outer.stress, g.stress_outer))      # wind really contributes
        self.assertIn("SYNTHETIC", res.wind_label)
        self.assertIn("SYNTHETIC", res.report())

    def test3_wind_scaling(self):
        g, mat, _ = _real()
        w = make_synthetic_wind_result(g, v_ref=10.0)
        for v, factor in ((0.0, 0.0), (5.0, 0.25), (10.0, 1.0), (20.0, 4.0), (30.0, 9.0)):
            res = SS.calculate_stress_and_strain(g, w, v, mat)
            self.assertAlmostEqual(res.wind_scale, factor)
            np.testing.assert_allclose(res.outer.stress_wind_scaled, factor * w.stress_outer, rtol=1e-13, atol=1e-9)
            np.testing.assert_allclose(res.inner.stress_wind_scaled, factor * w.stress_inner, rtol=1e-13, atol=1e-9)
        r1 = SS.calculate_stress_and_strain(g, w, 10.0, mat)
        r2 = SS.calculate_stress_and_strain(g, w, 20.0, mat)
        np.testing.assert_allclose(r2.outer.stress_wind_scaled, 4.0 * r1.outer.stress_wind_scaled, rtol=1e-13)

    def test5_inner_and_outer_stay_separate(self):
        g, mat, _ = _real()
        w = make_synthetic_wind_result(g)
        res = SS.calculate_stress_and_strain(g, w, 10.0, mat)
        np.testing.assert_allclose(res.outer.stress, g.stress_outer + w.stress_outer, rtol=1e-13, atol=1e-6)
        np.testing.assert_allclose(res.inner.stress, g.stress_inner + w.stress_inner, rtol=1e-13, atol=1e-6)
        self.assertFalse(np.allclose(res.outer.von_mises, res.inner.von_mises))
        # Swap the wind surfaces: outer result must change to use w.inner -> proves the right array is used.
        w_sw = make_synthetic_wind_result(g)
        w_sw.stress_outer, w_sw.stress_inner = w.stress_inner.copy(), w.stress_outer.copy()
        sw = SS.calculate_stress_and_strain(g, w_sw, 10.0, mat)
        np.testing.assert_allclose(sw.outer.stress, g.stress_outer + w.stress_inner, rtol=1e-13, atol=1e-6)
        self.assertFalse(np.allclose(sw.outer.stress, res.outer.stress))
        # per-surface strains come from that surface's own stress
        exp = SS.strain_from_stress(res.inner.stress, mat.E, mat.nu, "plane_stress")
        np.testing.assert_allclose(res.inner.strain, exp, rtol=1e-13)

    def test7_member2_von_mises_agreement(self):
        from solver import ccx_reader as R
        g, mat, mesh = _real()
        res = SS.calculate_stress_and_strain(g, SS.make_zero_wind_result(g), 0.0, mat, mesh=mesh)
        np.testing.assert_allclose(res.outer.von_mises, R.von_mises(g.stress_outer), rtol=1e-9, atol=1.0)
        np.testing.assert_allclose(res.inner.von_mises, R.von_mises(g.stress_inner), rtol=1e-9, atol=1.0)
        # and against a fully independent route: eigenvalues of the tensor
        pr = res.outer.principal
        vm_eig = np.sqrt(0.5 * ((pr[:, 0] - pr[:, 1]) ** 2 + (pr[:, 1] - pr[:, 2]) ** 2 + (pr[:, 2] - pr[:, 0]) ** 2))
        np.testing.assert_allclose(res.outer.von_mises, vm_eig, rtol=1e-9, atol=1.0)
        # same maxima as run_gravity.py prints
        vm = R.von_mises(np.stack([g.stress_outer, g.stress_inner]))
        self.assertAlmostEqual(res.critical.value, float(vm.max()), delta=1.0)
        self.assertEqual(res.critical.surface, "outer" if vm[0].max() >= vm[1].max() else "inner")

    def test_critical_element_and_ids(self):
        g, mat, mesh = _real()
        w = make_synthetic_wind_result(g)
        res = SS.calculate_stress_and_strain(g, w, 10.0, mat, mesh=mesh)
        vm = np.stack([res.outer.von_mises, res.inner.von_mises])
        s, e = np.unravel_index(np.argmax(vm), vm.shape)
        self.assertEqual(res.critical.element_index, int(e))
        self.assertEqual(res.critical.ccx_element_id, int(e) + 1)
        self.assertEqual(res.critical.surface, ("outer", "inner")[s])
        self.assertAlmostEqual(res.critical.value, float(vm.max()))
        if mesh is not None:
            self.assertEqual(res.critical.group, mesh.group_names[mesh.elem_group[e]])
        self.assertEqual(res.extremes["von_mises"].value, res.critical.value)

    def test_gravity_result_is_never_modified(self):
        g, mat, _ = _real()
        before_file = _sha(GRAV_PKL)
        before = (g.stress_outer.copy(), g.stress_inner.copy())
        w = make_synthetic_wind_result(g)
        SS.calculate_stress_and_strain(g, w, 12.0, mat)
        np.testing.assert_array_equal(g.stress_outer, before[0])
        np.testing.assert_array_equal(g.stress_inner, before[1])
        self.assertEqual(_sha(GRAV_PKL), before_file)

    def test_principal_directions_are_eigenvectors(self):
        g, mat, _ = _real()
        res = SS.calculate_stress_and_strain(g, make_synthetic_wind_result(g), 10.0, mat)
        T = SS.stress_to_tensor(res.outer.stress)
        for i in range(3):
            v = res.outer.principal_dirs[:, :, i]
            lhs = np.einsum("eij,ej->ei", T, v)
            rhs = res.outer.principal[:, i, None] * v
            np.testing.assert_allclose(lhs, rhs, rtol=0, atol=1e-6 * np.abs(res.outer.principal).max())
        np.testing.assert_allclose(np.linalg.norm(res.outer.principal_dirs, axis=1), 1.0, atol=1e-12)

    def test_full3d_equivalent_strain_equals_vm_over_E(self):
        g, mat, _ = _real()
        res = SS.calculate_stress_and_strain(g, make_synthetic_wind_result(g), 10.0, mat, strain_model="full_3d")
        np.testing.assert_allclose(res.outer.equivalent_strain, res.outer.von_mises / mat.E, rtol=1e-9)

    def test_pickled_wind_result_plugs_in_unchanged(self):
        """Future compatibility: a W SolveResult loaded from disk (as Member 2's will be) needs no code change."""
        g, mat, _ = _real()
        w = make_synthetic_wind_result(g, v_ref=50.0)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "res_W.pkl")
            with open(p, "wb") as fh:
                pickle.dump(w, fh)
            w2 = SS.load_solve_result(p)
        a = SS.calculate_stress_and_strain(g, w, 30.0, mat)
        b = SS.calculate_stress_and_strain(g, w2, 30.0, mat)
        np.testing.assert_array_equal(a.outer.stress, b.outer.stress)
        # A result without our label (like a real one) is reported as an actual wind SolveResult
        w3 = SolveResult(**{k: getattr(w, k) for k in
                            ("case", "stress_outer", "stress_inner", "displacements", "base_reaction_force",
                             "base_reaction_moment", "applied_force", "v_ref")})
        c = SS.calculate_stress_and_strain(g, w3, 30.0, mat)
        self.assertEqual(c.wind_label, "actual wind SolveResult")
        np.testing.assert_array_equal(a.outer.stress, c.outer.stress)


# =============================================================================================
class TestTensorAddition(unittest.TestCase):

    def test4_components_added_before_derived_quantities(self):
        sg = np.array([[10, 20, 3, 4, 5, 6.0]]) * MPa
        sw = np.array([[-7, 5, 1, -2, 3, 8.0]]) * MPa
        g = _tiny("G", sg)
        w = _tiny("W", sw, v_ref=10.0)
        res = SS.calculate_stress_and_strain(g, w, 20.0, {"E": E_STEEL, "nu": NU})    # scale = 4
        total = sg + 4.0 * sw
        np.testing.assert_allclose(res.outer.stress, total, rtol=1e-14)
        # the tensor of the sum is the sum of the tensors (component placement checked explicitly)
        Tg, Tw = SS.stress_to_tensor(sg)[0], SS.stress_to_tensor(sw)[0]
        np.testing.assert_allclose(SS.stress_to_tensor(res.outer.stress)[0], Tg + 4 * Tw, rtol=1e-14)
        T = SS.stress_to_tensor(sg)[0]
        self.assertEqual((T[0, 0], T[1, 1], T[2, 2]), (10 * MPa, 20 * MPa, 3 * MPa))
        self.assertEqual((T[0, 1], T[0, 2], T[1, 2]), (4 * MPa, 5 * MPa, 6 * MPa))   # xy, xz, yz order
        self.assertTrue(np.array_equal(T, T.T))
        # von Mises of the SUM is not the sum of the von Mises values
        vm_sum_wrong = SS.stress_invariants(sg)[4][0] + 4 * SS.stress_invariants(sw)[4][0]
        vm_right = SS.stress_invariants(total)[4][0]
        self.assertNotAlmostEqual(vm_right, vm_sum_wrong, delta=1e3)
        self.assertAlmostEqual(res.outer.von_mises[0], vm_right, delta=1e-6 * vm_right)
        # direct textbook formula from the six summed components
        xx, yy, zz, xy, xz, yz = total[0]
        textbook = np.sqrt(0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2) + 3 * (xy ** 2 + xz ** 2 + yz ** 2))
        self.assertAlmostEqual(res.outer.von_mises[0], textbook, delta=1e-9 * textbook)

    def test_stress_to_tensor_rejects_wrong_shape(self):
        with self.assertRaises(ValueError):
            SS.stress_to_tensor(np.zeros((4, 5)))


# =============================================================================================
class TestAnalytical(unittest.TestCase):
    """Closed-form answers (floating-point tolerances ~1e-12 relative)."""
    E, NU = 200e9, 0.3
    MAT = {"E": 200e9, "nu": 0.3}

    def _run(self, sig, model="plane_stress"):
        sig = np.atleast_2d(np.asarray(sig, float))
        g, w = _tiny("G", sig), _tiny("W", np.zeros_like(sig), v_ref=1.0)
        return SS.calculate_stress_and_strain(g, w, 0.0, self.MAT, strain_model=model)

    def test_uniaxial_tension(self):
        s = 100 * MPa
        for model in SS.STRAIN_MODELS:
            r = self._run([s, 0, 0, 0, 0, 0], model).outer
            np.testing.assert_allclose(r.principal[0], [s, 0, 0], atol=1e-6)
            self.assertAlmostEqual(r.von_mises[0], s, delta=1e-6)
            self.assertAlmostEqual(r.max_shear[0], s / 2, delta=1e-6)
            self.assertAlmostEqual(r.mean_stress[0], s / 3, delta=1e-6)
            self.assertAlmostEqual(r.I1[0], s, delta=1e-6)
            self.assertAlmostEqual(r.J2[0] / (s * s / 3), 1.0, places=12)
            self.assertAlmostEqual(r.J3[0] / (2 * s ** 3 / 27), 1.0, places=12)
            e = s / self.E
            np.testing.assert_allclose(r.strain[0], [e, -self.NU * e, -self.NU * e, 0, 0, 0], rtol=1e-12, atol=1e-18)
            np.testing.assert_allclose(r.principal_strain[0], [e, -self.NU * e, -self.NU * e], rtol=1e-12)
            self.assertAlmostEqual(r.max_shear_strain[0] / ((1 + self.NU) * e), 1.0, places=12)
            self.assertAlmostEqual(r.equivalent_strain[0] / e, 1.0, places=12)       # = vm / E

    def test_pure_shear_engineering_vs_tensorial(self):
        t = 50 * MPa
        r = self._run([0, 0, 0, t, 0, 0]).outer
        np.testing.assert_allclose(r.principal[0], [t, 0, -t], atol=1e-6)
        self.assertAlmostEqual(r.von_mises[0] / (np.sqrt(3) * t), 1.0, places=12)
        self.assertAlmostEqual(r.max_shear[0], t, delta=1e-6)
        self.assertAlmostEqual(r.mean_stress[0], 0.0, delta=1e-6)
        self.assertAlmostEqual(r.J3[0], 0.0, delta=1e-3 * t ** 3 * 1e-9)
        G = self.E / (2 * (1 + self.NU))
        gamma = t / G                                           # engineering shear strain
        self.assertAlmostEqual(r.engineering_shear[0, 0] / gamma, 1.0, places=12)
        self.assertAlmostEqual(r.strain[0, STRESS_ORDER.index("xy")] / (gamma / 2), 1.0, places=12)   # tensorial = gamma/2
        np.testing.assert_allclose(r.principal_strain[0], [gamma / 2, 0, -gamma / 2], atol=1e-15, rtol=1e-12)
        self.assertAlmostEqual(r.max_shear_strain[0] / gamma, 1.0, places=12)     # engineering max shear = gamma
        self.assertAlmostEqual(r.equivalent_strain[0] / (np.sqrt(3) * t / self.E), 1.0, places=12)

    def test_hydrostatic_full3d_vs_plane_stress(self):
        p = 80 * MPa
        r3 = self._run([p, p, p, 0, 0, 0], "full_3d").outer
        np.testing.assert_allclose(r3.principal[0], [p, p, p])
        self.assertAlmostEqual(r3.von_mises[0], 0.0, delta=1e-6)
        self.assertAlmostEqual(r3.J2[0], 0.0, delta=1e-3)
        self.assertAlmostEqual(r3.mean_stress[0] / p, 1.0, places=12)
        np.testing.assert_allclose(r3.strain[0, :3], (1 - 2 * self.NU) * p / self.E, rtol=1e-12)   # volumetric only
        self.assertAlmostEqual(r3.equivalent_strain[0], 0.0, delta=1e-15)
        # plane-stress model ignores szz: exx = (1-nu) p/E, ezz = -2 nu p/E
        rp = self._run([p, p, p, 0, 0, 0], "plane_stress").outer
        np.testing.assert_allclose(rp.strain[0, :2], (1 - self.NU) * p / self.E, rtol=1e-12)
        self.assertAlmostEqual(rp.strain[0, 2] / (-2 * self.NU * p / self.E), 1.0, places=12)
        # stress results unaffected by the strain model (all six components are used for stress)
        self.assertAlmostEqual(rp.von_mises[0], r3.von_mises[0], delta=1e-6)

    def test_biaxial_plane_stress_hand_values(self):
        sxx, syy, sxy = 100 * MPa, 50 * MPa, 20 * MPa
        r = self._run([sxx, syy, 0, sxy, 0, 0]).outer
        mean, rad = (sxx + syy) / 2, np.hypot((sxx - syy) / 2, sxy)
        np.testing.assert_allclose(r.principal[0], [mean + rad, mean - rad, 0.0], atol=1e-6)
        vm = np.sqrt(sxx ** 2 - sxx * syy + syy ** 2 + 3 * sxy ** 2)
        self.assertAlmostEqual(r.von_mises[0] / vm, 1.0, places=12)
        exx, eyy = (sxx - self.NU * syy) / self.E, (syy - self.NU * sxx) / self.E
        ezz = -self.NU * (sxx + syy) / self.E
        gxy = 2 * (1 + self.NU) * sxy / self.E
        np.testing.assert_allclose(r.strain[0], [exx, eyy, ezz, gxy / 2, 0, 0], rtol=1e-12, atol=1e-18)
        np.testing.assert_allclose(r.engineering_shear[0], [gxy, 0, 0], rtol=1e-12, atol=1e-18)

    def test_sigma_zz_handling_differs_exactly_as_theory_says(self):
        sig = [100 * MPa, 40 * MPa, 30 * MPa, 0, 0, 0]
        ep = self._run(sig, "plane_stress").outer.strain[0]
        ef = self._run(sig, "full_3d").outer.strain[0]
        self.assertAlmostEqual(ep[2], -self.NU * (100 + 40) * MPa / self.E, delta=1e-18)
        self.assertAlmostEqual(ef[2], (30 - self.NU * 140) * MPa / self.E, delta=1e-18)
        self.assertAlmostEqual(ef[0] - ep[0], -self.NU * 30 * MPa / self.E, delta=1e-18)
        r = self._run(sig).outer
        self.assertAlmostEqual(r.sigma_zz_ratio[0], 30 * MPa / r.von_mises[0], places=12)

    def test_rotated_tensor_recovers_principal_values_and_vm(self):
        lam = np.array([300.0, 100.0, -50.0]) * MPa
        a = np.array([1.0, 2.0, 3.0]); a /= np.linalg.norm(a); th = 0.7
        K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
        R = np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K            # Rodrigues rotation
        T = R @ np.diag(lam) @ R.T
        sig = [T[0, 0], T[1, 1], T[2, 2], T[0, 1], T[0, 2], T[1, 2]]
        r = self._run(sig).outer
        np.testing.assert_allclose(r.principal[0], lam, rtol=1e-12, atol=1e-6)
        vm = np.sqrt(0.5 * ((lam[0] - lam[1]) ** 2 + (lam[1] - lam[2]) ** 2 + (lam[2] - lam[0]) ** 2))
        self.assertAlmostEqual(r.von_mises[0] / vm, 1.0, places=12)
        self.assertAlmostEqual(r.max_shear[0] / ((lam[0] - lam[2]) / 2), 1.0, places=12)
        dev = lam - lam.mean()
        self.assertAlmostEqual(r.J3[0] / np.prod(dev), 1.0, places=10)
        self.assertAlmostEqual(r.J2[0] / (0.5 * np.sum(dev ** 2)), 1.0, places=12)
        # eigenvector of the largest principal stress is the rotated first axis (up to sign)
        np.testing.assert_allclose(np.abs(r.principal_dirs[0][:, 0]), np.abs(R[:, 0]), atol=1e-12)
        # invariants are frame independent
        r0 = self._run([lam[0], lam[1], lam[2], 0, 0, 0]).outer
        for q in ("von_mises", "I1", "J2", "J3", "max_shear"):
            self.assertAlmostEqual(getattr(r, q)[0] / getattr(r0, q)[0], 1.0, places=9)

    def test_combined_analytical_case_through_public_api(self):
        """sigma_G = uniaxial 60 MPa, sigma_W(vref=10) = shear 30 MPa; at v=20: total xx=60, xy=120."""
        g = _tiny("G", [60 * MPa, 0, 0, 0, 0, 0])
        w = _tiny("W", [0, 0, 0, 30 * MPa, 0, 0], v_ref=10.0)
        r = SS.calculate_stress_and_strain(g, w, 20.0, self.MAT).outer
        np.testing.assert_allclose(r.stress[0], [60 * MPa, 0, 0, 120 * MPa, 0, 0])
        self.assertAlmostEqual(r.von_mises[0] / (MPa * np.sqrt(60 ** 2 + 3 * 120 ** 2)), 1.0, places=12)
        rad = np.hypot(30, 120)
        np.testing.assert_allclose(r.principal[0], [(30 + rad) * MPa, 0, (30 - rad) * MPa], rtol=1e-12, atol=1e-6)


# =============================================================================================
class TestValidationAndErrors(unittest.TestCase):
    MAT = {"E": 210e9, "nu": 0.3}

    def setUp(self):
        self.g = _tiny("G", [[1e6, 2e6, 0, 1e5, 0, 0], [3e6, 1e6, 0, 0, 0, 0]])
        self.w = _tiny("W", [[1e5, 0, 0, 0, 0, 0], [0, 1e5, 0, 0, 0, 0]], v_ref=10.0)

    def test_baseline_ok(self):
        SS.calculate_stress_and_strain(self.g, self.w, 5.0, self.MAT)

    def test_missing_material_is_an_error_not_a_default(self):
        with self.assertRaises(ValueError):
            SS.calculate_stress_and_strain(self.g, self.w, 5.0, None)
        with self.assertRaises(ValueError):
            SS.calculate_stress_and_strain(self.g, self.w, 5.0, {"E": 210e9})
        with self.assertRaises(ValueError):
            SS.MaterialProps.uniform(-1.0, 0.3, 2)
        with self.assertRaises(ValueError):
            SS.MaterialProps.uniform(210e9, 0.5, 2)
        with self.assertRaises(ValueError):                                   # wrong number of elements
            SS.calculate_stress_and_strain(self.g, self.w, 5.0, SS.MaterialProps.uniform(210e9, 0.3, 7))

    def test_settings_object_accepted(self):
        r = SS.calculate_stress_and_strain(self.g, self.w, 5.0, Settings(E=200e9, nu=0.25))
        self.assertIn("Settings", r.material_source)

    def test_wrong_cases_and_shapes(self):
        with self.assertRaises(ValueError):
            SS.calculate_stress_and_strain(self.w, self.w, 5.0, self.MAT)       # gravity slot holds a W result
        with self.assertRaises(ValueError):
            SS.calculate_stress_and_strain(self.g, self.g, 5.0, self.MAT)       # wind slot holds a G result
        short = _tiny("W", [[1e5, 0, 0, 0, 0, 0]], v_ref=10.0)
        with self.assertRaises(ValueError):
            SS.calculate_stress_and_strain(self.g, short, 5.0, self.MAT)        # different element count
        other_mesh = _tiny("W", self.w.stress_outer, v_ref=10.0, n_nodes=9)
        with self.assertRaises(ValueError):
            SS.calculate_stress_and_strain(self.g, other_mesh, 5.0, self.MAT)   # different node count
        with self.assertRaises(TypeError):
            SS.calculate_stress_and_strain("nope", self.w, 5.0, self.MAT)

    def test_nan_rejected(self):
        bad = _tiny("W", self.w.stress_outer.copy(), v_ref=10.0)
        bad.stress_outer[0, 0] = np.nan
        with self.assertRaises(ValueError):
            SS.calculate_stress_and_strain(self.g, bad, 5.0, self.MAT)

    def test_wind_speed_and_vref(self):
        for v in (-1.0, np.nan, np.inf):
            with self.assertRaises(ValueError):
                SS.calculate_stress_and_strain(self.g, self.w, v, self.MAT)
        no_vref = _tiny("W", self.w.stress_outer, v_ref=None)
        with self.assertRaises(ValueError):
            SS.calculate_stress_and_strain(self.g, no_vref, 5.0, self.MAT)
        ok = SS.calculate_stress_and_strain(self.g, no_vref, 20.0, self.MAT, wind_v_ref=10.0)
        self.assertAlmostEqual(ok.wind_scale, 4.0)
        with self.assertRaises(ValueError):                                      # contradicting v_ref
            SS.calculate_stress_and_strain(self.g, self.w, 5.0, self.MAT, wind_v_ref=25.0)
        with self.assertRaises(ValueError):
            SS.wind_scale_factor(5.0, 0.0)

    def test_inner_surface_availability(self):
        g_no = _tiny("G", self.g.stress_outer, inner=None)
        w_no = _tiny("W", self.w.stress_outer, inner=None, v_ref=10.0)
        r = SS.calculate_stress_and_strain(g_no, w_no, 5.0, self.MAT)
        self.assertIsNone(r.inner)
        self.assertNotIn("inner", {e.surface for e in r.extremes.values()})
        with self.assertRaises(ValueError):                                       # only one has inner
            SS.calculate_stress_and_strain(g_no, self.w, 5.0, self.MAT)

    def test_unknown_strain_model(self):
        with self.assertRaises(ValueError):
            SS.calculate_stress_and_strain(self.g, self.w, 5.0, self.MAT, strain_model="plane_strain")

    def test_mesh_size_validation(self):
        mesh = Mesh(nodes=np.zeros((5, 3)), elems=np.zeros((3, 6), int), elem_group=np.zeros(3, int), group_names=["A"])
        with self.assertRaises(ValueError):                                       # 3 elements vs 2 in results
            SS.calculate_stress_and_strain(self.g, self.w, 5.0, self.MAT, mesh=mesh)
        mesh_ok = Mesh(nodes=np.zeros((5, 3)), elems=np.zeros((2, 6), int), elem_group=np.zeros(2, int), group_names=["Part"])
        r = SS.calculate_stress_and_strain(self.g, self.w, 5.0, self.MAT, mesh=mesh_ok)
        self.assertEqual(r.critical.group, "Part")


# =============================================================================================
class TestInpParser(unittest.TestCase):
    INP = """*HEADING
test
*NODE
1, 0, 0, 0
*ELEMENT, TYPE=S6, ELSET=PART_A
1, 1, 2, 3, 4, 5, 6
2, 1, 2, 3, 4, 5, 6
*ELEMENT, TYPE=S6, ELSET=PART_B
3, 1, 2, 3, 4, 5, 6
4, 1, 2, 3, 4,
 5, 6
5, 1, 2, 3, 4, 5, 6
*ELSET, ELSET=EALL
PART_A, PART_B
*ELSET, ELSET=GEN, GENERATE
3, 5, 1
*MATERIAL, NAME=MAT1
*ELASTIC
2.0e11, 0.3
*DENSITY
7850
*MATERIAL, NAME=MAT2
*ELASTIC
1.0e10, 0.25
*SHELL SECTION, ELSET=PART_A, MATERIAL=MAT1
0.01
*SHELL SECTION, ELSET=GEN, MATERIAL=MAT2
0.02
"""

    def _write(self, text):
        d = tempfile.TemporaryDirectory(); self.addCleanup(d.cleanup)
        p = os.path.join(d.name, "t.inp")
        with open(p, "w") as fh:
            fh.write(text)
        return p

    def test_parse_sets_generate_and_continuation(self):
        m = SS.read_inp_element_properties(self._write(self.INP), 5)
        np.testing.assert_allclose(m.E, [2e11, 2e11, 1e10, 1e10, 1e10])
        np.testing.assert_allclose(m.nu, [0.3, 0.3, 0.25, 0.25, 0.25])
        np.testing.assert_allclose(m.thickness, [0.01, 0.01, 0.02, 0.02, 0.02])

    def test_missing_section_detected(self):
        with self.assertRaises(ValueError):
            SS.read_inp_element_properties(self._write(self.INP), 6)                 # element 6 has no section

    def test_overlapping_sections_detected(self):
        bad = self.INP + "*SHELL SECTION, ELSET=EALL, MATERIAL=MAT1\n0.03\n"
        with self.assertRaises(ValueError):
            SS.read_inp_element_properties(self._write(bad), 5)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            SS.read_inp_element_properties("/nonexistent/file.inp", 5)


class TestSyntheticGenerator(unittest.TestCase):
    def test_layout_matches_gravity_result(self):
        g = _tiny("G", np.ones((37, 6)) * 1e6, n_nodes=11)
        w = make_synthetic_wind_result(g, v_ref=10.0)
        self.assertEqual(w.case, "W")
        self.assertEqual(w.v_ref, 10.0)
        self.assertEqual(w.stress_outer.shape, g.stress_outer.shape)
        self.assertEqual(w.stress_inner.shape, g.stress_inner.shape)
        self.assertEqual(w.displacements.shape, g.displacements.shape)
        self.assertTrue(np.all(np.abs(w.stress_outer) > 0) and np.all(np.abs(w.stress_inner) > 0))
        self.assertFalse(np.allclose(w.stress_outer, w.stress_inner))
        self.assertEqual(w.data_label, SYNTHETIC_LABEL)
        self.assertTrue(is_synthetic(w))
        g2 = _tiny("G", np.ones((5, 6)), inner=None)
        self.assertIsNone(make_synthetic_wind_result(g2).stress_inner)

    @real
    def test_matches_real_gravity_layout(self):
        g, _, _ = _real()
        w = make_synthetic_wind_result(g)
        self.assertEqual(w.stress_outer.shape, g.stress_outer.shape)
        self.assertEqual(w.displacements.shape, g.displacements.shape)
        self.assertEqual(w.v_ref, 10.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)