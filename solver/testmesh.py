"""Small deterministic quadratic-cylinder mesh fixture for unit tests only.

Not used by production geometry or analysis workflows.
"""
import numpy as np
from contracts import Mesh


def cylinder_mesh(diameter=2.0, height=10.0, n_circ=24, n_axial=20, order=2):
    if order != 2:
        raise ValueError("testmesh.cylinder_mesh currently supports quadratic S6 triangles only")
    if diameter <= 0 or height <= 0 or n_circ < 3 or n_axial < 1:
        raise ValueError("invalid cylinder mesh dimensions")
    radius = float(diameter) / 2.0
    nodes = []
    corner = {}
    for j in range(n_axial + 1):
        z = height * j / n_axial
        for i in range(n_circ):
            a = 2 * np.pi * i / n_circ
            corner[(i, j)] = len(nodes)
            nodes.append((radius * np.cos(a), radius * np.sin(a), z))
    edge_nodes = {}
    elems = []

    def midpoint(a, b):
        key = tuple(sorted((int(a), int(b))))
        if key in edge_nodes:
            return edge_nodes[key]
        pa, pb = np.asarray(nodes[a]), np.asarray(nodes[b])
        pm = 0.5 * (pa + pb)
        # Circumferential edges lie on a circular section; project their midpoint
        # back to the cylinder so the fixture resembles a curved shell surface.
        if abs(pa[2] - pb[2]) < 1e-12:
            rxy = np.linalg.norm(pm[:2])
            if rxy > 0:
                pm[:2] *= radius / rxy
        idx = len(nodes)
        nodes.append(tuple(pm))
        edge_nodes[key] = idx
        return idx

    for j in range(n_axial):
        for i in range(n_circ):
            ip = (i + 1) % n_circ
            a, b = corner[(i, j)], corner[(ip, j)]
            c, d = corner[(ip, j + 1)], corner[(i, j + 1)]
            for tri in ((a, b, c), (a, c, d)):
                n1, n2, n3 = tri
                elems.append((n1, n2, n3, midpoint(n1, n2), midpoint(n2, n3), midpoint(n3, n1)))
    return Mesh(nodes=np.asarray(nodes, float), elems=np.asarray(elems, int),
                elem_group=np.zeros(len(elems), dtype=int), group_names=["Tower_1"])
