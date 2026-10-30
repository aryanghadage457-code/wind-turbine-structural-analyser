
import json
from pathlib import Path

import gmsh


# ============================================================
# 1. LOAD PROJECT CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

CONFIG_FILE = ROOT / "data" / "default_turbine.json"
STEP_FILE = ROOT / "hollow_tower.step"

with open(CONFIG_FILE, "r", encoding="utf-8") as file:
    data = json.load(file)

tower = data["tower"]

HEIGHT = float(tower["height"])
BASE_DIAMETER = float(tower["base_outer_diameter"])
TOP_DIAMETER = float(tower["top_outer_diameter"])
BASE_THICKNESS = float(tower["base_wall_thickness"])
TOP_THICKNESS = float(tower["top_wall_thickness"])

SECTIONS = tower["sections"]

TOL = 1e-6


# ============================================================
# 2. VALIDATE CONFIGURATION
# ============================================================

if HEIGHT <= 0:
    raise ValueError("Tower height must be positive.")

if BASE_DIAMETER <= 0 or TOP_DIAMETER <= 0:
    raise ValueError("Tower diameters must be positive.")

if BASE_THICKNESS <= 0 or TOP_THICKNESS <= 0:
    raise ValueError("Wall thicknesses must be positive.")

if BASE_THICKNESS >= BASE_DIAMETER:
    raise ValueError("Base wall thickness is too large.")

if TOP_THICKNESS >= TOP_DIAMETER:
    raise ValueError("Top wall thickness is too large.")

if len(SECTIONS) != int(tower["number_of_sections"]):
    raise ValueError("Incorrect number of tower sections.")

if abs(float(SECTIONS[0]["z_start"])) > TOL:
    raise ValueError("Tower must start at z = 0.")

if abs(float(SECTIONS[-1]["z_end"]) - HEIGHT) > TOL:
    raise ValueError("Tower must end at the configured height.")

for i, section in enumerate(SECTIONS):

    z0 = float(section["z_start"])
    z1 = float(section["z_end"])

    if z1 <= z0:
        raise ValueError(f"Invalid section: {section['name']}")

    if i > 0:
        previous_end = float(SECTIONS[i - 1]["z_end"])

        if abs(z0 - previous_end) > TOL:
            raise ValueError(
                f"Gap or overlap between "
                f"{SECTIONS[i - 1]['name']} and {section['name']}"
            )


# ============================================================
# 3. INTERPOLATE TOWER DIMENSIONS
# ============================================================

def interpolate(a, b, fraction):
    return a + (b - a) * fraction


def dimensions(z):

    fraction = z / HEIGHT

    diameter = interpolate(
        BASE_DIAMETER,
        TOP_DIAMETER,
        fraction
    )

    thickness = interpolate(
        BASE_THICKNESS,
        TOP_THICKNESS,
        fraction
    )

    outer_radius = diameter / 2.0

    # Shell midsurface radius.
    midsurface_radius = outer_radius - thickness / 2.0

    return midsurface_radius, thickness


# ============================================================
# 4. SECTION THICKNESS METADATA
# ============================================================

GROUP_PROPS = {}

for section in SECTIONS:

    name = section["name"]

    z_mid = (
        float(section["z_start"]) +
        float(section["z_end"])
    ) / 2.0

    _, thickness = dimensions(z_mid)

    GROUP_PROPS[name] = thickness


# ============================================================
# 5. CREATE SHELL MIDSURFACE GEOMETRY
# ============================================================

gmsh.initialize()

