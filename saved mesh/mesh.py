
import numpy as np
import gmsh

from collections import defaultdict
from contracts import Mesh


TRI_FACTOR = 2.31
MAX_ELEMS_WARN = 200_000

GMSH_TYPE_K = {
    2: 3,   # T3
    9: 6    # S6
}

GROUP_SIZES = {
    "Nacelle": 0.6,
    "Hub": 0.4,
    "Blade_1": 0.8,
    "Blade_2": 0.8,
    "Blade_3": 0.8,
}


# =========================================================
# BASIC GEOMETRY FUNCTIONS
# =========================================================

def estimate_elements(area, h):
    return int(TRI_FACTOR * area / h**2)


def make_cylinder(D=2.0, L=20.0):
    """Create a surface-only cylinder for testing."""

    circle = gmsh.model.occ.addCircle(0, 0, 0, D / 2)

    out = gmsh.model.occ.extrude(
        [(1, circle)], 0, 0, L
    )

    gmsh.model.occ.synchronize()

    surfaces = [
        tag for dim, tag in out if dim == 2
    ]

    return {"Tower_1": surfaces}, [circle], np.pi * D * L


def get_tower_groups(groups):
    return {
        name: surfaces
        for name, surfaces in groups.items()
        if name.startswith("Tower_")
    }


def find_base_curves(tower_groups, tol=1e-4):
    """Find bottom boundary curves of tower surfaces."""

    surfaces = [
        (2, tag)
        for tags in tower_groups.values()
        for tag in tags
    ]

    boundary = gmsh.model.getBoundary(
        surfaces,
        combined=True,
        oriented=False,
        recursive=False
    )

    z_min = min(
        gmsh.model.getBoundingBox(2, tag)[2]
        for _, tag in surfaces
    )

    base_curves = []

    for dim, tag in boundary:

        if dim != 1:
            continue

        box = gmsh.model.getBoundingBox(1, tag)

        if (
            abs(box[2] - z_min) < tol
            and abs(box[5] - z_min) < tol
        ):
            base_curves.append(tag)

    if not base_curves:
        raise ValueError("Could not identify tower base curves.")

    return base_curves


def calculate_total_area(groups):
    total = 0.0

    for surfaces in groups.values():
        for tag in surfaces:
            total += gmsh.model.occ.getMass(2, tag)

    return total


# =========================================================
# MESH SIZE CONTROL
# =========================================================

def set_tower_base_refinement(
    base_curves,
    h=1.0,
    h_base=0.5,
    d_refine=6.0
):
    """Refine mesh near the tower foundation."""

    field = gmsh.model.mesh.field

    distance = field.add("Distance")

    field.setNumbers(
        distance, "CurvesList", base_curves
    )

    field.setNumber(
        distance, "Sampling", 200
    )

    threshold = field.add("Threshold")

    field.setNumber(
        threshold, "InField", distance
    )

    field.setNumber(
        threshold, "SizeMin", h_base
    )

    field.setNumber(
        threshold, "SizeMax", h
    )

    field.setNumber(
        threshold, "DistMin", 0.0
    )

    field.setNumber(
        threshold, "DistMax", d_refine
    )

    field.setAsBackgroundMesh(threshold)


def apply_group_sizes(groups):
    """Apply component-specific mesh sizes."""

    for name, surfaces in groups.items():

        if name not in GROUP_SIZES:
            continue

        boundary = gmsh.model.getBoundary(
            [(2, tag) for tag in surfaces],
            combined=False,
            oriented=False,
            recursive=True
        )

        points = [
            (dim, tag)
            for dim, tag in boundary
            if dim == 0
        ]

        if points:
            gmsh.model.mesh.setSize(
                points, GROUP_SIZES[name]
            )


def create_physical_groups(groups):
    """Create physical groups for turbine components."""

    existing = gmsh.model.getPhysicalGroups(2)

    for name, surfaces in groups.items():

        matching = [
            tag
            for dim, tag in existing
            if gmsh.model.getPhysicalName(dim, tag) == name
        ]

        if matching:
            pg = matching[0]
        else:
            pg = gmsh.model.addPhysicalGroup(2, surfaces)

        gmsh.model.setPhysicalName(2, pg, name)


