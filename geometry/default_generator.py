
"""Default turbine generator (Member 1). Units: metres. Z up, rotor axis +Y.
Outer SURFACES only (shell model). Wall thickness is a number per tag.
Tags: Tower_1.. , Nacelle, Hub, Blade_1..3
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
    """Lateral cone surface per section (solids and end-disks removed)."""

    for s in sections:
        h = s["z1"] - s["z0"]

        if abs(s["d0"] - s["d1"]) < 1e-9:
            # Straight cylindrical section
            occ.addCylinder(
                0, 0, s["z0"],
                0, 0, h,
                s["d0"] / 2
            )
        else:
            # Tapered conical section
            occ.addCone(
                0, 0, s["z0"],
                0, 0, h,
                s["d0"] / 2,
                s["d1"] / 2
            )

    occ.synchronize()

    vols = gmsh.model.getEntities(3)
    keep, disks = set(), []

    for (_, v) in vols:
        for (_, s) in gmsh.model.getBoundary(
            [(3, v)], oriented=False
        ):
            if gmsh.model.getType(2, s) in ("Cone", "Cylinder"):
                keep.add(s)
            else:
                disks.append((2, s))

    occ.remove(vols)
    occ.remove(disks, recursive=True)
    occ.synchronize()

    return sorted(keep)


def _nacelle_surfaces(nac, z_top):
    """Box faces (volume removed). Bottom face sits at z_top."""

    w, h = nac["width"], nac["height"]
    y0, y1 = nac["y_rear"], nac["y_front"]

    occ.addBox(-w / 2, y0, z_top, w, y1 - y0, h)
    occ.synchronize()

    vols = gmsh.model.getEntities(3)
    faces = []

    for (_, v) in vols:
        faces += [
            s for (_, s) in gmsh.model.getBoundary(
                [(3, v)], oriented=False
            )
        ]

    occ.remove(vols)
    occ.synchronize()

    return faces


def _hub_surface(hub, nac, z_top):
    """Create the outer spherical surface of the hub."""

    zc = z_top + nac["height"] / 2

    t = occ.addSphere(
        0,
        hub["overhang"],
        zc,
        hub["diameter"] / 2
    )

    occ.synchronize()

    vols = [(3, t)]
    face = [
        s for (_, s) in gmsh.model.getBoundary(
            vols, oriented=False
        )
    ]

    occ.remove(vols)
    occ.synchronize()

    return face


def build_default(params, tower_only=False):

    gmsh.model.add("turbine")

    sections = params["tower"]["sections"]
    z_top = sections[-1]["z1"]

    # Check whether head-component data exists
    has_head = (
        "nacelle" in params and
        "hub" in params
    )

    # Decide whether head components should actually be generated
    include_head = not tower_only and has_head

    # Blades can only be included if the head is included
    has_blade = include_head and "blade" in params

    # --------------------------------------------------
    # 1. GENERATE GEOMETRY
    # --------------------------------------------------

    # Tower is always generated
    tower = _tower_surfaces(sections)

    blades = []

    # Generate nacelle, hub and blades only when required
    if include_head:

        nac = params["nacelle"]
        hub = params["hub"]

        hub_c = (
            0.0,
            hub["overhang"],
            z_top + nac["height"] / 2
        )

        nac_faces = _nacelle_surfaces(nac, z_top)
        hub_face = _hub_surface(hub, nac, z_top)

        if has_blade:
            blades = build_blades(params["blade"], hub_c)

        flat = [t for b in blades for t in b]

        # Join intersecting surfaces and split them at intersections
        occ.fragment(
            [(2, s) for s in tower + nac_faces + hub_face + flat],
            []
        )

    else:
        # Clean up duplicate geometry in tower-only mode
        occ.removeAllDuplicates()

    occ.synchronize()

    # --------------------------------------------------
    # 2. CLASSIFY SURFACES INTO COMPONENT GROUPS
    # --------------------------------------------------

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

    # This helper is only needed when head components exist
    def in_nacelle_box(x, y, z, eps=1e-6):

        return (
            abs(x) <= nac["width"] / 2 + eps
            and nac["y_rear"] - eps <= y <= nac["y_front"] + eps
            and z_top - eps <= z <= z_top + nac["height"] + eps
        )

    # Examine every surface in the Gmsh model
    for (_, s) in gmsh.model.getEntities(2):

        typ = gmsh.model.getType(2, s)

        cx, cy, cz = occ.getCenterOfMass(2, s)

        xmin, ymin, zmin, xmax, ymax, zmax = (
            gmsh.model.getBoundingBox(2, s)
        )

        # Calculate distance from hub only if head exists
        if include_head:
            dist_hub = math.dist(
                (cx, cy, cz),
                hub_c
            )

        # ----------------------------------------------
        # Tower classification
        # ----------------------------------------------

        if typ in ("Cone", "Cylinder"):

            for i, sec in enumerate(sections):

                if (
                    sec["z0"] - 1e-6 <= cz
                    <= sec["z1"] + 1e-6
                ):

                    name = f"Tower_{i+1}"

                    groups.setdefault(name, []).append(s)
                    thickness[name] = sec["t"]

        # If we are generating only the tower,
        # ignore every remaining surface
        elif not include_head:
            continue

        # ----------------------------------------------
        # Hub classification
        # ----------------------------------------------

        elif typ == "Sphere":

            small = max(
                xmax - xmin,
                ymax - ymin,
                zmax - zmin
            ) < 2 * root_r + 0.3

            if cy > nac["y_front"] and not (has_blade and small):

                groups.setdefault("Hub", []).append(s)
                thickness["Hub"] = hub["t"]

            else:
                # Surface lies inside nacelle or blade root
                discard.append((2, s))

        # ----------------------------------------------
        # Nacelle classification
        # ----------------------------------------------

        elif typ == "Plane" and in_nacelle_box(cx, cy, cz):

            on_front = (
                abs(cy - nac["y_front"]) < 1e-6
                and abs(ymax - ymin) < 1e-6
            )

            if on_front and (xmax - xmin) < nac["width"] * 0.99:

                # Front-face disk inside the hub
                discard.append((2, s))

            else:

                groups.setdefault("Nacelle", []).append(s)
                thickness["Nacelle"] = nac["t"]

        # ----------------------------------------------
        # Blade classification
        # ----------------------------------------------

        elif has_blade:

            if dist_hub < hub["diameter"] / 2:

                # Blade part inside the hub
                discard.append((2, s))

            else:

                # Identify which blade using its centroid angle
                # in the rotor plane (X-Z)

                ang = math.degrees(
                    math.atan2(
                        cx - hub_c[0],
                        cz - hub_c[2]
                    )
                ) % 360

                k = int(
                    round((ang - az0) / (360.0 / n_bl))
                ) % n_bl

                name = f"Blade_{k+1}"

                groups.setdefault(name, []).append(s)
                thickness[name] = params["blade"]["t"]

    # --------------------------------------------------
    # 3. REMOVE UNWANTED SURFACES
    # --------------------------------------------------

    if discard:

        occ.remove(discard, recursive=False)
        occ.synchronize()

    # --------------------------------------------------
    # 4. CREATE PHYSICAL GROUPS
    # --------------------------------------------------

    for name, tags in groups.items():

        gmsh.model.addPhysicalGroup(
            2,
            tags,
            name=name
        )

    return groups, thickness