try:

    gmsh.option.setNumber("General.Terminal", 1)

    gmsh.model.add("NREL_5MW_Tower")

    occ = gmsh.model.occ

    temporary_volumes = []

    # Create one temporary conical frustum for each section.
    # Its lateral face represents the required shell midsurface.

    for section in SECTIONS:

        z0 = float(section["z_start"])
        z1 = float(section["z_end"])

        r0, _ = dimensions(z0)
        r1, _ = dimensions(z1)

        volume = occ.addCone(
            0.0, 0.0, z0,
            0.0, 0.0, z1 - z0,
            r0, r1
        )

        temporary_volumes.append(
            (3, volume)
        )

    occ.synchronize()

    # Identify the lateral surfaces and circular end caps.

    section_surfaces = {}
    caps_to_remove = []

    for i, section in enumerate(SECTIONS):

        name = section["name"]
        volume_tag = temporary_volumes[i][1]

        boundary = gmsh.model.getBoundary(
            [(3, volume_tag)],
            combined=False,
            oriented=False,
            recursive=False
        )

        side_surfaces = []

        z0 = float(section["z_start"])
        z1 = float(section["z_end"])

        for dim, tag in boundary:

            if dim != 2:
                continue

            bbox = gmsh.model.getBoundingBox(dim, tag)

            surface_z_min = bbox[2]
            surface_z_max = bbox[5]

            surface_height = surface_z_max - surface_z_min

            # The lateral surface spans the complete section height.
            if (
                abs(surface_z_min - z0) < TOL
                and abs(surface_z_max - z1) < TOL
            ):
                side_surfaces.append(tag)

            else:
                caps_to_remove.append((2, tag))

        if len(side_surfaces) != 1:
            raise RuntimeError(
                f"{name}: expected one lateral shell surface, "
                f"found {len(side_surfaces)}."
            )

        section_surfaces[name] = side_surfaces

    # Remove temporary volumes, retaining their boundary surfaces.
    occ.remove(
        temporary_volumes,
        recursive=False
    )

    # Remove circular end caps, retaining lateral shell surfaces.
    if caps_to_remove:

        occ.remove(
            caps_to_remove,
            recursive=False
        )

    occ.synchronize()

    # Merge coincident boundary curves between adjacent sections.
    occ.removeAllDuplicates()

    occ.synchronize()


    # ========================================================
    # 6. IDENTIFY FINAL SURFACES
    # ========================================================

    section_surfaces = {}

    all_surfaces = gmsh.model.getEntities(2)

    for section in SECTIONS:

        name = section["name"]

        z0 = float(section["z_start"])
        z1 = float(section["z_end"])

        matching_surfaces = []

        for dim, tag in all_surfaces:

            bbox = gmsh.model.getBoundingBox(dim, tag)

            if (
                abs(bbox[2] - z0) < TOL
                and abs(bbox[5] - z1) < TOL
            ):
                matching_surfaces.append(tag)

        if len(matching_surfaces) != 1:
            raise RuntimeError(
                f"{name}: expected one final shell surface, "
                f"found {len(matching_surfaces)}."
            )

        section_surfaces[name] = matching_surfaces


    # ========================================================
    # 7. CREATE PHYSICAL GROUPS
    # ========================================================

    for name, surfaces in section_surfaces.items():

        group = gmsh.model.addPhysicalGroup(
            2,
            surfaces
        )

        gmsh.model.setPhysicalName(
            2,
            group,
            name
        )

        print(f"{name}: physical surface group created.")


    # ========================================================
    # 8. VERIFY GEOMETRY
    # ========================================================

    all_surfaces = gmsh.model.getEntities(2)
    all_volumes = gmsh.model.getEntities(3)

    if len(all_surfaces) != len(SECTIONS):
        raise RuntimeError(
            f"Expected {len(SECTIONS)} shell surfaces, "
            f"found {len(all_surfaces)}."
        )

    if len(all_volumes) != 0:
        raise RuntimeError(
            f"Expected 0 solid volumes, found {len(all_volumes)}."
        )

    boxes = [
        gmsh.model.getBoundingBox(dim, tag)
        for dim, tag in all_surfaces
    ]

    lowest_z = min(box[2] for box in boxes)
    highest_z = max(box[5] for box in boxes)

    if abs(lowest_z) > TOL:
        raise RuntimeError("Incorrect tower base position.")

    if abs(highest_z - HEIGHT) > TOL:
        raise RuntimeError("Incorrect tower height.")


    # ========================================================
    # 9. EXPORT STEP FILE
    # ========================================================

    gmsh.write(str(STEP_FILE))


    # ========================================================
    # 10. PRINT VERIFICATION SUMMARY
    # ========================================================

    print("\n======================================")
    print("NREL 5-MW TOWER GEOMETRY VERIFICATION")
    print("======================================")

    print(f"Tower height: {HEIGHT:.3f} m")
    print(f"Base outer diameter: {BASE_DIAMETER:.3f} m")
    print(f"Top outer diameter: {TOP_DIAMETER:.3f} m")

    print(f"Lowest Z: {lowest_z:.6f} m")
    print(f"Highest Z: {highest_z:.6f} m")

    print(f"Shell surfaces: {len(all_surfaces)}")
    print(f"Solid volumes: {len(all_volumes)}")

    print("\nSection thickness metadata:")

    for name, thickness in GROUP_PROPS.items():
        print(f"{name}: {thickness:.4f} m")

    print("\nSTEP exported successfully:")
    print(STEP_FILE)


    # ========================================================
    # 11. OPEN GMSH VIEWER
    # ========================================================

    gmsh.fltk.run()

