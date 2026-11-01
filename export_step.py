"""Export the default turbine to a STEP file, then re-import it as a check.
Usage:  python export_step.py [params.json] [output.step]
"""
import sys, gmsh
from geometry.default_generator import load_params, build_default

args = [a for a in sys.argv[1:] if not a.startswith("-")]
json_path = args[0] if args else "data/default_turbine.json"
out_path = args[1] if len(args) > 1 else "turbine.step"

gmsh.initialize()
gmsh.option.setString("Geometry.OCCTargetUnit", "M")   # numbers are metres: write the file with true mm values

# 1) build and export
groups, thickness = build_default(load_params(json_path))
gmsh.model.occ.synchronize()
n_before = len(gmsh.model.getEntities(2))
gmsh.write(out_path)
print(f"Wrote {out_path} with {n_before} surfaces")

# 2) re-import into a fresh model and compare
gmsh.model.add("reimport")
gmsh.model.occ.importShapes(out_path)
gmsh.model.occ.synchronize()
n_after = len(gmsh.model.getEntities(2))
xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
print(f"Re-imported surfaces: {n_after} (want {n_before})")
print(f"Bounding box (m): x {xmin:.1f} to {xmax:.1f}, "
      f"y {ymin:.1f} to {ymax:.1f}, z {zmin:.1f} to {zmax:.1f}")
gmsh.finalize()