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
        if abs(s["d0"] - s["d1"]) < 1e-9:      # straight cylinder
            occ.addCylinder(0, 0, s["z0"], 0, 0, h, s["d0"] / 2)
        else:                                   # tapered cone
            occ.addCone(0, 0, s["z0"], 0, 0, h, s["d0"] / 2, s["d1"] / 2)
    occ.synchronize()
    vols = gmsh.model.getEntities(3)
    keep, disks = set(), []
    for (_, v) in vols:
        for (_, s) in gmsh.model.getBoundary([(3, v)], oriented=False):
            if gmsh.model.getType(2, s) in ("Cone", "Cylinder"):
                keep.add(s)
            else:
                disks.append((2, s))
    occ.remove(vols)
    occ.remove(disks, recursive=True)
    occ.synchronize()
    return sorted(keep)


def _nacelle_surfaces(nac, z_top, r_top):
    """Nacelle faces (volume removed). The floor sits at z_top.
    Optional "round" in the nacelle block: radius that rounds the 4 edges along the
    rotor axis, so the cross-section becomes a rounded rectangle. The front and rear
    faces stay flat, and the tower-top circle must fit on the flat part of the floor."""
    w, h = nac["width"], nac["height"]
    y0, y1 = nac["y_rear"], nac["y_front"]
    rnd = float(nac.get("round", 0.0))
    if rnd > 0:
        if rnd > min(w, h) / 2 - 0.1:
            raise ValueError("Nacelle rounding is larger than the nacelle can take.")
        if r_top + rnd + 0.1 > w / 2:
            raise ValueError("Nacelle rounding too large: the tower top must fit on the "
                             "flat part of the nacelle floor (reduce 'round' or widen the nacelle).")
    box = occ.addBox(-w / 2, y0, z_top, w, y1 - y0, h)
    occ.synchronize()
    if rnd > 0:
        faces = gmsh.model.getBoundary([(3, box)], oriented=False)
        curves = {c for f in faces for (_, c) in gmsh.model.getBoundary([f], oriented=False)}
        edges = []
        for c in curves:
            xa, ya, za, xb, yb, zb = gmsh.model.getBoundingBox(1, c)
            if abs(xb - xa) < 1e-6 and abs(zb - za) < 1e-6:     # edge runs along Y
                edges.append(c)
        occ.fillet([box], edges, [rnd])
        occ.synchronize()
    vols = [e for e in gmsh.model.getEntities(3)]
    faces = []
    for (_, v) in vols:
        faces += [s for (_, s) in gmsh.model.getBoundary([(3, v)], oriented=False)]
    occ.remove(vols)
    occ.synchronize()
    return faces


def _hub_surface(hub, nac, z_top):
    zc = z_top + nac["height"] / 2
    t = occ.addSphere(0, hub["overhang"], zc, hub["diameter"] / 2)
    occ.synchronize()
    vols = [(3, t)]
    face = [s for (_, s) in gmsh.model.getBoundary(vols, oriented=False)]
    occ.remove(vols)
    occ.synchronize()
    return face