finally:

    gmsh.finalize()

import json
from pathlib import Path

import gmsh


# ============================================================
# 1. LOAD PROJECT CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

CONFIG_FILE = ROOT / "data" / "default_turbine.json"
STEP_FILE = ROOT / "hollow_tower.step"

with open(CONFIG_FILE, "r", encoding="utf-8") as file:
    data = json.load(file)

tower = data["tower"]

HEIGHT = float(tower["height"])
BASE_DIAMETER = float(tower["base_outer_diameter"])
TOP_DIAMETER = float(tower["top_outer_diameter"])
BASE_THICKNESS = float(tower["base_wall_thickness"])
TOP_THICKNESS = float(tower["top_wall_thickness"])

SECTIONS = tower["sections"]

TOL = 1e-6


# ============================================================
# 2. VALIDATE CONFIGURATION
# ============================================================

if HEIGHT <= 0:
    raise ValueError("Tower height must be positive.")

if BASE_DIAMETER <= 0 or TOP_DIAMETER <= 0:
    raise ValueError("Tower diameters must be positive.")

if BASE_THICKNESS <= 0 or TOP_THICKNESS <= 0:
    raise ValueError("Wall thicknesses must be positive.")

if BASE_THICKNESS >= BASE_DIAMETER:
    raise ValueError("Base wall thickness is too large.")

if TOP_THICKNESS >= TOP_DIAMETER:
    raise ValueError("Top wall thickness is too large.")

if len(SECTIONS) != int(tower["number_of_sections"]):
    raise ValueError("Incorrect number of tower sections.")

if abs(float(SECTIONS[0]["z_start"])) > TOL:
    raise ValueError("Tower must start at z = 0.")

if abs(float(SECTIONS[-1]["z_end"]) - HEIGHT) > TOL:
    raise ValueError("Tower must end at the configured height.")

for i, section in enumerate(SECTIONS):

    z0 = float(section["z_start"])
    z1 = float(section["z_end"])

    if z1 <= z0:
        raise ValueError(f"Invalid section: {section['name']}")

    if i > 0:
        previous_end = float(SECTIONS[i - 1]["z_end"])

        if abs(z0 - previous_end) > TOL:
            raise ValueError(
                f"Gap or overlap between "
                f"{SECTIONS[i - 1]['name']} and {section['name']}"
            )


# ============================================================
# 3. INTERPOLATE TOWER DIMENSIONS
# ============================================================

def interpolate(a, b, fraction):
    return a + (b - a) * fraction


def dimensions(z):

    fraction = z / HEIGHT

    diameter = interpolate(
        BASE_DIAMETER,
        TOP_DIAMETER,
        fraction
    )

    thickness = interpolate(
        BASE_THICKNESS,
        TOP_THICKNESS,
        fraction
    )

    outer_radius = diameter / 2.0

    # Shell midsurface radius.
    midsurface_radius = outer_radius - thickness / 2.0

    return midsurface_radius, thickness


# ============================================================
# 4. SECTION THICKNESS METADATA
# ============================================================

GROUP_PROPS = {}

for section in SECTIONS:

    name = section["name"]

    z_mid = (
        float(section["z_start"]) +
        float(section["z_end"])
    ) / 2.0

    _, thickness = dimensions(z_mid)

    GROUP_PROPS[name] = thickness


# ============================================================
# 5. CREATE SHELL MIDSURFACE GEOMETRY
# ============================================================

gmsh.initialize()