# =========================================================
# MESH EXTRACTION
# =========================================================

def extract_mesh(groups, order=2):
    """Extract nodes and elements, preserving group identity."""

    tags, coords, _ = gmsh.model.mesh.getNodes()

    coords = coords.reshape(-1, 3)

    lookup = {
        int(tag): i for i, tag in enumerate(tags)
    }

    group_names = list(groups.keys())

    elem_list = []
    group_list = []
    element_orders = set()

    for gi, name in enumerate(group_names):

        for surface in groups[name]:

            types, _, element_tags = (
                gmsh.model.mesh.getElements(2, surface)
            )

            for element_type, connectivity in zip(
                types, element_tags
            ):

                if element_type not in GMSH_TYPE_K:
                    raise ValueError(
                        f"Unsupported element type {element_type} "
                        f"in group {name}"
                    )

                k = GMSH_TYPE_K[element_type]
                element_orders.add(k)

                raw = connectivity.reshape(-1, k)

                conn = np.array([
                    [lookup[int(tag)] for tag in row]
                    for row in raw
                ], dtype=int)

                elem_list.append(conn)

                group_list.append(
                    np.full(len(conn), gi, dtype=int)
                )

    if element_orders != {6}:
        raise ValueError(
            f"Expected only S6 elements. Found: {element_orders}"
        )

    elems = np.vstack(elem_list)
    elem_group = np.concatenate(group_list)

    used = np.unique(elems)

    remap = np.full(len(coords), -1, dtype=int)
    remap[used] = np.arange(len(used))

    nodes = coords[used]
    elems = remap[elems]

    return nodes, elems, elem_group, group_names


# =========================================================
# ELEMENT QUALITY
# =========================================================

def diagnose_element_quality(groups, stage, expected_type):

    print(f"\n{'=' * 55}")
    print(f"ELEMENT QUALITY: {stage}")
    print(f"{'=' * 55}")

    totals = {
        "total_elements": 0,
        "low_quality": 0,
        "negative_sicn": 0,
        "negative_detjac": 0
    }

    for name, surfaces in groups.items():

        print(f"\n{name}:")

        for surface in surfaces:

            types, element_tags, _ = (
                gmsh.model.mesh.getElements(2, surface)
            )

            for element_type, tags in zip(types, element_tags):

                if element_type != expected_type:
                    continue

                tags = np.asarray(tags, dtype=np.int64)

                if len(tags) == 0:
                    continue

                sicn = np.asarray(
                    gmsh.model.mesh.getElementQualities(
                        tags.tolist(), "minSICN"
                    )
                )

                detjac = np.asarray(
                    gmsh.model.mesh.getElementQualities(
                        tags.tolist(), "minDetJac"
                    )
                )

                if len(sicn) != len(tags) or len(detjac) != len(tags):
                    raise RuntimeError("Quality result count mismatch.")

                low = int(np.sum(sicn < 0.1))
                neg_sicn = int(np.sum(sicn < 0))
                neg_det = int(np.sum(detjac < 0))

                totals["total_elements"] += len(tags)
                totals["low_quality"] += low
                totals["negative_sicn"] += neg_sicn
                totals["negative_detjac"] += neg_det

                print(
                    f"  Surface {surface}: {len(tags)} elements | "
                    f"SICN < 0.1: {low} | "
                    f"negative SICN: {neg_sicn} | "
                    f"negative detJac: {neg_det}"
                )

                worst = np.argsort(sicn)[:3]

                for idx in worst:
                    print(
                        f"    Element {int(tags[idx])}: "
                        f"SICN={sicn[idx]:.5f}, "
                        f"detJac={detjac[idx]:.6g}"
                    )

    print("\nStage summary:", totals)

    return totals


# =========================================================
# S6 GEOMETRY AND AREA
# =========================================================

# Seven-point triangular quadrature.
# Weights sum to 0.5, the reference triangle area.

QUAD_POINTS = [
    (1/3, 1/3, 0.1125),
    (0.0597158717, 0.4701420641, 0.0661970764),
    (0.4701420641, 0.0597158717, 0.0661970764),
    (0.4701420641, 0.4701420641, 0.0661970764),
    (0.7974269853, 0.1012865073, 0.0629695903),
    (0.1012865073, 0.7974269853, 0.0629695903),
    (0.1012865073, 0.1012865073, 0.0629695903),
]


