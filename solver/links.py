"""links.py - rigid link between two node patches through a reference node, written as *EQUATION.
 
Why this way (CalculiX 2.23, tests/coupling_probe.py + tests/rigid_link_probe.py):
  *COUPLING (KINEMATIC / DISTRIBUTING)   -> load NOT transmitted (reaction 0)
  *RIGID BODY on shell nodes             -> "*ERROR in gen3dmpc: nodes belonging to shell elements must not be subject to a RIGID MPC"
  *EQUATION  u_i = u_ref + theta x r_i   -> PASS (base reaction = load; tip deflection within 0.5 % of the hand
                                            value for a tube with a rigid segment)
 
All nodes of patch A and patch B move as ONE rigid body (small-rotation kinematics, same as the rest of the
linear analysis). The rotation theta is stored as the three translational DOF of a second node ("rot node"),
so only the keyword that works is used. Reference and rotation nodes get ids above the mesh nodes and belong to
no element; ccx_reader.py never sees them.
 
A link makes the patch nodes rigid relative to each other: keep patches small (a ring or 1-2 element rows),
and expect local stress artefacts at the patch edge.
"""
from dataclasses import dataclass
 
import numpy as np
 
from solver.bcs import _occurrences
 
 
@dataclass
class RigidLink:
    name: str
    group_a: str
    group_b: str
    nodes_a: np.ndarray            # 0-based mesh node indices (patch on group_a)
    nodes_b: np.ndarray            # 0-based mesh node indices (patch on group_b)
    ref_xyz: np.ndarray            # reference point (m), default = centroid of both patches
 
    @property
    def nodes(self):
        return np.unique(np.concatenate([self.nodes_a, self.nodes_b]))
 
 
def free_edge_nodes(mesh, group, near=None, radius=None):
    """Nodes (corner + mid-side) on the free edges of one group, optionally only those within `radius` of `near`.
 
    Free edge = edge used by exactly one element of the whole mesh. Use `near`/`radius` to pick one ring when a
    group has several (for example the opening of the hub, and not its other end).
    """
    code, pairs, mid, owner = _occurrences(mesh)
    _, inv, cnt = np.unique(code, return_inverse=True, return_counts=True)
    free = (cnt[inv] == 1) & (mesh.elem_group[owner] == mesh.group_names.index(group))
    nodes = np.unique(np.concatenate([pairs[free].ravel(), mid[free]]))
    if near is not None:
        nodes = nodes[np.linalg.norm(mesh.nodes[nodes] - np.asarray(near, float), axis=1) <= radius]
    return nodes
 
 
def add_rows(mesh, nodes, rows=1, group=None):
    """Grow a patch by `rows` element rows: add every node of every element that touches the patch."""
    nodes = np.asarray(nodes)
    sel = np.ones(mesh.n_elems, bool) if group is None else mesh.elem_group == mesh.group_names.index(group)
    for _ in range(rows):
        hit = sel & np.isin(mesh.elems, nodes).any(axis=1)
        nodes = np.unique(np.concatenate([nodes, mesh.elems[hit].ravel()]))
    return nodes
 
 
def make_link(mesh, name, group_a, nodes_a, group_b, nodes_b, ref_xyz=None):
    na, nb = np.unique(nodes_a), np.unique(nodes_b)
    if len(na) < 6 or len(nb) < 6:
        raise ValueError(f"link {name}: patches need at least 6 nodes each (got {len(na)} and {len(nb)})")
    if len(np.intersect1d(na, nb)):
        raise ValueError(f"link {name}: patches share nodes: the parts are already connected there")
    ref = mesh.nodes[np.concatenate([na, nb])].mean(axis=0) if ref_xyz is None else np.asarray(ref_xyz, float)
    return RigidLink(name, group_a, group_b, na, nb, ref)
 
 
def check_links(mesh, links):
    """Each node may be tied by only one link and must not be a support node."""
    seen = {}
    base = set(np.asarray(mesh.node_sets.get("base", [])).tolist())
    for lk in links:
        for n in lk.nodes.tolist():
            if n in seen:
                raise ValueError(f"node {n} is in links '{seen[n]}' and '{lk.name}': a node can be tied only once")
            if n in base:
                raise ValueError(f"link '{lk.name}' contains support (base) node {n}")
            seen[n] = lk.name
 
 
def link_ids(mesh, links, first_id=None):
    """{link name: (ref node id, rot node id)} in CalculiX numbering."""
    first = mesh.n_nodes + 1 if first_id is None else first_id
    return {lk.name: (first + 2 * k, first + 2 * k + 1) for k, lk in enumerate(links)}
 
 
def link_lines(mesh, links, first_id=None):
    """.inp text: the reference/rotation nodes and the *EQUATION block. Put it before *STEP.
 
    u_i = u_ref + theta x (x_i - x_ref)   for every patch node i (3 equations per node):
        ux = urx + ty*rz - tz*ry ;  uy = ury + tz*rx - tx*rz ;  uz = urz + tx*ry - ty*rx
    """
    if not links:
        return []
    check_links(mesh, links)
    ids = link_ids(mesh, links, first_id)
    L = ["*NODE"]
    for lk in links:
        ref, rot = ids[lk.name]
        x, y, z = lk.ref_xyz
        L += [f"{ref}, {x:.10g}, {y:.10g}, {z:.10g}", f"{rot}, {x:.10g}, {y:.10g}, {z:.10g}"]
    L.append("*EQUATION")
    for lk in links:
        ref, rot = ids[lk.name]
        for i in lk.nodes:
            rx, ry, rz = mesh.nodes[i] - lk.ref_xyz
            n = int(i) + 1
            L += ["4", f"{n}, 1, 1., {ref}, 1, -1., {rot}, 2, {-rz:.10g}, {rot}, 3, {ry:.10g}"]
            L += ["4", f"{n}, 2, 1., {ref}, 2, -1., {rot}, 3, {-rx:.10g}, {rot}, 1, {rz:.10g}"]
            L += ["4", f"{n}, 3, 1., {ref}, 3, -1., {rot}, 1, {-ry:.10g}, {rot}, 2, {rx:.10g}"]
    return L
 