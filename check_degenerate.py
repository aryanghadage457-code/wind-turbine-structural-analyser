
import gmsh
from geometry.default_generator import load_params, build_default

gmsh.initialize()

try:
    params = load_params()
    groups, thickness = build_default(params)

    curve_tag = 119

    curves = {tag for dim, tag in gmsh.model.getEntities(1)}

    if curve_tag not in curves:
        print("Curve does not exist.")
    else:
        print("Curve:", curve_tag)
        print("Type:", gmsh.model.getType(1, curve_tag))
        print("Length:", gmsh.model.occ.getMass(1, curve_tag))
        print("Bounding box:", gmsh.model.getBoundingBox(1, curve_tag))
        print("Adjacent surfaces:",
              gmsh.model.getAdjacencies(1, curve_tag)[0])

finally:
    gmsh.finalize()