def s6_shape_derivatives(r, s):
    """Derivatives of six-node triangular shape functions."""

    L1 = 1.0 - r - s
    L2 = r
    L3 = s

    dNdr = np.array([
        -(4 * L1 - 1),
        4 * L2 - 1,
        0.0,
        4 * (L1 - L2),
        4 * L3,
        -4 * L3
    ])

    dNds = np.array([
        -(4 * L1 - 1),
        0.0,
        4 * L3 - 1,
        -4 * L2,
        4 * L2,
        4 * (L1 - L3)
    ])

    return dNdr, dNds


def s6_element_area(points):
    """Integrate the curved S6 element surface area."""

    area = 0.0

    for r, s, weight in QUAD_POINTS:

        dNdr, dNds = s6_shape_derivatives(r, s)

        tangent_r = dNdr @ points
        tangent_s = dNds @ points

        jacobian = np.linalg.norm(
            np.cross(tangent_r, tangent_s)
        )

        area += weight * jacobian

    return area


def calculate_s6_areas(nodes, elems):

    areas = np.array([
        s6_element_area(nodes[element])
        for element in elems
    ])

    return areas


def check_surface_area(nodes, elems, cad_area):

    areas = calculate_s6_areas(nodes, elems)

    mesh_area = areas.sum()

    error = (
        abs(mesh_area - cad_area)
        / cad_area * 100
    )

    print("\n--- S6 Surface Area Check ---")
    print(f"CAD area:  {cad_area:.4f} m2")
    print(f"Mesh area: {mesh_area:.4f} m2")
    print(f"Area error: {error:.4f}%")

    return mesh_area, error


# =========================================================
# SURFACE NORMAL CHECK
# =========================================================


