import numpy as np
from contracts import Mesh
from solver.testmesh import cylinder_mesh
from solver import bcs, links


def _gap_mesh(gap=0.5):
    """Two tubes along Z with a gap: 'Tower_1' (clamped at z=0) and 'Hub' above it. NOT sharing nodes."""
    a = cylinder_mesh(2.0, 10.0, 24, 20, 2)
    b = cylinder_mesh(2.0, 10.0, 24, 20, 2)
    nb = b.nodes.copy(); nb[:, 2] += 10.0 + gap
    m = Mesh(nodes=np.vstack([a.nodes, nb]), elems=np.vstack([a.elems, b.elems + a.n_nodes]),
             elem_group=np.r_[a.elem_group, b.elem_group + 1], group_names=["Tower_1", "Hub"])
    bcs.assign_node_sets(m)
    return m


def _link(m, rows=1):
    pa = links.free_edge_nodes(m, "Tower_1", near=(0, 0, 10.0), radius=1.5)
    pb = links.free_edge_nodes(m, "Hub", near=(0, 0, 10.5), radius=1.5)
    return links.make_link(m, "L1", "Tower_1", links.add_rows(m, pa, rows, "Tower_1"),
                           "Hub", links.add_rows(m, pb, rows, "Hub"))


def test_patches_are_the_rings():
    m = _gap_mesh()
    pa = links.free_edge_nodes(m, "Tower_1", near=(0, 0, 10.0), radius=1.5)
    pb = links.free_edge_nodes(m, "Hub", near=(0, 0, 10.5), radius=1.5)
    assert len(pa) == len(pb) == 48                                  # 24 cells -> 48 S6 ring nodes
    assert np.allclose(m.nodes[pa, 2], 10.0) and np.allclose(m.nodes[pb, 2], 10.5)
    assert len(links.add_rows(m, pa, 1, "Tower_1")) > len(pa)


def test_preflight_needs_the_link():
    m = _gap_mesh()
    errs = bcs.preflight(m, strict=False, verbose=False, allow_open_top=False)["errors"]
    assert any("2 connected components" in e for e in errs)
    spec = [("Tower_1", "Hub")]
    errs2 = bcs.preflight(m, strict=False, verbose=False, joint_spec=spec)["errors"]
    assert any("Joint Tower_1 - Hub" in e for e in errs2)             # without the link the joint is reported missing
    rep = bcs.preflight(m, strict=False, verbose=False, joint_spec=spec, links=[_link(m)])
    only = [e for e in rep["errors"]]
    assert rep["components"] == 1 and rep["joint_status"][("Tower_1", "Hub")] == "link"
    assert rep["free_edges"]["n_linked"] == 48          # 24 corner edges on each ring
    # what remains is the open far end of the Hub tube (stands in for something else), nothing about the gap
    assert all("Hub" in e and "z 20" in e.replace("z 20.", "z 20") or "Free edges away" in e for e in only)
    assert not any("components" in e or "Joint" in e for e in only)


def test_equations_reproduce_a_rigid_motion():
    m = _gap_mesh(); lk = _link(m, rows=1)
    ids = links.link_ids(m, [lk])["L1"]
    lines = links.link_lines(m, [lk])
    assert lines[0] == "*NODE" and "*EQUATION" in lines
    rng = np.random.default_rng(5); uref, th = rng.normal(size=3), rng.normal(size=3)
    xyz = {}
    for l in lines[1:lines.index("*EQUATION")]:
        p = [float(x) for x in l.split(",")]; xyz[int(p[0])] = np.array(p[1:])

    def dof(n, d):
        if n == ids[0]: return uref[d - 1]
        if n == ids[1]: return th[d - 1]
        return (uref + np.cross(th, m.nodes[n - 1] - lk.ref_xyz))[d - 1]
    i, worst, cnt = lines.index("*EQUATION") + 1, 0.0, 0
    while i < len(lines):
        assert lines[i] == "4"
        v = [x.strip() for x in lines[i + 1].split(",")]
        worst = max(worst, abs(sum(float(v[k + 2]) * dof(int(v[k]), int(v[k + 1])) for k in range(0, 12, 3)))); cnt += 1; i += 2
    assert cnt == 3 * len(lk.nodes) and worst < 1e-8     # coefficients are printed with 10 digits
    assert ids == (m.n_nodes + 1, m.n_nodes + 2)


def test_guards():
    m = _gap_mesh(); lk = _link(m)
    try:
        links.check_links(m, [lk, lk]); raise AssertionError
    except ValueError as e:
        assert "only once" in str(e)
    m.node_sets["base"] = np.r_[m.node_sets["base"], lk.nodes_a[:1]]
    try:
        links.check_links(m, [lk]); raise AssertionError
    except ValueError as e:
        assert "support" in str(e)
    try:
        links.make_link(m, "x", "Tower_1", lk.nodes_a[:3], "Hub", lk.nodes_b); raise AssertionError
    except ValueError as e:
        assert "at least 6" in str(e)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)