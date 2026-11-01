"""bcs.py - boundary-condition node sets and pre-run mesh checks (Member 2).

What this module does
  * builds the fixed-support node set "base" (bottom ring of the tower) and "top_ring"
  * checks the base ring is complete
  * checks the mesh is ONE connected body (else the solver gets a singular matrix)
  * finds free edges and says WHICH group they belong to (open blade tip, unfused joint...)
  * finds duplicate nodes (parts that touch but do not share nodes)
  * checks every joint: tower sections, tower-nacelle, nacelle-hub, hub-each blade
    (shared edges exist, close all the way round, mid-side nodes match)
  * writes the CalculiX *NSET / *BOUNDARY text for the fixed ring

Works on contracts.Mesh with S3 or S6 elements (corner nodes = first 3 columns).
SI units (m). Support model: base ring fully clamped (DOF 1-6) = rigid foundation.
"""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from contracts import Mesh, check_group_props


class PreflightError(ValueError):
    """Raised when a mesh must not be sent to CalculiX."""


# ----------------------------------------------------------------------------
# node sets
# ----------------------------------------------------------------------------
def _tower_mask(mesh, prefix="Tower_"):
    ids = [i for i, n in enumerate(mesh.group_names) if n.startswith(prefix)]
    if not ids:
        raise PreflightError(f"No group name starts with '{prefix}' (groups: {mesh.group_names})")
    return np.isin(mesh.elem_group, ids)


def select_base_nodes(mesh: Mesh, tol=1e-3, prefix="Tower_"):
    """Nodes of tower elements within tol of the tower's lowest z. Mid-side nodes included."""
    used = np.unique(mesh.elems[_tower_mask(mesh, prefix)])
    z = mesh.nodes[used, 2]
    return used[z < z.min() + tol]


def select_top_ring(mesh: Mesh, tol=1e-3, prefix="Tower_"):
    """Nodes of tower elements within tol of the tower's highest z (tower-top ring)."""
    used = np.unique(mesh.elems[_tower_mask(mesh, prefix)])
    z = mesh.nodes[used, 2]
    return used[z > z.max() - tol]


def assign_node_sets(mesh: Mesh, tol=1e-3):
    """Fill mesh.node_sets['base'] and ['top_ring']. Returns the mesh."""
    mesh.node_sets["base"] = select_base_nodes(mesh, tol)
    mesh.node_sets["top_ring"] = select_top_ring(mesh, tol)
    return mesh


def check_ring(mesh: Mesh, idx, axis_xy=(0.0, 0.0), expected_radius=None):
    """Is a node ring complete? Looks for gaps in the angles around the tower axis."""
    if len(idx) == 0:
        return {"n": 0, "r_min": 0.0, "r_max": 0.0, "max_gap_deg": 360.0, "median_gap_deg": 360.0, "complete": False}
    xyz = mesh.nodes[np.asarray(idx)]
    dx, dy = xyz[:, 0] - axis_xy[0], xyz[:, 1] - axis_xy[1]
    r = np.hypot(dx, dy)
    ang = np.sort(np.arctan2(dy, dx))
    gaps = np.degrees(np.diff(np.r_[ang, ang[0] + 2 * np.pi]))
    out = dict(n=len(idx), r_min=float(r.min()), r_max=float(r.max()),
               max_gap_deg=float(gaps.max()), median_gap_deg=float(np.median(gaps)))
    out["complete"] = bool(len(idx) >= 6 and gaps.max() < 3.0 * max(np.median(gaps), 1e-9))
    if expected_radius is not None:
        out["radius_ok"] = bool(abs(out["r_min"] - expected_radius) < 0.01 * expected_radius
                                and abs(out["r_max"] - expected_radius) < 0.01 * expected_radius)
    return out