def check_surface_normals(nodes, elems, groups, group_names):
    """
    Diagnose S6 shell element orientation.

    Checks:
    1. Element normal against raw CAD normal.
    2. Whether raw CAD normals have a consistent sign on each surface.
    3. Whether neighbouring elements have consistent normal directions.

    This function only diagnoses. It does NOT change element connectivity.
    """

    print("\n" + "=" * 65)
    print("DETAILED SHELL NORMAL DIAGNOSTIC")
    print("=" * 65)

    # Get Gmsh node tags and coordinates.
    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    node_coords = node_coords.reshape(-1, 3)

    coord_lookup = {
        int(tag): node_coords[i]
        for i, tag in enumerate(node_tags)
    }

    total_elements = 0
    total_cad_opposite = 0
    total_neighbour_conflicts = 0
    total_unverified = 0

    for group_name, surfaces in groups.items():

        print(f"\n{'-' * 65}")
        print(f"GROUP: {group_name}")
        print(f"{'-' * 65}")

        group_elements = []

        # -------------------------------------------------
        # Collect elements and calculate their normals.
        # -------------------------------------------------

        for surface in surfaces:

            types, element_tags, connectivity = (
                gmsh.model.mesh.getElements(2, surface)
            )

            for element_type, tags, conn in zip(
                types, element_tags, connectivity
            ):

                if element_type != 9:
                    continue

                conn = np.asarray(
                    conn, dtype=int
                ).reshape(-1, 6)

                tags = np.asarray(tags, dtype=int)

                for element_tag, row in zip(tags, conn):

                    corner_tags = row[:3]

                    p = np.array([
                        coord_lookup[int(tag)]
                        for tag in corner_tags
                    ])

                    v1 = p[1] - p[0]
                    v2 = p[2] - p[0]

                    normal = np.cross(v1, v2)
                    norm = np.linalg.norm(normal)

                    if norm < 1e-14:
                        continue

                    normal /= norm

                    centroid = p.mean(axis=0)

                    # -------------------------------------
                    # Compare with CAD normal.
                    # -------------------------------------

                    cad_dot = None

                    try:
                        uv = gmsh.model.getParametrization(
                            2,
                            surface,
                            centroid.tolist()
                        )

                        cad_normal = np.asarray(
                            gmsh.model.getNormal(
                                surface,
                                uv
                            ),
                            dtype=float
                        ).reshape(3, -1)[:, 0]

                        cad_norm = np.linalg.norm(cad_normal)

                        if cad_norm > 1e-14:
                            cad_normal /= cad_norm

                            cad_dot = float(
                                np.dot(normal, cad_normal)
                            )

                    except Exception:
                        cad_dot = None

                    group_elements.append({
                        "tag": int(element_tag),
                        "surface": int(surface),
                        "nodes": corner_tags.copy(),
                        "normal": normal,
                        "cad_dot": cad_dot
                    })

        # -------------------------------------------------
        # Analyse each CAD surface independently.
        # -------------------------------------------------

        surface_signs = {}

        for surface in surfaces:

            records = [
                item for item in group_elements
                if item["surface"] == surface
                and item["cad_dot"] is not None
            ]

            signs = [
                1 if item["cad_dot"] >= 0 else -1
                for item in records
            ]

            if not signs:
                surface_signs[surface] = None
                continue

            positive = signs.count(1)
            negative = signs.count(-1)

            # Majority sign indicates the dominant relationship
            # between mesh normals and raw CAD normals.
            dominant_sign = (
                1 if positive >= negative else -1
            )

            surface_signs[surface] = dominant_sign

            print(
                f"\nSurface {surface}: "
                f"elements={len(records)}, "
                f"raw CAD-aligned={positive}, "
                f"raw CAD-opposite={negative}"
            )

            if dominant_sign == -1:
                print(
                    "  NOTE: Majority of mesh elements oppose "
                    "the raw CAD normal on this surface."
                )
                print(
                    "  This may indicate reversed CAD "
                    "parameterisation, not reversed elements."
                )

        # -------------------------------------------------
        # Find elements that disagree with the dominant
        # CAD relationship on their own surface.
        # -------------------------------------------------

        cad_anomalies = []

        for item in group_elements:

            dot = item["cad_dot"]

            if dot is None:
                continue

            dominant_sign = surface_signs.get(
                item["surface"]
            )

            if dominant_sign is None:
                continue

            actual_sign = 1 if dot >= 0 else -1

            if actual_sign != dominant_sign:
                cad_anomalies.append(item)

        # -------------------------------------------------
        # Check neighbouring elements.
        # Two elements sharing an edge should normally have
        # normals pointing in broadly the same direction.
        # -------------------------------------------------

        edge_map = defaultdict(list)

        for index, item in enumerate(group_elements):

            corner_nodes = item["nodes"]

            edges = [
                (corner_nodes[0], corner_nodes[1]),
                (corner_nodes[1], corner_nodes[2]),
                (corner_nodes[2], corner_nodes[0])
            ]

            for a, b in edges:

                key = tuple(sorted((int(a), int(b))))

                edge_map[key].append(index)

        neighbour_conflicts = set()
        checked_pairs = set()

        for edge, occurrences in edge_map.items():

            if len(occurrences) != 2:
                continue

            i, j = occurrences

            pair = tuple(sorted((i, j)))

            if pair in checked_pairs:
                continue

            checked_pairs.add(pair)

            ni = group_elements[i]["normal"]
            nj = group_elements[j]["normal"]

            dot = float(np.dot(ni, nj))

            # Negative dot means the normals point more than
            # 90 degrees apart.
            if dot < 0:
                neighbour_conflicts.add(i)
                neighbour_conflicts.add(j)

        neighbour_conflict_records = [
            group_elements[i]
            for i in sorted(neighbour_conflicts)
        ]

        # -------------------------------------------------
        # Report group results.
        # -------------------------------------------------

        verified = sum(
            item["cad_dot"] is not None
            for item in group_elements
        )

        raw_opposite = sum(
            item["cad_dot"] is not None
            and item["cad_dot"] < 0
            for item in group_elements
        )

        print("\nGroup summary:")
        print("  Total elements:", len(group_elements))
        print("  CAD comparisons successful:", verified)
        print("  Opposite to raw CAD normal:", raw_opposite)
        print(
            "  CAD-sign anomalies within their surface:",
            len(cad_anomalies)
        )
        print(
            "  Elements involved in neighbour conflicts:",
            len(neighbour_conflict_records)
        )

        if cad_anomalies:
            print("\n  CAD-sign anomaly element IDs:")
            print(
                " ",
                [item["tag"] for item in cad_anomalies[:50]]
            )

        if neighbour_conflict_records:
            print("\n  Neighbour-conflict element IDs:")
            print(
                "  ",
                [
                    item["tag"]
                    for item in neighbour_conflict_records[:50]
                ]
            )

        total_elements += len(group_elements)
        total_cad_opposite += raw_opposite
        total_neighbour_conflicts += len(
            neighbour_conflict_records
        )
        total_unverified += len(group_elements) - verified

    # -----------------------------------------------------
    # Final summary.
    # -----------------------------------------------------

    print("\n" + "=" * 65)
    print("OVERALL NORMAL DIAGNOSTIC SUMMARY")
    print("=" * 65)

    print("Total elements:", total_elements)
    print("Opposite to raw CAD normals:", total_cad_opposite)
    print(
        "Elements involved in neighbour conflicts:",
        total_neighbour_conflicts
    )
    print("Unverified CAD comparisons:", total_unverified)

    print("\nNo element connectivity was modified.")



