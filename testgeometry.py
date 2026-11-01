
import gmsh
import math
from collections import defaultdict

from geometry.default_generator import load_params, build_default


# =========================================================
# CONFIGURATION
# =========================================================

EXPECTED_GROUPS = {
    "Tower_1",
    "Tower_2",
    "Tower_3",
    "Tower_4",
    "Nacelle",
    "Hub",
    "Blade_1",
    "Blade_2",
    "Blade_3",
}


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def get_surface_boundary_curves(surface_tag):
    """Return all boundary curves of a surface."""

    boundary = gmsh.model.getBoundary(
        [(2, surface_tag)],
        combined=False,
        oriented=False,
        recursive=False
    )

    return {
        abs(tag)
        for dim, tag in boundary
        if dim == 1
    }


def get_curve_adjacent_surfaces(curve_tag):
    """Return unique surfaces directly connected to a curve."""

    upward, downward = gmsh.model.getAdjacencies(1, curve_tag)

    return set(int(tag) for tag in upward)


def get_surface_group_map(groups):
    """Map every surface tag to its physical group name."""

    surface_to_group = {}

    for group_name, surface_tags in groups.items():
        for surface_tag in surface_tags:
            surface_to_group[surface_tag] = group_name

    return surface_to_group


def get_curve_info(curve_tag):
    """Return bounding box, centre and length of a curve."""

    bbox = gmsh.model.getBoundingBox(1, curve_tag)
    centre = gmsh.model.occ.getCenterOfMass(1, curve_tag)
    length = gmsh.model.occ.getMass(1, curve_tag)

    return bbox, centre, length


def get_surface_info(surface_tag):
    """Return type, bounding box, centre and area."""

    surface_type = gmsh.model.getType(2, surface_tag)
    bbox = gmsh.model.getBoundingBox(2, surface_tag)
    centre = gmsh.model.occ.getCenterOfMass(2, surface_tag)
    area = gmsh.model.occ.getMass(2, surface_tag)

    return surface_type, bbox, centre, area


# =========================================================
# MAIN GEOMETRY CHECK
# =========================================================

