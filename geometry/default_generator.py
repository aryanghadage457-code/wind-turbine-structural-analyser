
"""Default turbine generator.

Units: metres.
Z up, rotor axis +Y.
Outer surfaces only (shell model).
Wall thickness is assigned per surface group.
"""

import json
import math
import gmsh

from geometry.blade import build_blades

occ = gmsh.model.occ


def load_params(path="data/default_turbine.json"):
    with open(path) as f:
        return json.load(f)


def _tower_surfaces(sections):
    """Create tower lateral surfaces; remove solids and end disks."""
    for s in sections:
        h = s["z1"] - s["z0"]

        if abs(s["d0"] - s["d1"]) < 1e-9:
            occ.addCylinder(
                0, 0, s["z0"],
                0, 0, h,
                s["d0"] / 2
            )
        else:
            occ.addCone(
                0, 0, s["z0"],
                0, 0, h,
                s["d0"] / 2,
                s["d1"] / 2
            )

    occ.synchronize()

    vols = gmsh.model.getEntities(3)
    keep = set()
    disks = []

    for _, v in vols:
        boundary = gmsh.model.getBoundary(
            [(3, v)], oriented=False
        )

        for _, s in boundary:
            if gmsh.model.getType(2, s) in ("Cone", "Cylinder"):
                keep.add(s)
            else:
                disks.append((2, s))

    occ.remove(vols)
    if disks:
        occ.remove(disks, recursive=True)

    occ.synchronize()
    return sorted(keep)


def _nacelle_surfaces(nac, z_top):
    """Create the nacelle box surfaces."""
    w = nac["width"]
    h = nac["height"]
    y0 = nac["y_rear"]
    y1 = nac["y_front"]

    occ.addBox(
        -w / 2, y0, z_top,
        w, y1 - y0, h
    )
    occ.synchronize()

    vols = gmsh.model.getEntities(3)
    faces = []

    for _, v in vols:
        faces.extend(
            s for _, s in gmsh.model.getBoundary(
                [(3, v)], oriented=False
            )
        )

    occ.remove(vols)
    occ.synchronize()

    return faces


def _hub_surface(hub, nac, z_top):
    """Create the spherical hub surface."""
    zc = z_top + nac["height"] / 2

    tag = occ.addSphere(
        0,
        hub["overhang"],
        zc,
        hub["diameter"] / 2
    )

    occ.synchronize()

    face = [
        s for _, s in gmsh.model.getBoundary(
            [(3, tag)], oriented=False
        )
    ]

    occ.remove([(3, tag)])
    occ.synchronize()

    return face


def _tower_top_ring(sections, nac, z_top):
    """
    Create an annular shell surface at the tower top.

    The inner radius matches the tower-top radius.
    The outer radius is configurable in the JSON file.
    """
    r_inner = sections[-1]["d1"] / 2
    r_outer = nac.get("tower_ring_outer_radius", 2.4)

    if r_outer <= r_inner:
        raise ValueError(
            "tower_ring_outer_radius must be greater "
            "than the tower-top radius."
        )

    if r_outer > min(nac["width"] / 2, nac["y_front"]):
        raise ValueError(
            "Tower ring outer radius must fit inside "
            "the nacelle floor footprint."
        )

    outer = occ.addDisk(
        0, 0, z_top,
        r_outer, r_outer
    )

    inner = occ.addDisk(
        0, 0, z_top,
        r_inner, r_inner
    )

    ring, _ = occ.cut(
        [(2, outer)],
        [(2, inner)],
        removeObject=True,
        removeTool=True
    )

    occ.synchronize()

    ring_faces = [
        tag for dim, tag in ring if dim == 2
    ]

    if not ring_faces:
        raise RuntimeError("Could not create tower-top ring.")

    return ring_faces