# =========================================================
# S6 EDGE CONSISTENCY
# =========================================================

def check_s6_edges(elems):

    print("\n--- S6 Shared-Edge Consistency ---")

    # Each S6 edge has two corner nodes and one midside node.
    edge_definitions = [
        (0, 1, 3),
        (1, 2, 4),
        (2, 0, 5)
    ]

    edge_occurrences = defaultdict(list)

    for element_index, element in enumerate(elems):

        for a, b, mid in edge_definitions:

            na = int(element[a])
            nb = int(element[b])
            nm = int(element[mid])

            key = tuple(sorted((na, nb)))

            direction = (na, nb)

            edge_occurrences[key].append(
                (nm, direction, element_index)
            )

    boundary = 0
    internal = 0
    non_manifold = 0
    mismatch = 0
    same_direction = 0

    for key, occurrences in edge_occurrences.items():

        if len(occurrences) == 1:
            boundary += 1

        elif len(occurrences) == 2:
            internal += 1

            mid_nodes = {
                item[0] for item in occurrences
            }

            if len(mid_nodes) != 1:
                mismatch += 1

            d1 = occurrences[0][1]
            d2 = occurrences[1][1]

            if d1 == d2:
                same_direction += 1

        else:
            non_manifold += 1

    print("Boundary S6 edges:", boundary)
    print("Shared S6 edges:", internal)
    print("Non-manifold edges:", non_manifold)
    print("Midside-node mismatches:", mismatch)
    print("Same-direction shared edges:", same_direction)

    return {
        "boundary": boundary,
        "internal": internal,
        "non_manifold": non_manifold,
        "mismatch": mismatch,
        "same_direction": same_direction
    }


# =========================================================
# CONNECTIVITY AND DUPLICATES
# =========================================================

def check_connectivity(elems, n_nodes):

    invalid = np.sum(
        (elems < 0) | (elems >= n_nodes)
    )

    print("Invalid node references:", invalid)

    if invalid:
        raise ValueError("Invalid node references detected.")


def check_duplicates(elems):

    unique = np.unique(
        np.sort(elems, axis=1),
        axis=0
    )

    duplicates = len(elems) - len(unique)

    print("Duplicate elements:", duplicates)

    if duplicates:
        raise ValueError("Duplicate elements detected.")


def count_components(elems, n_nodes):
    """Count connected components using corner nodes."""

    parent = np.arange(n_nodes)

    def find(x):

        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]

        return x

    def union(a, b):

        ra = find(a)
        rb = find(b)

        if ra != rb:
            parent[rb] = ra

    for e in elems:

        for node in e[1:3]:
            union(int(e[0]), int(node))

    roots = {
        find(int(node))
        for node in np.unique(elems[:, :3])
    }

    return len(roots)


# =========================================================
# ASPECT RATIO
# =========================================================

