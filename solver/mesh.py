import numpy as np
import gmsh
from contracts import Mesh

TRI_FACTOR = 2.31          # elements ~ 2.31 * area / h^2 for triangles
MAX_ELEMS_WARN = 200_000
GMSH_TYPE_K = {2: 3, 9: 6}  # gmsh 3-node tri, 6-node tri -> nodes per element


def estimate_elements(total_area_m2, h):
    """Estimated triangle count. total_area in m^2, h in m."""
    return int(TRI_FACTOR * total_area_m2 / h**2)


def make_cylinder(D=2.0, L=20.0):
    """Surface-only cylinder. Returns ({group: [surface tags]}, base_curve_tags, area)."""
    c = gmsh.model.occ.addCircle(0, 0, 0, D / 2)
    out = gmsh.model.occ.extrude([(1, c)], 0, 0, L)
    gmsh.model.occ.synchronize()
    surfs = [t for d, t in out if d == 2]
    area = np.pi * D * L
    return {"Tower_1": surfs}, [c], area


def set_size_fields(base_curves, h, h_base, d_refine):
    """Element size h_base at the base curves, growing to h at d_refine metres away."""
    F = gmsh.model.mesh.field
    f1 = F.add("Distance")
    F.setNumbers(f1, "CurvesList", base_curves)
    F.setNumber(f1, "Sampling", 200)
    f2 = F.add("Threshold")
    F.setNumber(f2, "InField", f1)
    F.setNumber(f2, "SizeMin", h_base)
    F.setNumber(f2, "SizeMax", h)
    F.setNumber(f2, "DistMin", 0.0)
    F.setNumber(f2, "DistMax", d_refine)
    F.setAsBackgroundMesh(f2)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)

def normal_check(nodes, elems):
    """Check whether cylindrical shell elements face outward."""

    # Get the three corner nodes of every S6 element
    p1 = nodes[elems[:, 0]]
    p2 = nodes[elems[:, 1]]
    p3 = nodes[elems[:, 2]]

    # Calculate element normal using cross product
    a = p2 - p1
    b = p3 - p1
    normals = np.cross(a, b)

    # Calculate element centres
    centres = (p1 + p2 + p3) / 3.0

    # Radial direction from cylinder axis
    radial = np.column_stack((
        centres[:, 0],
        centres[:, 1],
        np.zeros(len(centres))
    ))

    # Positive dot product means outward
    dot_products = np.sum(normals * radial, axis=1)

    outward = dot_products > 1e-12
    inward = dot_products < -1e-12
    uncertain = ~(outward | inward)

    print("\n--- Shell Normal Check ---")
    print("Outward elements:", np.sum(outward))
    print("Inward elements:", np.sum(inward))
    print("Uncertain elements:", np.sum(uncertain))

    return inward

def fix_inward_elements(nodes, elems):
    """Reverse the node ordering of inward-facing S3/S6 elements."""

    inward = normal_check(nodes, elems)

    elems = elems.copy()

    # Reverse corner-node ordering
    elems[inward, 1], elems[inward, 2] = (
        elems[inward, 2].copy(),
        elems[inward, 1].copy()
    )

    # Also reverse corresponding midside nodes for S6
    if elems.shape[1] == 6:
        elems[inward, 3], elems[inward, 5] = (
            elems[inward, 5].copy(),
            elems[inward, 3].copy()
        )

    print("\nCorrected inward-facing elements:", np.sum(inward))

    return elems

