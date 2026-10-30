import sys, gmsh
from geometry.default_generator import load_params, build_default

gmsh.initialize()
params = load_params()
groups, thickness = build_default(params)
print("Groups:", groups)
print("Thickness (m):", thickness)

gmsh.option.setNumber("Mesh.MeshSizeMax", 1.0)     # element size (m)
gmsh.model.mesh.generate(2)                         # 2D surface mesh
n_nodes = len(gmsh.model.mesh.getNodes()[0])
n_tri = sum(len(t) for t in gmsh.model.mesh.getElements(2)[1])
print(f"Mesh: {n_nodes} nodes, {n_tri} elements")

if "-nopopup" not in sys.argv:
    gmsh.option.setNumber("Geometry.Surfaces", 1)       # show surfaces
    gmsh.option.setNumber("Mesh.SurfaceFaces", 1)       # coloured faces
    gmsh.option.setNumber("Mesh.SurfaceEdges", 1)       # show mesh lines
    gmsh.fltk.run()
gmsh.finalize()