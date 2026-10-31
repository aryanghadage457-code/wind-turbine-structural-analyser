
import gmsh
from geometry.default_generator import load_params, build_default
from solver.mesh import build_mesh
gmsh.initialize()

try:
    params = load_params()

    groups, thickness = build_default(
        params,
        tower_only=True
    )
    mesh = build_mesh(
        groups=groups,
        base_curves=[],
        total_area=0.0,
        create_groups=False
    )

    print("\nMesh generation completed!")
    print("Returned mesh object:", mesh)

    print("\nGenerated component groups:")

    for name, surfaces in groups.items():
        print(f"{name}: {len(surfaces)} surfaces")

    print("\nThickness values:")

    for name, value in thickness.items():
        print(f"{name}: {value} m")

    print("\nTotal surfaces:", len(gmsh.model.getEntities(2)))
    print("Surface details:")

    for dim, tag in gmsh.model.getEntities(2):
        print(
            "Surface:", tag,
            "Type:", gmsh.model.getType(dim, tag),
            "Bounding box:", gmsh.model.getBoundingBox(dim, tag)
        )

    print("Volumes:", gmsh.model.getEntities(3))
    print("Curves:", len(gmsh.model.getEntities(1)))   
    

    gmsh.fltk.run()

finally:
    gmsh.finalize()