def build_mesh(groups, base_curves, total_area, h=0.25, h_base=None,
               d_refine=3.0, order=2, tol=0.01,
               orientation=None):
    """Mesh the current gmsh model and return a contracts.Mesh."""
    h_base = h_base or h / 2
    n_est = estimate_elements(total_area, h)
    print(f"Estimated elements: ~{n_est}")
    if n_est > MAX_ELEMS_WARN:
        print("WARNING: mesh may be very large and slow. Increase element size.")

    for name, surfs in groups.items():
        pg = gmsh.model.addPhysicalGroup(2, surfs)
        gmsh.model.setPhysicalName(2, pg, name)

    set_size_fields(base_curves, h, h_base, d_refine)
    gmsh.model.mesh.generate(2)
    if order == 2:
        gmsh.model.mesh.setOrder(2)

    # nodes
    tags, coords, _ = gmsh.model.mesh.getNodes()
    coords = coords.reshape(-1, 3)
    lookup = np.full(int(tags.max()) + 1, -1, dtype=int)
    lookup[tags.astype(int)] = np.arange(len(tags))

    # elements, one group at a time
    group_names = list(groups.keys())
    elem_list, grp_list, k_seen = [], [], set()
    for gi, name in enumerate(group_names):
        for s in groups[name]:
            types, _, ntags = gmsh.model.mesh.getElements(2, s)
            for t, nt in zip(types, ntags):
                if t not in GMSH_TYPE_K:
                    raise ValueError(f"Unsupported gmsh element type {t} in {name}")
                k = GMSH_TYPE_K[t]
                k_seen.add(k)
                conn = lookup[nt.astype(int).reshape(-1, k)]
                elem_list.append(conn)
                grp_list.append(np.full(len(conn), gi))
    if len(k_seen) != 1:
        raise ValueError(f"Mixed element types in mesh (nodes per element: {k_seen})")
    elems = np.vstack(elem_list)
    elem_group = np.concatenate(grp_list)

    # drop nodes not used by any element, renumber
    used = np.unique(elems)
    remap = np.full(len(coords), -1, dtype=int)
    remap[used] = np.arange(len(used))

    nodes = coords[used]
    elems = remap[elems]

    # Correct orientation for the Z-axis test cylinder
    if orientation == "cylinder_z":
        elems = fix_inward_elements(nodes, elems)
        print("\n--- Verification After Correction ---")
        normal_check(nodes, elems)

    # Check 4: Surface area verification
    p1 = nodes[elems[:, 0]]
    p2 = nodes[elems[:, 1]]
    p3 = nodes[elems[:, 2]]

    a = p2 - p1
    b = p3 - p1

    cross = np.cross(a, b)

    triangle_areas = 0.5 * np.linalg.norm(cross, axis=1)

    mesh_area = np.sum(triangle_areas)

    theoretical_area = total_area

    error_percent = abs(mesh_area - theoretical_area) / theoretical_area * 100

    print(f"Theoretical surface area: {theoretical_area:.4f} m^2")
    print(f"Mesh surface area: {mesh_area:.4f} m^2")
    print(f"Area error: {error_percent:.4f}%")

    mesh = Mesh(nodes=nodes, elems=elems, elem_group=elem_group,
                group_names=group_names)

    # Check 6: Free-edge verification

    edge_list = np.vstack([
        elems[:, [0, 1]],
        elems[:, [1, 2]],
        elems[:, [2, 0]]
    ])

    # Sort each edge so (10, 20) and (20, 10) are identical
    edge_list = np.sort(edge_list, axis=1)

    # Count how many elements share each unique edge
    unique_edges, edge_counts = np.unique(
        edge_list, axis=0, return_counts=True
    )

    # Edges belonging to only one element are free edges
    free_edges = unique_edges[edge_counts == 1]

    print("Total unique edges:", len(unique_edges))
    print("Free edges:", len(free_edges))
    print("Internal edges:", np.sum(edge_counts == 2))
    print("Unexpected edges:", np.sum(edge_counts > 2))
        # Check location of free edges

    free_edge_nodes = nodes[free_edges]

    edge_z_min = free_edge_nodes[:, :, 2].min(axis=1)
    edge_z_max = free_edge_nodes[:, :, 2].max(axis=1)

    bottom_edges = np.all(free_edge_nodes[:, :, 2] < tol, axis=1)

    top_edges = np.all(
        free_edge_nodes[:, :, 2] > nodes[:, 2].max() - tol, axis=1
    )

    middle_edges = ~(bottom_edges | top_edges)

    print("Bottom free edges:", np.sum(bottom_edges))
    print("Top free edges:", np.sum(top_edges))
    print("Middle free edges:", np.sum(middle_edges))

    mesh.node_sets["base"] = np.where(nodes[:, 2] < nodes[:, 2].min() + tol)[0]
    print(f"Nodes: {mesh.n_nodes}, elements: {mesh.n_elems}, "
          f"base nodes: {len(mesh.node_sets['base'])}")
    
    # Check 3: Base ring completeness
    base_nodes = nodes[mesh.node_sets["base"]]

    angles = np.arctan2(base_nodes[:, 1], base_nodes[:, 0])
    angles = np.sort(angles)

    gaps = np.diff(np.append(angles, angles[0] + 2*np.pi))

    print("Largest angular gap (degrees):", np.degrees(gaps.max()))
    return mesh


if __name__ == "__main__":
    gmsh.initialize()
    gmsh.model.add("cyl")
    groups, base_curves, area = make_cylinder(2.0, 20.0)
    m = build_mesh(groups, base_curves, area, h=0.25, order=2,orientation="cylinder_z")


    # inward = normal_check(m.nodes, m.elems)

        # Verify Gmsh S6 reference-node ordering
        # Verify Gmsh S6 reference-node ordering
    properties = gmsh.model.mesh.getElementProperties(9)

    name, dim, order, num_nodes, local_coords, num_primary = properties

    print("\nElement name:", name)
    print("Dimension:", dim)
    print("Polynomial order:", order)
    print("Number of nodes:", num_nodes)
    print("Primary nodes:", num_primary)
    print("Length of local coordinates:", len(local_coords))

    local_coords = np.array(local_coords).reshape(-1, 2)

    print("\nReference node coordinates:")

    for i, coord in enumerate(local_coords):
        print(f"Node {i + 1}: {coord}")

    print("Element nodes per element:", m.elems.shape[1])
    print("First S6 element node indices:", m.elems[0])
    gmsh.fltk.run()
    gmsh.finalize()