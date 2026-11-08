"""machinery.py - apply an extra (machinery) mass as vertical nodal forces on a CHOSEN set of nodes.

The weight m*g acts at a point (px, py) that may be off-centre. For a vertical force only the horizontal
position matters, so the nodal forces F_i = -m*g*w_i are chosen with
    sum(w_i) = 1,  sum(w_i x_i) = px,  sum(w_i y_i) = py      (closest to an equal share)
which gives exactly the same force AND moment about any point as the weight acting at (px, py).
Because z is not used, the nodes may be a flat ring (the tower-top / yaw ring).
Negative weights (an upward force on part of the ring) are normal when the point is far off-centre:
they are the couple the bedplate passes into the yaw bearing.
"""
import numpy as np


def vertical_load_weights(xy, point_xy):
    xy = np.asarray(xy, float)
    N = len(xy)
    A = np.vstack([np.ones(N), xy[:, 0], xy[:, 1]])
    rhs = np.array([0.0, point_xy[0] - xy[:, 0].mean(), point_xy[1] - xy[:, 1].mean()])
    return 1.0 / N + A.T @ np.linalg.solve(A @ A.T, rhs)


def machinery_forces(mesh, group, mass_kg, point_xy, g=9.81):
    """(N,3) nodal forces for case G and a small info dict. `group` is the name of the group whose nodes carry the weight."""
    nodes = np.unique(mesh.elems[mesh.elem_group == mesh.group_names.index(group)])
    w = vertical_load_weights(mesh.nodes[nodes, :2], point_xy)
    F = np.zeros((mesh.n_nodes, 3))
    F[nodes, 2] = -mass_kg * g * w
    return F, dict(n_nodes=len(nodes), min_rel_weight=float(w.min() * len(nodes)), max_rel_weight=float(w.max() * len(nodes)))