def check_quality(nodes, elems):

    p = nodes[elems[:, :3]]

    e1 = np.linalg.norm(
        p[:, 1] - p[:, 0], axis=1
    )

    e2 = np.linalg.norm(
        p[:, 2] - p[:, 1], axis=1
    )

    e3 = np.linalg.norm(
        p[:, 0] - p[:, 2], axis=1
    )

    longest = np.maximum.reduce([e1, e2, e3])

    area = 0.5 * np.linalg.norm(
        np.cross(
            p[:, 1] - p[:, 0],
            p[:, 2] - p[:, 0]
        ),
        axis=1
    )

    altitude = (
        2.0 * area /
        np.maximum(longest, 1e-15)
    )

    aspect = (
        longest /
        np.maximum(altitude, 1e-15)
    )

    print("\n--- Corner-node Aspect Ratio ---")
    print("Minimum:", aspect.min())
    print("Maximum:", aspect.max())
    print("Average:", aspect.mean())
    print("> 5:", np.sum(aspect > 5))

    return aspect


# =========================================================
# FREE EDGE CHECK
# =========================================================

def free_edges(elems):

    edges = np.vstack([
        elems[:, [0, 1]],
        elems[:, [1, 2]],
        elems[:, [2, 0]]
    ])

    edges = np.sort(edges, axis=1)

    unique, counts = np.unique(
        edges,
        axis=0,
        return_counts=True
    )

    return (
        unique[counts == 1],
        unique[counts == 2],
        unique[counts > 2]
    )


# =========================================================
# THICKNESS CHECK
# =========================================================

def check_thickness(groups, thickness):

    print("\n--- Shell Thickness Check ---")

    if thickness is None:
        print(
            "Thickness data not supplied to build_mesh()."
        )
        return

    missing = []

    for name in groups:

        if name not in thickness:
            missing.append(name)
            print(f"{name}: MISSING")
        else:
            value = thickness[name]

            print(f"{name}: {value} m")

            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"Invalid thickness for {name}: {value}"
                )

            if value <= 0:
                raise ValueError(
                    f"Non-positive thickness for {name}"
                )

    if missing:
        print("Groups missing thickness:", missing)
    else:
        print("All groups have thickness values.")

    print(
        "Note: This verifies supplied thickness data. "
        "It does not verify CalculiX section assignment."
    )


# =========================================================
# GEOMETRY DIAGNOSTICS
# =========================================================

def diagnose_surfaces(groups):

    print("\n--- Surface Diagnostics ---")

    for name, surfaces in groups.items():

        print(f"\n{name}:")

        for surface in surfaces:

            surface_type = gmsh.model.getType(2, surface)

            area = gmsh.model.occ.getMass(2, surface)

            bbox = gmsh.model.getBoundingBox(2, surface)

            print(
                f"  Surface {surface}: "
                f"type={surface_type}, "
                f"area={area:.4f} m2, "
                f"bbox={bbox}"
            )


# =========================================================
# COMPLETE MESH GENERATION
# =========================================================

