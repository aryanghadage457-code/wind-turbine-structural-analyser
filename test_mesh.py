import time, json, gmsh
from pathlib import Path
from geometry.default_generator import build_default
gmsh.initialize()
build_default(json.loads(Path("data/default_turbine.json").read_text(encoding="utf-8").replace("\u00a0", " ")))
for k, v in [("MeshSizeMax", 3.0), ("MeshSizeFromCurvature", 12), ("MeshSizeMin", 0.15)]:
    gmsh.option.setNumber("Mesh." + k, v)
t = time.time(); gmsh.model.mesh.generate(2); print("mesh seconds:", time.time() - t)