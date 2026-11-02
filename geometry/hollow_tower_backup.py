
import json
from pathlib import Path

import gmsh


# ==================================================
# 1. LOAD CONFIGURATION
# ==================================================

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "data" / "default_turbine.json"
STEP_FILE = ROOT / "hollow_tower.step"
MSH_FILE = ROOT / "hollow_tower.msh"

with open(CONFIG, "r", encoding="utf-8") as f:
    data = json.load(f)

tower = data["tower"]
height = float(tower["height"])
d_base = float(tower["base_outer_diameter"])
d_top = float(tower["top_outer_diameter"])
t_base = float(tower["base_wall_thickness"])
t_top = float(tower["top_wall_thickness"])
sections = tower["sections"]


def interpolate(a, b, fraction):
    return a + (b - a) * fraction


def dimensions(z):
    fraction = z / height
    diameter = interpolate(d_base, d_top, fraction)
    thickness = interpolate(t_base, t_top, fraction)
    return diameter / 2, diameter / 2 - thickness, thickness


# ==================================================
# 2. CREATE ONE CONNECTED TOWER WITH SECTION BOUNDARIES
# ==================================================

gmsh.initialize()

try:
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("Wind_Turbine_Tower")
    occ = gmsh.model.occ

    outer_solids = []
    inner_solids = []

    for section in sections:
        z0 = float(section["z_start"])
        z1 = float(section["z_end"])

        r0, ri0, _ = dimensions(z0)
        r1, ri1, _ = dimensions(z1)

        outer = occ.addCone(
            0, 0, z0,
            0, 0, z1 - z0,
            r0, r1
        )

        inner = occ.addCone(
            0, 0, z0,
            0, 0, z1 - z0,
            ri0, ri1
        )

        outer_solids.append((3, outer))
        inner_solids.append((3, inner))

    # Fragment adjacent section solids so they share topology
    # at their boundaries instead of creating separate bodies.
    fragmented, _ = occ.fragment(
        outer_solids,
        outer_solids[1:],
        removeObject=True,
        removeTool=False
    )

    # Rebuild the full outer and inner geometry from the section
    # list and cut the hollow interiors.
    occ.synchronize()

    outer_entities = gmsh.model.getEntities(3)
    inner_tags = [tag for dim, tag in inner_solids]

    # Build the four hollow sections independently.
    # Each section retains its own exterior conical face.
    # OCC fragment/fuse behaviour can vary by version, so check
    # the result before assigning groups.
    occ.remove(outer_entities, recursive=True)
    occ.synchronize()

    section_volumes = []

    for section in sections:
        z0 = float(section["z_start"])
        z1 = float(section["z_end"])
        r0, ri0, _ = dimensions(z0)
        r1, ri1, _ = dimensions(z1)

        outer = occ.addCone(
            0, 0, z0,
            0, 0, z1 - z0,
            r0, r1
        )
        inner = occ.addCone(
            0, 0, z0,
            0, 0, z1 - z0,
            ri0, ri1
        )

        result, _ = occ.cut(
            [(3, outer)],
            [(3, inner)],
            removeObject=True,
            removeTool=True
        )
        section_volumes.extend(result)

    occ.synchronize()

    # Keep section boundaries: do not fuse the sections.
    # The resulting geometry is suitable for checking and
    # meshing, but shared-node connectivity must be verified.
    all_volumes = gmsh.model.getEntities(3)

    if len(all_volumes) != len(sections):
        raise RuntimeError(
            f"Expected {len(sections)} section volumes; "
            f"found {len(all_volumes)}."
        )

    # ==================================================
    # 3. CREATE ONE PHYSICAL SURFACE GROUP PER SECTION
    # ==================================================

    for section in sections:
        name = section["name"]
        z0 = float(section["z_start"])
        z1 = float(section["z_end"])

        candidate_surfaces = []

        for dim, tag in gmsh.model.getEntities(2):
            xmin, ymin, zmin, xmax, ymax, zmax = (
                gmsh.model.getBoundingBox(dim, tag)
            )

            # Select conical surfaces belonging to this height
            # interval. Exclude horizontal end faces.
            lies_in_section = (
                zmin >= z0 - 1e-4
                and zmax <= z1 + 1e-4
                and zmax - zmin > 0.5 * (z1 - z0)
            )

            if lies_in_section:
                candidate_surfaces.append(tag)

        if not candidate_surfaces:
            raise RuntimeError(
                f"No conical surface found for {name}."
            )

        group = gmsh.model.addPhysicalGroup(
            2, candidate_surfaces
        )
        gmsh.model.setPhysicalName(2, group, name)

        print(
            f"{name}: physical group created "
            f"for z={z0:.2f} to {z1:.2f} m"
        )

    # ==================================================
    # 4. MESH, EXPORT AND CHECK
    # ==================================================

    gmsh.option.setNumber("Mesh.MeshSizeMax", 2.0)
    gmsh.option.setNumber("Mesh.MeshSizeMin", 0.5)

    gmsh.model.mesh.generate(2)
    gmsh.write(str(MSH_FILE))
    gmsh.write(str(STEP_FILE))

    print("\nGenerated files:")
    print(STEP_FILE)
    print(MSH_FILE)


    # Check whether adjacent tower sections share mesh nodes
    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    coords = node_coords.reshape(-1, 3)

    print("\n--- Tower mesh height check ---")
    print(f"Lowest Z:  {coords[:, 2].min():.6f} m")
    print(f"Highest Z: {coords[:, 2].max():.6f} m")
    print(f"Total height: {coords[:, 2].max() - coords[:, 2].min():.6f} m")

    print("\nSection boundary node counts:")
    for z in [21.9, 43.8, 65.7]:
        count = sum(abs(zc - z) < 1e-5 for zc in coords[:, 2])
        print(f"z = {z:.1f} m: {count} mesh nodes")


    gmsh.fltk.run()

finally:
    gmsh.finalize()