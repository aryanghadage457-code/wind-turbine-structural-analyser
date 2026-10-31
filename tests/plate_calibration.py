"""Flat-plate bending test: which layer is the +normal face? And do the extrapolated surface stresses match beam theory?"""
import numpy as np, gmsh, sys
sys.path.insert(0, ".")
from contracts import Mesh, Settings, LoadSet
from solver.ccx_writer import write_inp
from solver.ccx_runner import run_ccx
from solver import ccx_reader as R
 
L, b, t, P = 2.0, 0.4, 0.02, 1000.0
gmsh.initialize(); gmsh.option.setNumber("General.Terminal", 0)
gmsh.model.occ.addRectangle(0, -b/2, 0, L, b); gmsh.model.occ.synchronize()
gmsh.option.setNumber("Mesh.MeshSizeMax", 0.1); gmsh.option.setNumber("Mesh.MeshSizeMin", 0.05)
gmsh.model.mesh.generate(2); gmsh.model.mesh.setOrder(2)
tags, xyz, _ = gmsh.model.mesh.getNodes(); X = np.array(xyz).reshape(-1, 3); idx = {int(tg): i for i, tg in enumerate(tags)}
et, _, en = gmsh.model.mesh.getElements(2); E = np.array([[idx[int(n)] for n in r] for r in np.array(en[0]).reshape(-1, 6)])
gmsh.finalize()
mesh = Mesh(X, E, np.zeros(len(E), int), ["Plate"])
mesh.node_sets["base"] = np.where(X[:, 0] < 1e-9)[0]
print("element normals (z component) min/max:", R.element_normals(mesh)[:, 2].min(), R.element_normals(mesh)[:, 2].max(), "(+1 means +z normal)")
tip = np.where(X[:, 0] > L - 1e-9)[0]
f = np.zeros((len(X), 3)); f[tip, 2] = -P / len(tip)
loads = LoadSet(f, [0, 0, 0], [0, 0, 0], f.sum(axis=0), [0, 0, 0], case="W", v_ref=1.0)
S = Settings(); write_inp("out/plate.inp", mesh, {"Plate": t}, S, case="W", loads=loads)
dat = run_ccx("out/plate.inp")
d = R.read_dat(dat, len(X), len(E))
cent = X[E[:, :3]].mean(axis=1)
sel = np.argmin((cent[:, 0] - 1.0) ** 2 + cent[:, 1] ** 2)          # element near x = 1, y = 0
Sel = d["S"][sel].reshape(3, 3, 6).mean(axis=1)                      # layers 0,1,2
print("layer stresses (sxx, syy) at x = 1 m:")
for l in range(3): print("  layer", l, Sel[l, :2] / 1e6, "MPa")
hand = 6 * P * (L - cent[sel, 0]) / (b * t ** 2)
print("beam theory surface stress at x=%.2f: %.2f MPa" % (cent[sel, 0], hand / 1e6))
plus, minus, mid = R.surface_stresses(d["S"], plus_layer=2)
print("extrapolated +normal face sxx: %.2f MPa, -normal face sxx: %.2f MPa, mid: %.2f MPa" % (plus[sel, 0] / 1e6, minus[sel, 0] / 1e6, mid[sel, 0] / 1e6))
print("reaction Fz total = %.3f N (expected +%.0f)" % (d["rf"][:, 2].sum(), P))
tipu = d["U"][tip, 2].mean(); EI = S.E * b * t ** 3 / 12
print("tip deflection %.4e m, beam theory %.4e m" % (tipu, -P * L ** 3 / (3 * EI)))
 