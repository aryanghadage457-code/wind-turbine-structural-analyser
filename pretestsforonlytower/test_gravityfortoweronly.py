
import gmsh

from geometry.default_generator import load_params, build_default
from solver.mesh import build_mesh
from solver.ccx_writer import write_inp
from contracts import Settings


gmsh.initialize()

try:
    # 1. Generate tower-only geometry
    params = load_params()

    groups, thickness = build_default(
        params,
        tower_only=True
    )

    # 2. Generate the tower mesh
    mesh = build_mesh(
        groups=groups,
        base_curves=[],
        total_area=0.0,
        create_groups=False
    )

    print("\nTower mesh generated successfully!")

    # 3. Create temporary material settings
    settings = Settings()
    settings.validate()

    # 4. Use the thickness values from the geometry generator
    props = thickness

    # 5. Generate the CalculiX input file
    write_inp(
        path="tower_gravity.inp",
        mesh=mesh,
        props=props,
        s=settings
    )
    # 6. Calculate theoretical weight using the actual mesh
    import numpy as np

    total_volume = 0.0

    for e, element in enumerate(mesh.elems):

        p = mesh.nodes[element]

        # Calculate triangular element area
        area = 0.5 * np.linalg.norm(
            np.cross(p[1] - p[0], p[2] - p[0])
        )

        group_index = mesh.elem_group[e]
        group_name = mesh.group_names[group_index]

        thickness = props[group_name]

        total_volume += area * thickness

    theoretical_mass = settings.rho * total_volume
    theoretical_weight = theoretical_mass * 9.81

    print("\n--- Mesh-based weight check ---")
    print(f"Shell volume: {total_volume:.4f} m^3")
    print(f"Mass: {theoretical_mass:.2f} kg")
    print(f"Weight: {theoretical_weight:.2f} N")

    print("\nCalculiX input file generated successfully!")
    print("File: tower_gravity.inp")
    # 6. Run CalculiX
    import subprocess
    import os

    os.makedirs("runs", exist_ok=True)

    # Move the generated input file into runs/
    os.replace(
        "tower_gravity.inp",
        "runs/tower_gravity.inp"
    )

    result = subprocess.run(
        ["ccx", "tower_gravity"],
        cwd="runs",
        capture_output=True,
        text=True
    )

    print("\n--- CalculiX Output ---")
    print(result.stdout[-3000:])

    if result.stderr:
        print("\n--- CalculiX Errors ---")
        print(result.stderr[-1000:])

    if result.returncode != 0:
        raise RuntimeError("CalculiX analysis failed!")

    print("\nCalculiX analysis completed successfully!")
    print("Check the runs folder for tower_gravity.dat")

finally:
    gmsh.finalize()