# ----------------------------------------------------------------------------
# connectivity
# ----------------------------------------------------------------------------
def component_labels(mesh: Mesh, links=None):
    """(n_components, label per node). Nodes not used by any element get -1.

    links: RigidLink list (solver/links.py). All nodes of one link move as one rigid body, so they are joined.
    """
    e = mesh.elems
    k = e.shape[1]
    rows = np.repeat(e[:, 0], k - 1)
    cols = e[:, 1:].ravel()
    for lk in (links or []):
        nn = lk.nodes
        rows = np.concatenate([rows, np.full(len(nn) - 1, nn[0])])
        cols = np.concatenate([cols, nn[1:]])
    n = mesh.n_nodes
    g = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    _, lab = connected_components(g, directed=False)
    used = np.zeros(n, dtype=bool)
    used[np.unique(e)] = True
    lab = np.where(used, lab, -1)
    return len(np.unique(lab[used])), lab


def describe_components(mesh: Mesh, links=None):
    """Human-readable list: which groups make up each connected component."""
    n, lab = component_labels(mesh, links)
    out = []
    for c in np.unique(lab[lab >= 0]):
        el = lab[mesh.elems[:, 0]] == c
        names = sorted({mesh.group_names[g] for g in np.unique(mesh.elem_group[el])})
        out.append((int(c), int(el.sum()), names))
    out.sort(key=lambda t: -t[1])
    return out


# ----------------------------------------------------------------------------
# edges: free edges, mid-side consistency, joints between parts
# ----------------------------------------------------------------------------
def _occurrences(mesh: Mesh):
    """Every element edge as (sorted corner pair, mid-side node or -1, owning element, edge code)."""
    k = mesh.elems.shape[1]
    if k not in (3, 6):
        raise PreflightError("Only S3 / S6 meshes are supported")
    e = mesh.elems
    c = e[:, :3]
    pairs = np.sort(np.concatenate([c[:, [0, 1]], c[:, [1, 2]], c[:, [2, 0]]]), axis=1)
    mid = (np.concatenate([e[:, 3], e[:, 4], e[:, 5]]).astype(np.int64)
           if k == 6 else -np.ones(len(pairs), dtype=np.int64))
    owner = np.tile(np.arange(len(e)), 3)
    code = pairs[:, 0].astype(np.int64) * mesh.n_nodes + pairs[:, 1]
    return code, pairs, mid, owner


def check_free_edges(mesh: Mesh, base_idx, tol=1e-3, allow_open_top=False, linked_nodes=None):
    """Free edges (used by one element) grouped by part. Edges on the base ring are expected.

    allow_open_top=True also accepts the tower-top ring (stand-alone tower tests only).
    """
    code, pairs, mid, owner = _occurrences(mesh)
    uniq, inv, cnt = np.unique(code, return_inverse=True, return_counts=True)
    free = cnt[inv] == 1
    fe, fo = pairs[free], owner[free]
    ok = np.isin(fe, base_idx).all(axis=1)
    n_base = int(ok.sum())
    n_linked = 0
    if linked_nodes is not None and len(linked_nodes):
        lk_ok = np.isin(fe, linked_nodes).all(axis=1) & ~ok
        n_linked = int(lk_ok.sum())
        ok = ok | lk_ok
    if allow_open_top:
        ok = ok | np.isin(fe, select_top_ring(mesh, tol)).all(axis=1)
    bad = ~ok
    by_group = {}
    for g in np.unique(mesh.elem_group[fo[bad]]):
        m = bad & (mesh.elem_group[fo] == g)
        z = mesh.nodes[fe[m]][:, :, 2]
        by_group[mesh.group_names[g]] = dict(n=int(m.sum()), z_min=float(z.min()), z_max=float(z.max()))
    return dict(n_free=len(fe), n_base=n_base, n_linked=n_linked, n_unexpected=int(bad.sum()),
                unexpected_by_group=by_group, n_shared=int((cnt == 2).sum()),
                n_nonmanifold=int((cnt >= 3).sum()))


