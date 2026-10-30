"""Default turbine generator (Member 1). Units: metres. Z up, rotor axis +Y.
Outer SURFACES only (shell model). Wall thickness is a number per tag.
Tags: Tower_1.. , Nacelle, Hub
"""
import json
import gmsh

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


def _nacelle_surfaces(nac, z_top):
    """Box faces (volume removed). Bottom face sits at z_top."""
    w, h = nac["width"], nac["height"]
    y0, y1 = nac["y_rear"], nac["y_front"]
    occ.addBox(-w / 2, y0, z_top, w, y1 - y0, h)
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

    tower = _tower_surfaces(sections)
    if has_head:
        nac, hub = params["nacelle"], params["hub"]
        nac_faces = _nacelle_surfaces(nac, z_top)
        hub_face = _hub_surface(hub, nac, z_top)
        allsurf = [(2, s) for s in tower + nac_faces + hub_face]
        occ.fragment(allsurf, [])          # make shared edges at all joints
    else:
        occ.removeAllDuplicates()
    occ.synchronize()

    # ---- classify every surface, delete the pieces that lie inside others
    groups = {}
    thickness = {}
    discard = []
    for (_, s) in gmsh.model.getEntities(2):
        typ = gmsh.model.getType(2, s)
        cx, cy, cz = occ.getCenterOfMass(2, s)
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(2, s)
        if typ in ("Cone", "Cylinder"):
            for i, sec in enumerate(sections):
                if sec["z0"] - 1e-6 <= cz <= sec["z1"] + 1e-6:
                    groups.setdefault(f"Tower_{i+1}", []).append(s)
                    thickness[f"Tower_{i+1}"] = sec["t"]
        elif has_head and typ == "Sphere":
            if cy > nac["y_front"]:
                groups.setdefault("Hub", []).append(s)
                thickness["Hub"] = hub["t"]
            else:
                discard.append((2, s))        # hub part inside the nacelle
        elif has_head:                         # planar box faces
            on_front = abs(cy - nac["y_front"]) < 1e-6 and abs(ymax - ymin) < 1e-6
            if on_front and (xmax - xmin) < nac["width"] * 0.99:
                discard.append((2, s))        # front-face disk inside the hub
            else:
                groups.setdefault("Nacelle", []).append(s)
                thickness["Nacelle"] = nac["t"]
    if discard:
        occ.remove(discard, recursive=False)
        occ.synchronize()
    for name, tags in groups.items():
        gmsh.model.addPhysicalGroup(2, tags, name=name)
    return groups, thickness