def build_mesh(
    groups,
    base_curves=None,
    total_area=None,
    h=1.0,
    h_base=0.5,
    d_refine=6.0,
    order=2,
    tol=0.01,
    orientation=None,
    create_groups=True,
    thickness=None
):
    """Generate and validate the complete turbine S6 mesh."""

    if order != 2:
        raise ValueError("This project uses S6 elements.")

    tower_groups = get_tower_groups(groups)

    if not tower_groups:
        raise ValueError("No tower groups found.")

    base_curves = find_base_curves(tower_groups)

    total_area = calculate_total_area(groups)

    print("\n--- Geometry Summary ---")

    for name, surfaces in groups.items():

        area = sum(
            gmsh.model.occ.getMass(2, s)
            for s in surfaces
        )

        print(
            f"{name}: {len(surfaces)} surfaces, "
            f"area={area:.3f} m2"
        )

    print("\nTotal CAD area:", total_area, "m2")

    estimated = estimate_elements(total_area, h)

    print("Estimated elements:", estimated)

    if estimated > MAX_ELEMS_WARN:
        print("WARNING: Large mesh expected.")

    diagnose_surfaces(groups)

    if create_groups:
        create_physical_groups(groups)

    # Mesh settings.
    gmsh.option.setNumber(
        "Mesh.MeshSizeExtendFromBoundary", 1
    )

    gmsh.option.setNumber(
        "Mesh.MeshSizeFromPoints", 1
    )

    gmsh.option.setNumber(
        "Mesh.MeshSizeFromCurvature", 0
    )

    gmsh.option.setNumber(
        "Mesh.MeshSizeMin", 0.05
    )

    gmsh.option.setNumber(
        "Mesh.MeshSizeMax", h
    )

    gmsh.option.setNumber(
        "Mesh.Algorithm", 6
    )

    gmsh.option.setNumber(
        "Mesh.RandomFactor", 1e-9
    )

    gmsh.option.setNumber(
        "Mesh.ElementOrder", 1
    )

    gmsh.option.setNumber(
        "Mesh.SecondOrderLinear", 1
    )

    set_tower_base_refinement(
        base_curves,
        h=h,
        h_base=h_base,
        d_refine=d_refine
    )

    apply_group_sizes(groups)

    print("\nGenerating complete turbine mesh...")

    gmsh.model.mesh.generate(2)

    # T3 quality before conversion.
    t3_results = diagnose_element_quality(
        groups,
        "Original T3 mesh",
        expected_type=2
    )

    # Convert to S6.
    print("\nConverting T3 to S6...")

    gmsh.model.mesh.setOrder(2)

    s6_results = diagnose_element_quality(
        groups,
        "Final S6 mesh",
        expected_type=9
    )

    print("\n--- T3 vs S6 Comparison ---")

    for key in (
        "total_elements",
        "low_quality",
        "negative_sicn",
        "negative_detjac"
    ):
        print(
            f"{key}: T3={t3_results[key]}, "
            f"S6={s6_results[key]}"
        )

    # Extract mesh.
    nodes, elems, elem_group, group_names = extract_mesh(
        groups, order=order
    )

    # 1. Surface normal direction.
    check_surface_normals(
        nodes, elems, groups, group_names
    )

    # 2. S6 shared-edge consistency.
    edge_results = check_s6_edges(elems)

    # Connectivity.
    print("\n--- Node Reference Check ---")

    check_connectivity(elems, len(nodes))

    # Duplicate elements.
    print("\n--- Duplicate Element Check ---")

    check_duplicates(elems)

    # 3. Accurate S6 surface area.
    check_surface_area(
        nodes, elems, total_area
    )

    # 4. Element quality and aspect ratio.
    check_quality(nodes, elems)

    # 5. Free-edge and component checks.
    print("\n--- Free Edge Check ---")

    free, internal, unexpected = free_edges(elems)

    print("Free edges:", len(free))
    print("Internal edges:", len(internal))
    print("Unexpected edges:", len(unexpected))

    components = count_components(
        elems, len(nodes)
    )

    print("Connected components:", components)

    # 6. Thickness check.
    check_thickness(groups, thickness)

    # Base node set.
    z_min = nodes[:, 2].min()

    base_nodes = np.where(
        np.abs(nodes[:, 2] - z_min) < tol
    )[0]

    if len(base_nodes) == 0:
        raise ValueError("Tower base nodes not found.")

    mesh = Mesh(
        nodes=nodes,
        elems=elems,
        elem_group=elem_group,
        group_names=group_names
    )

    mesh.node_sets["base"] = base_nodes

    print("\n" + "=" * 55)
    print("FINAL MESH SUMMARY")
    print("=" * 55)

    print("Groups:", group_names)
    print("Nodes:", mesh.n_nodes)
    print("Elements:", mesh.n_elems)
    print("Z range:", nodes[:, 2].min(), "to", nodes[:, 2].max())
    print("Base nodes:", len(base_nodes))

    print("\nValidation report completed.")

    return mesh


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    from geometry.default_generator import (
        load_params,
        build_default
    )

    gmsh.initialize()

    try:

        gmsh.model.add("wind_turbine")

        params = load_params(
            "data/default_turbine.json"
        )

        groups, thickness = build_default(params)

        mesh = build_mesh(
            groups,
            h=1.0,
            h_base=0.5,
            d_refine=6.0,
            order=2,
            thickness=thickness
        )

        gmsh.write("turbine_mesh.msh")

        print("\nSaved turbine_mesh.msh")

        gmsh.fltk.run()

    finally:
        gmsh.finalize()