def check_midside_consistency(mesh: Mesh):
    """Two elements sharing an edge must also share its mid-side node (S6 only).

    If they do not, the edge has a crack at its mid-point even though the corners match.
    """
    if mesh.elems.shape[1] != 6:
        return dict(n_mismatch=0, groups=[])
    code, pairs, mid, owner = _occurrences(mesh)
    uniq, inv, cnt = np.unique(code, return_inverse=True, return_counts=True)
    mn = np.full(len(uniq), np.iinfo(np.int64).max, dtype=np.int64)
    mx = np.full(len(uniq), -1, dtype=np.int64)
    np.minimum.at(mn, inv, mid)
    np.maximum.at(mx, inv, mid)
    bad = (cnt >= 2) & (mn != mx)
    occ = bad[inv]
    names = sorted({mesh.group_names[g] for g in np.unique(mesh.elem_group[owner[occ]])})
    return dict(n_mismatch=int(bad.sum()), groups=names)


def default_joint_spec(group_names):
    """Joints a normal turbine must have: tower chain, tower top-nacelle, nacelle-hub, hub-each blade."""
    def num(s):
        return int(s.split("_")[1])
    towers = sorted([n for n in group_names if n.startswith("Tower_")], key=num)
    blades = sorted([n for n in group_names if n.startswith("Blade_")], key=num)
    spec = [(towers[i], towers[i + 1]) for i in range(len(towers) - 1)]
    if towers and "Nacelle" in group_names:
        spec.append((towers[-1], "Nacelle"))
    if "Nacelle" in group_names and "Hub" in group_names:
        spec.append(("Nacelle", "Hub"))
    if "Hub" in group_names:
        spec += [("Hub", b) for b in blades]
    return spec


def analyze_joints(mesh: Mesh):
    """All places where two different parts share edges.

    Returns {(nameA, nameB): dict(n_edges, n_shared_nodes, closed, length_m, z_min, z_max)}.
    closed=True means the shared edges form closed loops (no open ends), i.e. the parts are
    joined all the way round. length_m is the chord length of the joint (compare with the
    circumference of the ring you expect).
    """
    code, pairs, mid, owner = _occurrences(mesh)
    grp = mesh.elem_group[owner]
    uniq, first, inv, cnt = np.unique(code, return_index=True, return_inverse=True, return_counts=True)
    G = len(mesh.group_names)
    gmin = np.full(len(uniq), 10 ** 9, dtype=np.int64)
    gmax = np.full(len(uniq), -1, dtype=np.int64)
    np.minimum.at(gmin, inv, grp)
    np.maximum.at(gmax, inv, grp)
    cross = gmin != gmax
    ends = pairs[first]                                   # (U, 2) corner nodes of each unique edge
    edges_of = {}
    two = np.where(cross & (cnt == 2))[0]
    for u, a, b in zip(two, gmin[two], gmax[two]):
        edges_of.setdefault((int(a), int(b)), []).append(u)
    for u in np.where(cross & (cnt > 2))[0]:              # T-junctions: every pair of parts on that edge
        gs = np.unique(grp[inv == u])
        for i in range(len(gs)):
            for j in range(i + 1, len(gs)):
                edges_of.setdefault((int(gs[i]), int(gs[j])), []).append(u)

    nodes_of = {g: np.unique(mesh.elems[mesh.elem_group == g]) for g in range(G)}
    out = {}
    for (a, b), ues in edges_of.items():
        en = ends[np.array(ues)]
        deg = np.bincount(en.ravel(), minlength=mesh.n_nodes)
        deg = deg[deg > 0]
        pts = mesh.nodes[en]
        key = tuple(sorted((mesh.group_names[a], mesh.group_names[b])))
        out[key] = dict(n_edges=len(ues),
                        n_shared_nodes=int(len(np.intersect1d(nodes_of[a], nodes_of[b]))),
                        closed=bool(np.all(deg % 2 == 0)),
                        length_m=float(np.linalg.norm(pts[:, 0] - pts[:, 1], axis=1).sum()),
                        z_min=float(pts[:, :, 2].min()), z_max=float(pts[:, :, 2].max()))
    return out