try:

    gmsh.option.setNumber("General.Terminal", 1)

    gmsh.model.add("NREL_5MW_Tower")

    occ = gmsh.model.occ

    temporary_volumes = []

    # Create one temporary conical frustum for each section.
    # Its lateral face represents the required shell midsurface.

    for section in SECTIONS:

        z0 = float(section["z_start"])
        z1 = float(section["z_end"])

        r0, _ = dimensions(z0)
        r1, _ = dimensions(z1)

        volume = occ.addCone(
            0.0, 0.0, z0,
            0.0, 0.0, z1 - z0,
            r0, r1
        )

        temporary_volumes.append(
            (3, volume)
        )

    occ.synchronize()

    # Identify the lateral surfaces and circular end caps.

    section_surfaces = {}
    caps_to_remove = []

    for i, section in enumerate(SECTIONS):

        name = section["name"]
        volume_tag = temporary_volumes[i][1]

        boundary = gmsh.model.getBoundary(
            [(3, volume_tag)],
            combined=False,
            oriented=False,
            recursive=False
        )

        side_surfaces = []

        z0 = float(section["z_start"])
        z1 = float(section["z_end"])

        for dim, tag in boundary:

            if dim != 2:
                continue

            bbox = gmsh.model.getBoundingBox(dim, tag)

            surface_z_min = bbox[2]
            surface_z_max = bbox[5]

            surface_height = surface_z_max - surface_z_min

            # The lateral surface spans the complete section height.
            if (
                abs(surface_z_min - z0) < TOL
                and abs(surface_z_max - z1) < TOL
            ):
                side_surfaces.append(tag)

            else:
                caps_to_remove.append((2, tag))

        if len(side_surfaces) != 1:
            raise RuntimeError(
                f"{name}: expected one lateral shell surface, "
                f"found {len(side_surfaces)}."
            )

        section_surfaces[name] = side_surfaces

    # Remove temporary volumes, retaining their boundary surfaces.
    occ.remove(
        temporary_volumes,
        recursive=False
    )

    # Remove circular end caps, retaining lateral shell surfaces.
    if caps_to_remove:

        occ.remove(
            caps_to_remove,
            recursive=False
        )

    occ.synchronize()

    # Merge coincident boundary curves between adjacent sections.
    occ.removeAllDuplicates()

    occ.synchronize()


    # ========================================================
    # 6. IDENTIFY FINAL SURFACES
    # ========================================================

    section_surfaces = {}

    all_surfaces = gmsh.model.getEntities(2)

    for section in SECTIONS:

        name = section["name"]

        z0 = float(section["z_start"])
        z1 = float(section["z_end"])

        matching_surfaces = []

        for dim, tag in all_surfaces:

            bbox = gmsh.model.getBoundingBox(dim, tag)

            if (
                abs(bbox[2] - z0) < TOL
                and abs(bbox[5] - z1) < TOL
            ):
                matching_surfaces.append(tag)

        if len(matching_surfaces) != 1:
            raise RuntimeError(
                f"{name}: expected one final shell surface, "
                f"found {len(matching_surfaces)}."
            )

        section_surfaces[name] = matching_surfaces


    # ========================================================
    # 7. CREATE PHYSICAL GROUPS
    # ========================================================

    for name, surfaces in section_surfaces.items():

        group = gmsh.model.addPhysicalGroup(
            2,
            surfaces
        )

        gmsh.model.setPhysicalName(
            2,
            group,
            name
        )

        print(f"{name}: physical surface group created.")


    # ========================================================
    # 8. VERIFY GEOMETRY
    # ========================================================

    all_surfaces = gmsh.model.getEntities(2)
    all_volumes = gmsh.model.getEntities(3)

    if len(all_surfaces) != len(SECTIONS):
        raise RuntimeError(
            f"Expected {len(SECTIONS)} shell surfaces, "
            f"found {len(all_surfaces)}."
        )

    if len(all_volumes) != 0:
        raise RuntimeError(
            f"Expected 0 solid volumes, found {len(all_volumes)}."
        )

    boxes = [
        gmsh.model.getBoundingBox(dim, tag)
        for dim, tag in all_surfaces
    ]

    lowest_z = min(box[2] for box in boxes)
    highest_z = max(box[5] for box in boxes)

    if abs(lowest_z) > TOL:
        raise RuntimeError("Incorrect tower base position.")

    if abs(highest_z - HEIGHT) > TOL:
        raise RuntimeError("Incorrect tower height.")


    # ========================================================
    # 9. EXPORT STEP FILE
    # ========================================================

    gmsh.write(str(STEP_FILE))


    # ========================================================
    # 10. PRINT VERIFICATION SUMMARY
    # ========================================================

    print("\n======================================")
    print("NREL 5-MW TOWER GEOMETRY VERIFICATION")
    print("======================================")

    print(f"Tower height: {HEIGHT:.3f} m")
    print(f"Base outer diameter: {BASE_DIAMETER:.3f} m")
    print(f"Top outer diameter: {TOP_DIAMETER:.3f} m")

    print(f"Lowest Z: {lowest_z:.6f} m")
    print(f"Highest Z: {highest_z:.6f} m")

    print(f"Shell surfaces: {len(all_surfaces)}")
    print(f"Solid volumes: {len(all_volumes)}")

    print("\nSection thickness metadata:")

    for name, thickness in GROUP_PROPS.items():
        print(f"{name}: {thickness:.4f} m")

    print("\nSTEP exported successfully:")
    print(STEP_FILE)


    # ========================================================
    # 11. OPEN GMSH VIEWER
    # ========================================================

    gmsh.fltk.run()

finally:

    gmsh.finalize()