def build_default(params):
    gmsh.model.add("turbine")
    sections = params["tower"]["sections"]
    z_top = sections[-1]["z1"]
    has_head = "nacelle" in params and "hub" in params
    has_blade = has_head and "blade" in params

    tower = _tower_surfaces(sections)
    blades = []
    if has_head:
        nac, hub = params["nacelle"], params["hub"]
        hub_c = (0.0, hub["overhang"], z_top + nac["height"] / 2)
        nac_faces = _nacelle_surfaces(nac, z_top, sections[-1]["d1"] / 2)
        hub_face = _hub_surface(hub, nac, z_top)
        if has_blade:
            blades = build_blades(params["blade"], hub_c)
        flat = [t for b in blades for t in b]
        occ.fragment([(2, s) for s in tower + nac_faces + hub_face + flat], [])
    else:
        occ.removeAllDuplicates()
    occ.synchronize()

    # ---- classify every surface, delete the pieces that lie inside others
    groups, thickness, discard = {}, {}, []
    n_bl = int(params["blade"].get("count", 3)) if has_blade else 0
    az0 = params["blade"].get("azimuth_deg", 0.0) if has_blade else 0.0
    root_r = params["blade"]["stations"][0]["chord"] / 2 if has_blade else 0.0

    # tower-top circle: used to find the disc that fragment() creates inside
    # the nacelle floor (open tower top)
    r_top = sections[-1]["d1"] / 2
    disc_area = math.pi * r_top ** 2

    def in_nacelle_box(x, y, z, eps=1e-6):
        return (abs(x) <= nac["width"] / 2 + eps and
                nac["y_rear"] - eps <= y <= nac["y_front"] + eps and
                z_top - eps <= z <= z_top + nac["height"] + eps)

    for (_, s) in gmsh.model.getEntities(2):
        typ = gmsh.model.getType(2, s)
        cx, cy, cz = occ.getCenterOfMass(2, s)
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(2, s)
        if has_head:
            dist_hub = math.dist((cx, cy, cz), hub_c)
        # Nacelle first: every surface whose centre lies inside the nacelle box
        # (flat faces AND rounded strips), except pieces of the hub sphere.
        if has_head and (typ != "Sphere" or dist_hub > hub["diameter"] / 2 + 0.5) \
                and in_nacelle_box(cx, cy, cz):
            on_front = abs(cy - nac["y_front"]) < 1e-6 and abs(ymax - ymin) < 1e-6
            # open tower top: planar disc inside the tower-top circle, lying in
            # the nacelle floor plane (found by position and size, not by ID)
            on_floor_disc = (typ == "Plane"
                             and abs(zmax - zmin) < 1e-6
                             and abs(cz - z_top) < 1e-6
                             and math.hypot(cx, cy) < 1e-4
                             and abs((xmax - xmin) - 2 * r_top) < 1e-3
                             and abs(occ.getMass(2, s) - disc_area) < 1e-3 * disc_area)
            if on_floor_disc:
                discard.append((2, s))        # disc inside tower-top circle
            elif (typ == "Plane" and on_front
                  and occ.getMass(2, s) < 0.5 * nac["width"] * nac["height"]):
                discard.append((2, s))        # front-face disk inside the hub (by area)
            else:
                groups.setdefault("Nacelle", []).append(s)
                thickness["Nacelle"] = nac["t"]
        elif typ in ("Cone", "Cylinder"):
            for i, sec in enumerate(sections):
                if sec["z0"] - 1e-6 <= cz <= sec["z1"] + 1e-6:
                    groups.setdefault(f"Tower_{i+1}", []).append(s)
                    thickness[f"Tower_{i+1}"] = sec["t"]
        elif not has_head:
            continue
        elif typ == "Sphere":
            small = max(xmax - xmin, ymax - ymin, zmax - zmin) < 2 * root_r + 0.3
            if cy > nac["y_front"] and not (has_blade and small):
                groups.setdefault("Hub", []).append(s)
                thickness["Hub"] = hub["t"]
            else:
                discard.append((2, s))        # inside nacelle or inside a blade root
        elif has_blade:
            if dist_hub < hub["diameter"] / 2:
                discard.append((2, s))        # blade part inside the hub
            else:
                # which blade? angle of the centroid in the rotor plane (X-Z)
                ang = math.degrees(math.atan2(cx - hub_c[0], cz - hub_c[2])) % 360
                k = int(round((ang - az0) / (360.0 / n_bl))) % n_bl
                groups.setdefault(f"Blade_{k+1}", []).append(s)
                thickness[f"Blade_{k+1}"] = params["blade"]["t"]
    if discard:
        occ.remove(discard, recursive=False)
        occ.synchronize()

    # ---- yaw: turn the nacelle, hub and blades about the tower axis (Z through
    # the origin). The tower is round, so turning the WHOLE model is the same as
    # turning only the head, and every shared edge stays shared.
    # Positive yaw = counter-clockwise seen from above (right-hand rule about +Z).
    yaw = float(params.get("yaw_deg", 0.0))
    if has_head and abs(yaw) > 1e-9:
        occ.rotate(gmsh.model.getEntities(), 0, 0, 0, 0, 0, 1, math.radians(yaw))
        occ.synchronize()

    for name, tags in groups.items():
        gmsh.model.addPhysicalGroup(2, tags, name=name)
    return groups, thickness