def find_duplicate_nodes(mesh: Mesh, tol=1e-6):
    """Pairs of different nodes closer than tol: touching parts that do not share nodes."""
    return cKDTree(mesh.nodes).query_pairs(tol, output_type="ndarray")


# ----------------------------------------------------------------------------
# the one call to use before every solve
# ----------------------------------------------------------------------------
def preflight(mesh: Mesh, props=None, expected_base_radius=None, allow_open_top=False,
              joint_spec=None, links=None, strict=True, verbose=True):
    """Run every check. Raises PreflightError (if strict) when the mesh is not safe to solve.

    links: RigidLink list. A link joins its patches (components), makes free edges on the patches acceptable, and
    counts as the joint between its two groups.
    joint_spec: list of (groupA, groupB) joints that must exist. Default: tower sections in a
    chain, last tower section-Nacelle, Nacelle-Hub, Hub-every blade. Pass [] to skip.
    Returns a report dict. Sets the node sets if missing.
    """
    if "base" not in mesh.node_sets:
        assign_node_sets(mesh)
    base = mesh.node_sets["base"]
    errors, warnings_ = [], []
    rep = {"n_nodes": mesh.n_nodes, "n_elems": mesh.n_elems}

    rep["ring"] = check_ring(mesh, base, expected_radius=expected_base_radius)
    if len(base) == 0:
        errors.append("No base nodes found")
    if not rep["ring"]["complete"]:
        errors.append(f"Base ring looks incomplete (max angular gap {rep['ring']['max_gap_deg']:.1f} deg "
                      f"vs median {rep['ring']['median_gap_deg']:.1f} deg)")
    if rep["ring"].get("radius_ok") is False:
        warnings_.append(f"Base radius {rep['ring']['r_min']:.3f}..{rep['ring']['r_max']:.3f} m "
                         f"differs from expected {expected_base_radius} m (wrong units?)")

    links = links or []
    if links:
        from solver.links import check_links
        try:
            check_links(mesh, links)
        except ValueError as ex:
            errors.append(str(ex))
    linked = np.unique(np.concatenate([lk.nodes for lk in links])) if links else None
    ncomp = component_labels(mesh, links)[0]
    rep["components"] = ncomp
    if ncomp != 1:
        rep["component_groups"] = describe_components(mesh, links)
        errors.append(f"{ncomp} connected components, expected 1. Parts: "
                      + "; ".join(f"[{', '.join(n)}] ({ne} elems)" for _, ne, n in rep["component_groups"]))

    fe = check_free_edges(mesh, base, allow_open_top=allow_open_top, linked_nodes=linked)
    rep["free_edges"] = fe
    if fe["n_unexpected"]:
        errors.append("Free edges away from the base: " + "; ".join(
            f"{g}: {d['n']} edges, z {d['z_min']:.2f}..{d['z_max']:.2f} m"
            for g, d in fe["unexpected_by_group"].items())
            + " (open blade tip? part not fused to its neighbour?)")
    if fe["n_nonmanifold"]:
        warnings_.append(f"{fe['n_nonmanifold']} edges shared by 3+ elements (T-junction; check it is intended)")

    mc = check_midside_consistency(mesh)
    rep["midside"] = mc
    if mc["n_mismatch"]:
        errors.append(f"{mc['n_mismatch']} shared edges have different mid-side nodes in the two elements "
                      f"(groups: {', '.join(mc['groups'])}): the mesh has a crack along those edges")

    dup = find_duplicate_nodes(mesh)
    rep["duplicate_node_pairs"] = len(dup)
    if len(dup):
        msg = f"{len(dup)} pairs of coincident nodes: touching parts do not share nodes"
        (errors if ncomp != 1 else warnings_).append(msg)

    joints = analyze_joints(mesh)
    rep["joints"] = joints
    spec = default_joint_spec(mesh.group_names) if joint_spec is None else joint_spec
    wanted = {tuple(sorted(p)): tuple(p) for p in spec}      # sorted key -> display order
    rep["joint_status"] = {}
    link_pairs = {tuple(sorted((lk.group_a, lk.group_b))) for lk in links}
    for key, (a, b) in wanted.items():
        j = joints.get(key)
        if j is None and key in link_pairs:
            rep["joint_status"][(a, b)] = "link"
            continue
        if j is None:
            errors.append(f"Joint {a} - {b}: the parts share no edges (not fused)")
            rep["joint_status"][(a, b)] = "MISSING"
        elif not j["closed"]:
            errors.append(f"Joint {a} - {b}: shared edges have open ends "
                          f"(connection is not closed all the way round)")
            rep["joint_status"][(a, b)] = "OPEN"
        else:
            rep["joint_status"][(a, b)] = "ok"
    for pair, j in joints.items():
        if pair not in wanted:
            warnings_.append(f"Unexpected contact {pair[0]} - {pair[1]} ({j['n_edges']} shared edges)")

    if props is not None:
        try:
            check_group_props(props, mesh)
        except ValueError as ex:
            errors.append(str(ex))

    rep["errors"], rep["warnings"] = errors, warnings_
    if verbose:
        r = rep["ring"]
        print("\n--- Boundary-condition preflight ---")
        print(f"nodes {mesh.n_nodes}, elements {mesh.n_elems}, groups {mesh.group_names}")
        print(f"base ring: {r['n']} nodes, radius {r['r_min']:.3f}..{r['r_max']:.3f} m, "
              f"max angular gap {r['max_gap_deg']:.1f} deg, complete={r['complete']}")
        print(f"connected components: {ncomp}")
        print(f"free edges: {fe['n_free']} (on base ring {fe['n_base']}, on link patches {fe['n_linked']}, unexpected {fe['n_unexpected']})")
        print(f"mid-side node mismatches: {mc['n_mismatch']}   coincident node pairs: {len(dup)}")
        print("joints:")
        for key, (a, b) in wanted.items():
            j = joints.get(key)
            if rep["joint_status"][(a, b)] == "link":
                print(f"  {a:8s} - {b:8s} link    (rigid link through a reference node)")
            elif j:
                print(f"  {a:8s} - {b:8s} {rep['joint_status'][(a, b)]:7s} {j['n_edges']:4d} edges, "
                      f"{j['n_shared_nodes']:4d} nodes, length {j['length_m']:7.2f} m, "
                      f"z {j['z_min']:.2f}..{j['z_max']:.2f}")
            else:
                print(f"  {a:8s} - {b:8s} MISSING")
        for w in warnings_:
            print("WARNING:", w)
        for er in errors:
            print("ERROR:", er)
        print("RESULT:", "OK to solve" if not errors else "NOT OK")
    if errors and strict:
        raise PreflightError("; ".join(errors))
    return rep


# ----------------------------------------------------------------------------
# CalculiX text
# ----------------------------------------------------------------------------
def nset_lines(name, node_idx, per_line=10):
    """*NSET block. node_idx are 0-based mesh indices; CalculiX ids are index+1."""
    ids = (np.asarray(node_idx, dtype=int) + 1).tolist()
    out = [f"*NSET, NSET={name.upper()}"]
    out += [", ".join(map(str, ids[i:i + per_line])) for i in range(0, len(ids), per_line)]
    return out


def boundary_lines(mesh: Mesh, name="base"):
    """Fixed support: all six DOF (3 displacements + 3 rotations) on the node set."""
    return nset_lines(name, mesh.node_sets[name]) + ["*BOUNDARY", f"{name.upper()}, 1, 6"]