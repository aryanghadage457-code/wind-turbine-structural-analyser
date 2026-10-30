import sys, gmsh
from geometry.default_generator import load_params, build_default

args = [a for a in sys.argv[1:] if not a.startswith("-")]
path = args[0] if args else "data/default_turbine.json"
size = float(args[1]) if len(args) > 1 else 3.0     # element size in metres

gmsh.initialize()
params = load_params(path)
groups, thickness = build_default(params)
print("Groups:", groups)
print("Thickness (m):", thickness)

gmsh.option.setNumber("Mesh.MeshSizeMax", size)
gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)   # finer where the surface curves (blades)
gmsh.option.setNumber("Mesh.MeshSizeMin", 0.15)           # but never smaller than 0.15 m
gmsh.model.mesh.generate(2)                         # 2D surface mesh
n_nodes = len(gmsh.model.mesh.getNodes()[0])
n_tri = sum(len(t) for t in gmsh.model.mesh.getElements(2)[1])
print(f"Mesh: {n_nodes} nodes, {n_tri} elements")

if "-nopopup" not in sys.argv:
    gmsh.option.setNumber("Geometry.Surfaces", 1)
    gmsh.option.setNumber("Mesh.SurfaceFaces", 1)
    gmsh.option.setNumber("Mesh.SurfaceEdges", 1)
    gmsh.fltk.run()
gmsh.finalize()