def main():

    gmsh.initialize()

    try:

        gmsh.option.setNumber("General.Terminal", 1)

        # -------------------------------------------------
        # 1. Generate geometry
        # -------------------------------------------------

        print("\n" + "=" * 70)
        print("GENERATING TURBINE GEOMETRY")
        print("=" * 70)

        params = load_params()

        groups, thickness = build_default(params)

        surface_to_group = get_surface_group_map(groups)

        print("Geometry generation completed.")

        # -------------------------------------------------
        # 2. Check physical groups
        # -------------------------------------------------

        print("\n" + "=" * 70)
        print("1. PHYSICAL GROUP CHECK")
        print("=" * 70)

        actual_groups = set(groups.keys())

        missing_groups = EXPECTED_GROUPS - actual_groups
        unexpected_groups = actual_groups - EXPECTED_GROUPS

        if missing_groups:
            print("FAIL: Missing groups:", sorted(missing_groups))
        else:
            print("PASS: All expected groups exist.")

        if unexpected_groups:
            print("WARNING: Unexpected groups:", sorted(unexpected_groups))

        for group_name in sorted(groups):

            surfaces = groups[group_name]

            print(f"{group_name}: {len(surfaces)} surfaces")

            if not surfaces:
                print("  FAIL: Group contains no surfaces.")

        # -------------------------------------------------
        # 3. Check thickness assignments
        # -------------------------------------------------

        print("\n" + "=" * 70)
        print("2. THICKNESS CHECK")
        print("=" * 70)

        thickness_ok = True

        for group_name in sorted(groups):

            if group_name not in thickness:
                print(f"FAIL: No thickness assigned to {group_name}")
                thickness_ok = False
                continue

            value = thickness[group_name]

            if value <= 0:
                print(f"FAIL: Invalid thickness for {group_name}: {value}")
                thickness_ok = False
            else:
                print(f"{group_name}: {value:.4f} m")

        if thickness_ok:
            print("PASS: All groups have positive thickness values.")

        # -------------------------------------------------
        # 4. Check that all group surfaces exist
        # -------------------------------------------------

        print("\n" + "=" * 70)
        print("3. SURFACE EXISTENCE CHECK")
        print("=" * 70)

        existing_surfaces = {
            tag for dim, tag in gmsh.model.getEntities(2)
        }

        invalid_surfaces = []

        for group_name, surface_tags in groups.items():

            for surface_tag in surface_tags:

                if surface_tag not in existing_surfaces:
                    invalid_surfaces.append(
                        (group_name, surface_tag)
                    )

        if invalid_surfaces:
            print("FAIL: Invalid surface references:")
            for item in invalid_surfaces:
                print(" ", item)
        else:
            print("PASS: All grouped surfaces exist in the geometry.")

        # -------------------------------------------------
        # 5. Build curve-to-surface connectivity
        # -------------------------------------------------

        curve_to_surfaces = defaultdict(set)

        for group_name, surface_tags in groups.items():

            for surface_tag in surface_tags:

                curves = get_surface_boundary_curves(surface_tag)

                for curve_tag in curves:
                    curve_to_surfaces[curve_tag].add(surface_tag)

        print("\n" + "=" * 70)
        print("4. CURVE CONNECTIVITY SUMMARY")
        print("=" * 70)

        one_surface = []
        two_surfaces = []
        more_than_two = []

        for curve_tag in sorted(curve_to_surfaces):

            adjacent = curve_to_surfaces[curve_tag]

            if len(adjacent) == 1:
                one_surface.append(curve_tag)

            elif len(adjacent) == 2:
                two_surfaces.append(curve_tag)

            else:
                more_than_two.append(curve_tag)

        print(f"Total unique boundary curves: {len(curve_to_surfaces)}")
        print(f"Curves shared by 1 surface: {len(one_surface)}")
        print(f"Curves shared by 2 surfaces: {len(two_surfaces)}")
        print(f"Curves shared by more than 2 surfaces: {len(more_than_two)}")

        # -------------------------------------------------
        # 6. Check non-manifold curves
        # -------------------------------------------------

        print("\n" + "=" * 70)
        print("5. NON-MANIFOLD CURVE CHECK")
        print("=" * 70)

        if not more_than_two:

            print("PASS: No curves are shared by more than two grouped surfaces.")

        else:

            print("FAIL: Non-manifold curves detected.")

            for curve_tag in more_than_two:

                adjacent = sorted(curve_to_surfaces[curve_tag])

                group_names = sorted({
                    surface_to_group[s]
                    for s in adjacent
                    if s in surface_to_group
                })

                bbox, centre, length = get_curve_info(curve_tag)

                print(f"\nCurve {curve_tag}")
                print("  Adjacent surfaces:", adjacent)
                print("  Groups:", group_names)
                print("  Length:", length)
                print("  Centre:", centre)
                print("  Bounding box:", bbox)

        # -------------------------------------------------
        # 7. Check tower-nacelle interface
        # -------------------------------------------------

        print("\n" + "=" * 70)
        print("6. TOWER-NACELLE CONNECTION")
        print("=" * 70)

        interface_curves = []

        for curve_tag, surface_tags in curve_to_surfaces.items():

            group_names = {
                surface_to_group[s]
                for s in surface_tags
                if s in surface_to_group
            }

            if "Tower_4" in group_names and "Nacelle" in group_names:
                interface_curves.append(curve_tag)

        if interface_curves:

            print("PASS: Tower_4 and Nacelle share boundary curves.")

            for curve_tag in sorted(interface_curves):

                bbox, centre, length = get_curve_info(curve_tag)

                print(f"\nCurve {curve_tag}")
                print("  Centre:", centre)
                print("  Length:", length)
                print("  Bounding box:", bbox)

        else:

            print("FAIL: Tower_4-Nacelle connection was not found.")

        # -------------------------------------------------
        # 8. Check blade-hub connections
        # -------------------------------------------------

        print("\n" + "=" * 70)
        print("7. BLADE-HUB CONNECTIONS")
        print("=" * 70)

        hub_curves = set()

        if "Hub" in groups:

            for surface_tag in groups["Hub"]:
                hub_curves.update(
                    get_surface_boundary_curves(surface_tag)
                )

        for blade_name in ["Blade_1", "Blade_2", "Blade_3"]:

            blade_curves = set()

            if blade_name in groups:

                for surface_tag in groups[blade_name]:
                    blade_curves.update(
                        get_surface_boundary_curves(surface_tag)
                    )

            shared = blade_curves.intersection(hub_curves)

            if shared:

                print(f"PASS: {blade_name} is connected to Hub.")
                print("  Shared curves:", sorted(shared))

            else:

                print(f"FAIL: {blade_name} is NOT connected to Hub.")

        # -------------------------------------------------
        # 9. Investigate single-surface curves
        # -------------------------------------------------

        print("\n" + "=" * 70)
        print("8. SINGLE-SURFACE CURVES")
        print("=" * 70)

        print(
            "These curves belong to only one grouped surface. "
            "They may be expected open boundaries."
        )

        curves_by_group = defaultdict(list)

        for curve_tag in sorted(one_surface):

            surface_tags = curve_to_surfaces[curve_tag]

            group_names = sorted({
                surface_to_group[s]
                for s in surface_tags
                if s in surface_to_group
            })

            bbox, centre, length = get_curve_info(curve_tag)

            for group_name in group_names:
                curves_by_group[group_name].append(curve_tag)

            print(f"\nCurve {curve_tag}")
            print("  Group:", group_names)
            print("  Length:", length)
            print("  Centre:", centre)
            print("  Bounding box:", bbox)

        print("\nSingle-surface curves by group:")

        for group_name in sorted(curves_by_group):

            print(
                f"  {group_name}: {len(curves_by_group[group_name])}"
            )

        # -------------------------------------------------
        # 10. Blade planar surface investigation
        # -------------------------------------------------

        print("\n" + "=" * 70)
        print("9. BLADE PLANAR SURFACE INVESTIGATION")
        print("=" * 70)

        for blade_name in ["Blade_1", "Blade_2", "Blade_3"]:

            if blade_name not in groups:
                continue

            print(f"\n{blade_name}")

            for surface_tag in groups[blade_name]:

                surface_type, bbox, centre, area = get_surface_info(
                    surface_tag
                )

                if surface_type.lower() == "plane":

                    print(f"  Planar surface: {surface_tag}")
                    print("    Area:", area)
                    print("    Centre:", centre)
                    print("    Bounding box:", bbox)

                    cap_curves = get_surface_boundary_curves(surface_tag)

                    connected_surfaces = set()

                    for curve_tag in cap_curves:

                        adjacent = get_curve_adjacent_surfaces(curve_tag)

                        connected_surfaces.update(
                            adjacent.intersection(groups[blade_name])
                        )

                    connected_surfaces.discard(surface_tag)

                    print(
                        "    Connected blade surfaces:",
                        sorted(connected_surfaces)
                    )

        # -------------------------------------------------
        # 11. Save geometry
        # -------------------------------------------------

        gmsh.write("turbine_inspection.brep")

        print("\nGeometry saved as turbine_inspection.brep")

        # -------------------------------------------------
        # 12. Final summary
        # -------------------------------------------------

        print("\n" + "=" * 70)
        print("10. FINAL TOPOLOGY SUMMARY")
        print("=" * 70)

        checks = {
            "All expected groups exist": not missing_groups,
            "All groups have valid thickness": thickness_ok,
            "All grouped surfaces exist": not invalid_surfaces,
            "No non-manifold curves": not more_than_two,
            "Tower-Nacelle connection exists": bool(interface_curves),
        }

        for blade_name in ["Blade_1", "Blade_2", "Blade_3"]:

            blade_curves = set()

            if blade_name in groups:

                for surface_tag in groups[blade_name]:
                    blade_curves.update(
                        get_surface_boundary_curves(surface_tag)
                    )

            shared = blade_curves.intersection(hub_curves)

            checks[f"{blade_name}-Hub connection"] = bool(shared)

        for name, passed in checks.items():

            print(f"{'PASS' if passed else 'FAIL'}: {name}")

        if all(checks.values()):

            print("\nALL BASIC GEOMETRY AND TOPOLOGY CHECKS PASSED.")

        else:

            print("\nSOME CHECKS FAILED. REVIEW THE OUTPUT ABOVE.")

        print("\nTopology inspection completed.")

    finally:

        gmsh.finalize()


if __name__ == "__main__":
    main()
