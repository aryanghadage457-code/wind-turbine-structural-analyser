import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import numpy as np
import pytest

from analysis_metadata import geometry_fingerprint, mesh_fingerprint, make_metadata, metadata_matches
from contracts import Mesh, SolveResult
from StressAndStrain import calculate_stress_and_strain, MaterialProps, validate_gravity_wind_pair
from failure_analysis import assess_npz


def _mesh():
    return Mesh(nodes=np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]),
                elems=np.array([[0, 1, 2]]), elem_group=np.array([0]), group_names=["Plate"])


def _result(case, stress, disp, v_ref=None, metadata=None):
    return SolveResult(case=case, stress_outer=np.asarray(stress, float), stress_inner=None,
                       displacements=np.asarray(disp, float), base_reaction_force=np.zeros(3),
                       base_reaction_moment=np.zeros(3), applied_force=np.zeros(3),
                       v_ref=v_ref, metadata=metadata or {})


def test_mesh_fingerprint_includes_node_and_element_order():
    m = _mesh()
    h = mesh_fingerprint(m)
    reordered = Mesh(nodes=m.nodes.copy(), elems=np.array([[1, 0, 2]]),
                     elem_group=m.elem_group.copy(), group_names=list(m.group_names))
    assert h != mesh_fingerprint(reordered)


def test_geometry_fingerprint_changes_when_config_changes(tmp_path):
    f = tmp_path / "geometry.json"
    f.write_text(json.dumps({"tower": {"height": 80}}))
    h1 = geometry_fingerprint(f)
    f.write_text(json.dumps({"tower": {"height": 90}}))
    assert h1 != geometry_fingerprint(f)


def test_cache_metadata_checks_direction_and_reference_speed():
    meta = make_metadata(case="W", geometry_hash="g", mesh_hash="m", v_ref=50,
                         wind_direction_deg=90)
    assert metadata_matches(meta, case="W", geometry_hash="g", mesh_hash="m",
                            wind_direction_deg=450, v_ref=50)
    assert not metadata_matches(meta, case="W", geometry_hash="g", mesh_hash="m",
                               wind_direction_deg=180, v_ref=50)


def test_speed_scaling_is_quadratic_and_direction_is_saved():
    g = _result("G", [[10e6, 0, 0, 0, 0, 0]], np.zeros((3, 3)))
    wmeta = {"wind_direction_deg": 90, "geometry_fingerprint": "g", "mesh_fingerprint": "m"}
    w = _result("W", [[4e6, 0, 0, 0, 0, 0]], np.ones((3, 3)), 50, wmeta)
    m = _mesh()
    a = calculate_stress_and_strain(g, w, 25, MaterialProps.uniform(210e9, .3, 1),
                                    mesh=m, wind_mesh=m)
    b = calculate_stress_and_strain(g, w, 50, MaterialProps.uniform(210e9, .3, 1),
                                    mesh=m, wind_mesh=m)
    assert np.allclose(a.outer.stress[0, 0], 11e6)
    assert np.allclose(b.outer.stress[0, 0], 14e6)
    assert a.wind_direction == 90
    assert np.allclose(a.outer.stress_wind_scaled * 4, b.outer.stress_wind_scaled)


def test_requested_direction_cannot_disagree_with_solver_case():
    g = _result("G", [[0, 0, 0, 0, 0, 0]], np.zeros((3, 3)))
    w = _result("W", [[0, 0, 0, 0, 0, 0]], np.zeros((3, 3)), 50,
                {"wind_direction_deg": 0})
    with pytest.raises(ValueError, match="direction"):
        calculate_stress_and_strain(g, w, 20, MaterialProps.uniform(210e9, .3, 1),
                                    wind_direction_deg=90)


def test_pair_rejects_different_mesh_identity():
    g = _result("G", [[0, 0, 0, 0, 0, 0]], np.zeros((3, 3)), metadata={"mesh_fingerprint": "a"})
    w = _result("W", [[0, 0, 0, 0, 0, 0]], np.zeros((3, 3)), 50,
                {"mesh_fingerprint": "b"})
    with pytest.raises(ValueError, match="fingerprints differ"):
        validate_gravity_wind_pair(g, w)


def test_failure_assessment_uses_saved_vm_and_marks_limit(tmp_path):
    f = tmp_path / "r.npz"
    np.savez_compressed(f, outer_von_mises=np.array([100e6, 300e6]),
                        metadata_json=np.array(json.dumps({"wind_direction_deg": 0})))
    r = assess_npz(f, yield_strength_pa=345e6, safety_factor=1.5)
    assert r["governing_element_index_0_based"] == 1
    assert r["status"] == "EXCEEDS_ALLOWABLE"


def test_visualization_loader_checks_metadata_and_combines_displacements(tmp_path):
    import pickle
    from example_deformation import load_validated_results
    m = _mesh()
    mh = mesh_fingerprint(m)
    gm = make_metadata(case="G", geometry_hash="geo", mesh_hash=mh)
    wm = make_metadata(case="W", geometry_hash="geo", mesh_hash=mh,
                       wind_speed=50, v_ref=50, wind_direction_deg=90)
    g = _result("G", [[1e6, 0, 0, 0, 0, 0]], np.ones((3, 3)), metadata=gm)
    w = _result("W", [[2e6, 0, 0, 0, 0, 0]], np.ones((3, 3)) * 2, 50, wm)
    paths = {name: tmp_path / name for name in ("mesh.pkl", "wind_mesh.pkl", "g.pkl", "w.pkl", "s.npz")}
    for key, obj in (("mesh.pkl", (m, {"Plate": .01})), ("wind_mesh.pkl", m),
                     ("g.pkl", g), ("w.pkl", w)):
        with paths[key].open("wb") as f:
            pickle.dump(obj, f)
    sm = dict(wm)
    sm.update({"operating_wind_speed_m_s": 25, "reference_wind_speed_m_s": 50,
               "wind_direction_deg": 90})
    np.savez_compressed(paths["s.npz"], metadata_json=np.array(json.dumps(sm)),
                        outer_principal=np.array([[3e6, 2e6, 1e6]]),
                        outer_von_mises=np.array([2e6]), outer_max_shear=np.array([1e6]))
    loaded = load_validated_results(paths["mesh.pkl"], paths["wind_mesh.pkl"],
                                    paths["g.pkl"], paths["w.pkl"], paths["s.npz"])
    assert np.allclose(loaded[4], np.ones((3, 3)) + .25 * np.ones((3, 3)) * 2)
    assert loaded[5]["wind_direction"] == 90


def test_compass_wind_bearings_are_from_direction_and_cardinal():
    from solver.loads import wind_dir_vector
    assert np.allclose(wind_dir_vector(0), [0, -1, 0], atol=1e-14)
    assert np.allclose(wind_dir_vector(90), [-1, 0, 0], atol=1e-14)
    assert np.allclose(wind_dir_vector(180), [0, 1, 0], atol=1e-14)
    assert np.allclose(wind_dir_vector(270), [1, 0, 0], atol=1e-14)
