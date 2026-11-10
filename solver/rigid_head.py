"""rigid_head.py - make whole shell groups (e.g. Nacelle + Hub) ONE rigid body in the CalculiX input.
 
Method: the same linearised rigid-body equations your G.inp already uses (no *RIGID BODY / *COUPLING):
two extra nodes, a reference node R (its DOF 1-3 = translation u_R) and a rotation node T (its DOF 1-3 =
small rotation vector theta, location irrelevant). Every node i of the groups gets
        u_i = u_R + theta x (x_i - x_R)
written as three *EQUATION per node (translations of the shell node only, rotations left free):
        ux:  ux_i - ux_R - (z_i - z_R) thy + (y_i - y_R) thz = 0
        uy:  uy_i - uy_R - (x_i - x_R) thz + (z_i - z_R) thx = 0
        uz:  uz_i - uz_R - (y_i - y_R) thx + (x_i - x_R) thy = 0
(signs checked against the equations in your G.inp). Valid for small rotations (linear analysis).
 
Effect: the grouped shells cannot deform. Their element stresses come out ~0 and mean nothing: report no
stress for them. Loads on their nodes (gravity, extra masses, wind) are carried to R and T and into the
tower through the nodes the head shares with the rest of the model.
 
Usage in write_inp (see the 3 edits in the chat):  rigid_head=("Nacelle", "Hub")
The reference nodes are numbered above n_nodes, so they are not in NALL and ccx_reader.py never sees them.
"""
import numpy as np
 
 
def node_equations(x, ref_pt, node_id, ref_id, rot_id):
    """The three equations (as CalculiX line pairs) for one node at position x."""
    dx, dy, dz = (np.asarray(x, float) - np.asarray(ref_pt, float))
    spec = {  # dof: [(rot dof, coefficient), ...]
        1: [(2, -dz), (3, +dy)],
        2: [(3, -dx), (1, +dz)],
        3: [(1, -dy), (2, +dx)],
    }
    out = []
    for d in (1, 2, 3):
        terms = [(node_id, d, 1.0), (ref_id, d, -1.0)] + [(rot_id, k, c) for k, c in spec[d] if abs(c) > 1e-12]
        out.append(str(len(terms)))
        out.append(", ".join(f"{n}, {k}, {c:.10g}" for n, k, c in terms))
    return out
 
 
def head_nodes(mesh, groups):
    missing = [g for g in groups if g not in mesh.group_names]
    if missing:
        raise ValueError(f"rigid_head: group(s) {missing} not in mesh groups {list(mesh.group_names)}")
    ids = [mesh.group_names.index(g) for g in groups]
    nodes = np.unique(mesh.elems[np.isin(mesh.elem_group, ids)])
    base = mesh.node_sets.get("base") if hasattr(mesh, "node_sets") else None
    if base is not None and len(np.intersect1d(nodes, base)):
        raise ValueError("rigid_head: some head nodes are in the fixed base set; the rigid body would be clamped")
    return nodes
 
 
def default_ref_point(mesh):
    """Tower-top axis point (0, 0, z_top) if there are Tower_* groups, else the head centroid."""
    tw = [i for i, n in enumerate(mesh.group_names) if n.startswith("Tower_")]
    if tw:
        zt = mesh.nodes[np.unique(mesh.elems[np.isin(mesh.elem_group, tw)])][:, 2].max()
        return np.array([0.0, 0.0, zt])
    return None
 
 
def rigid_head_lines(mesh, groups=("Nacelle", "Hub"), first_id=None, ref_point=None):
    """Return (lines, info): the *NODE and *EQUATION text and a dict with ids/counts.
    first_id = id of the reference node (rotation node gets first_id + 1); default n_nodes + 1."""
    nodes = head_nodes(mesh, groups)
    if len(nodes) < 10:
        raise ValueError(f"rigid_head: only {len(nodes)} nodes found for {groups}")
    first_id = mesh.n_nodes + 1 if first_id is None else int(first_id)
    ref_id, rot_id = first_id, first_id + 1
    if ref_point is None:
        ref_point = default_ref_point(mesh)
    ref_point = mesh.nodes[nodes].mean(axis=0) if ref_point is None else np.asarray(ref_point, float)
    L = ["*NODE",
         f"{ref_id}, {ref_point[0]:.10g}, {ref_point[1]:.10g}, {ref_point[2]:.10g}",
         f"{rot_id}, {ref_point[0]:.10g}, {ref_point[1]:.10g}, {ref_point[2]:.10g}",
         "*EQUATION"]
    for n in nodes:
        L += node_equations(mesh.nodes[n], ref_point, int(n) + 1, ref_id, rot_id)
    info = dict(ref_id=ref_id, rot_id=rot_id, ref_point=ref_point, nodes=nodes, n_nodes=len(nodes),
                n_equations=3 * len(nodes), groups=tuple(groups))
    return L, info
 