"""Connectivity + free-edge check (run after meshing)."""
import sys, collections, gmsh
import numpy as np
from geometry.default_generator import load_params, build_default

path = sys.argv[1] if len(sys.argv) > 1 else "data/default_turbine.json"
gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
build_default(load_params(path))
gmsh.option.setNumber("Mesh.MeshSizeMax", 1.0)
gmsh.model.mesh.generate(2)
tags, coords, _ = gmsh.model.mesh.getNodes()
xyz = {int(t): coords[3*i:3*i+3] for i, t in enumerate(tags)}
et, _, en = gmsh.model.mesh.getElements(2)
tri = np.array(en[0], dtype=int).reshape(-1, 3)

# connected components (union-find on nodes)
par = {}
def f(a):
    while par.setdefault(a, a) != a:
        par[a] = par[par[a]]; a = par[a]
    return a
for t in tri:
    for k in (1, 2): par[f(t[k])] = f(t[0])
print("connected components:", len({f(n) for n in set(tri.ravel())}), "(want 1)")

# free edges
cnt = collections.Counter()
for t in tri:
    for a, b in ((0,1),(1,2),(2,0)): cnt[tuple(sorted((t[a], t[b])))] += 1
free = [e for e, c in cnt.items() if c == 1]
zs = sorted({round(float(xyz[e[0]][2]), 2) for e in free})
print("free edges:", len(free), "at heights z =", zs, "(want only z=0, the base)")
gmsh.finalize()