def build_default(params):
    gmsh.model.add("turbine")

    sections = params["tower"]["sections"]
    z_top = sections[-1]["z1"]

    has_head = (
        "nacelle" in params
        and "hub" in params
    )

    has_blade = has_head and "blade" in params

    tower = _tower_surfaces(sections)

    blades = []
    ring_faces = []

    if has_head:
        nac = params["nacelle"]
        hub = params["hub"]

        hub_c = (
            0.0,
            hub["overhang"],
            z_top + nac["height"] / 2
        )

        nac_faces = _nacelle_surfaces(nac, z_top)
        hub_face = _hub_surface(hub, nac, z_top)

        ring_faces = _tower_top_ring(
            sections, nac, z_top
        )

        if has_blade:
            blades = build_blades(
                params["blade"], hub_c
            )

        flat_blades = [
            tag for blade in blades for tag in blade
        ]

        # Keep the input order: ring faces are last.
        objects = (
            [(2, s) for s in tower]
            + [(2, s) for s in nac_faces]
            + [(2, s) for s in hub_face]
            + [(2, s) for s in flat_blades]
            + [(2, s) for s in ring_faces]
        )

        _, maps = occ.fragment(objects, [])

        # The final input objects are the ring faces.
        ring_input_start = len(objects) - len(ring_faces)

        ring_tags = set()

        for mapping in maps[ring_input_start:]:
            for dim, tag in mapping:
                if dim == 2:
                    ring_tags.add(tag)

    else:
        ring_tags = set()
        occ.removeAllDuplicates()

    occ.synchronize()

    groups = {}
    thickness = {}
    discard = []

    n_bl = (
        int(params["blade"].get("count", 3))
        if has_blade else 0
    )

    az0 = (
        params["blade"].get("azimuth_deg", 0.0)
        if has_blade else 0.0
    )

    root_r = (
        params["blade"]["stations"][0]["chord"] / 2
        if has_blade else 0.0
    )

    r_top = sections[-1]["d1"] / 2
    disc_area = math.pi * r_top**2

    def in_nacelle_box(x, y, z, eps=1e-6):
        return (
            abs(x) <= nac["width"] / 2 + eps
            and nac["y_rear"] - eps <= y <= nac["y_front"] + eps
            and z_top - eps <= z <= z_top + nac["height"] + eps
        )

    for _, s in gmsh.model.getEntities(2):

        typ = gmsh.model.getType(2, s)

        cx, cy, cz = occ.getCenterOfMass(2, s)

        xmin, ymin, zmin, xmax, ymax, zmax = (
            gmsh.model.getBoundingBox(2, s)
        )

        if has_head:
            dist_hub = math.dist(
                (cx, cy, cz), hub_c
            )

        # -------------------------------------------------
        # Tower lateral surfaces
        # -------------------------------------------------
        if typ in ("Cone", "Cylinder"):

            for i, sec in enumerate(sections):
                if (
                    sec["z0"] - 1e-6
                    <= cz
                    <= sec["z1"] + 1e-6
                ):
                    name = f"Tower_{i + 1}"

                    groups.setdefault(name, []).append(s)
                    thickness[name] = sec["t"]

        elif not has_head:
            continue

        # -------------------------------------------------
        # Tower top ring
        # -------------------------------------------------
        elif s in ring_tags:

            groups.setdefault(
                "TowerTopRing", []
            ).append(s)

            thickness["TowerTopRing"] = nac.get(
                "tower_ring_t", 0.03
            )

        # -------------------------------------------------
        # Hub
        # -------------------------------------------------
        elif typ == "Sphere":

            small = (
                max(
                    xmax - xmin,
                    ymax - ymin,
                    zmax - zmin
                ) < 2 * root_r + 0.3
            )

            if cy > nac["y_front"] and not (
                has_blade and small
            ):
                groups.setdefault("Hub", []).append(s)
                thickness["Hub"] = hub["t"]
            else:
                discard.append((2, s))

        # -------------------------------------------------
        # Nacelle planar surfaces
        # -------------------------------------------------
        elif typ == "Plane" and in_nacelle_box(
            cx, cy, cz
        ):

            on_front = (
                abs(cy - nac["y_front"]) < 1e-6
                and abs(ymax - ymin) < 1e-6
            )

            # Remove the small floor disk inside the
            # open tower top. The annular ring is retained
            # separately through ring_tags.
            on_floor_disc = (
                abs(zmax - zmin) < 1e-6
                and abs(cz - z_top) < 1e-6
                and math.hypot(cx, cy) < 1e-4
                and abs((xmax - xmin) - 2 * r_top) < 1e-3
                and abs(
                    occ.getMass(2, s) - disc_area
                ) < 1e-3 * disc_area
            )

            if on_floor_disc:
                discard.append((2, s))

            elif on_front and (
                xmax - xmin < nac["width"] * 0.99
            ):
                discard.append((2, s))

            else:
                groups.setdefault("Nacelle", []).append(s)
                thickness["Nacelle"] = nac["t"]

        # -------------------------------------------------
        # Blade surfaces
        # -------------------------------------------------
        elif has_blade:

            if dist_hub < hub["diameter"] / 2:
                discard.append((2, s))

            else:
                ang = math.degrees(
                    math.atan2(
                        cx - hub_c[0],
                        cz - hub_c[2]
                    )
                ) % 360

                k = int(
                    round(
                        (ang - az0) / (360.0 / n_bl)
                    )
                ) % n_bl

                name = f"Blade_{k + 1}"

                groups.setdefault(name, []).append(s)
                thickness[name] = params["blade"]["t"]

    if discard:
        occ.remove(discard, recursive=False)
        occ.synchronize()

    # -------------------------------------------------
    # Create physical groups
    # -------------------------------------------------
    for name, tags in groups.items():
        if not tags:
            continue

        gmsh.model.addPhysicalGroup(2, tags, name=name)

    return groups, thickness
