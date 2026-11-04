"""Group an imported STEP model into Tower, Nacelle, Hub and Blades (Member 1, part B).

Works on the model after step_import.import_step(): metres, Z up, tower base
centre at the origin. Designed for assemblies of solids (volumes). Each part is
classified by the centre of its bounding box:

  distance from the tower axis / model height H  >  rotor_r_min
        -> rotor part: Blades if its longest side / H > blade_len_min, else Hub
  otherwise, centre height / H  >=  nacelle_z_min   -> Nacelle
  otherwise                                         -> Tower

All thresholds are fractions of the model height H, so they do not change when
the model is scaled.

Library use:
    from step_import import import_step
    from grouping import group_model
    import_step("model.step", up_axis="Y")
    report = group_model(tower_height=87.6)       # None = do not scale

Command line:
    python grouping.py "C:/step_test/model_b/Mini Wind Turbine.STEP" --up Y
    python grouping.py "C:/step_test/model_b/Mini Wind Turbine.STEP" --up Y --tower-height 87.6
    options: --rotor-r 0.075   --nacelle-z 0.62   --blade-len 0.20
             --min-frac 0.02   --nogui
"""
import sys
import math
import argparse
import gmsh
from step_import import import_step, StepImportError, _top_dim, _parts_bounds

DEFAULTS = {
    "rotor_r_min": 0.075,   # farther than this (x H) from the tower axis -> hub or blade
    "nacelle_z_min": 0.62,  # near the axis and above this height (x H) -> nacelle
    "blade_len_min": 0.20,  # rotor part with longest side above this (x H) -> blade
}
GROUP_NAMES = ["Tower", "Nacelle", "Hub", "Blades"]
COLOURS = {"Tower": (150, 150, 150), "Nacelle": (230, 160, 30),
           "Hub": (200, 40, 40), "Blades": (40, 110, 220)}


class GroupingError(Exception):
    """Raised with a clear message when the model cannot be grouped."""


def classify(th):
    """Return (dim, groups, H). groups maps group name -> list of entity tags."""
    dim = _top_dim()
    lo, hi = _parts_bounds(dim)
    H = hi[2] - lo[2]
    if H <= 0:
        raise GroupingError("The model has zero height")
    groups = {g: [] for g in GROUP_NAMES}
    for _, e in gmsh.model.getEntities(dim):
        b = gmsh.model.getBoundingBox(dim, e)
        cx, cy, cz = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2
        r = math.hypot(cx, cy) / H               # distance from the tower (z) axis
        z = (cz - lo[2]) / H                     # centre height
        longest = max(b[3] - b[0], b[4] - b[1], b[5] - b[2]) / H
        if r > th["rotor_r_min"]:
            g = "Blades" if longest > th["blade_len_min"] else "Hub"
        elif z >= th["nacelle_z_min"]:
            g = "Nacelle"
        else:
            g = "Tower"
        groups[g].append(e)
    return dim, groups, H


def _check(groups):
    for g in ("Tower", "Blades"):
        if not groups[g]:
            raise GroupingError(
                f"No parts were classified as {g}. Try changing the thresholds "
                "(--rotor-r, --nacelle-z, --blade-len).")


def _tower_top(dim, groups):
    """Height of the top of the Tower group (the base is at z = 0)."""
    return max(gmsh.model.getBoundingBox(dim, e)[5] for e in groups["Tower"])


def _face_count(dim, ents):
    faces = set()
    for e in ents:
        if dim == 3:
            for _, t in gmsh.model.getBoundary([(3, e)], combined=False, oriented=False):
                faces.add(abs(t))
        else:
            faces.add(e)
    return len(faces)


def group_model(tower_height=None, thresholds=None):
    """Classify the current gmsh model, optionally scale it so the Tower group is
    `tower_height` metres tall, and add one physical group per class.
    Returns a dict with a report."""
    gmsh.model.removePhysicalGroups()   # re-running must not duplicate the groups
    th = dict(DEFAULTS)
    if thresholds:
        unknown = set(thresholds) - set(DEFAULTS)
        if unknown:
            raise GroupingError(f"Unknown threshold(s): {sorted(unknown)}")
        th.update(thresholds)

    dim, groups, H = classify(th)
    _check(groups)

    factor = 1.0
    if tower_height is not None:
        if tower_height <= 0:
            raise GroupingError("The tower height must be a positive number of metres")
        current = _tower_top(dim, groups)
        if current <= 0:
            raise GroupingError("Could not measure the tower height")
        factor = tower_height / current
        gmsh.model.occ.dilate(gmsh.model.getEntities(), 0, 0, 0, factor, factor, factor)
        gmsh.model.occ.synchronize()
        dim, groups, H = classify(th)            # same result: thresholds are relative to H
        _check(groups)

    for g, ents in groups.items():
        if ents:
            gmsh.model.addPhysicalGroup(dim, ents, name=g)

    warnings = [f"No parts were classified as {g}" for g in ("Nacelle", "Hub") if not groups[g]]
    lo, hi = _parts_bounds(dim)
    return {
        "dim": dim,
        "thresholds": th,
        "factor": factor,
        "tower_height_m": _tower_top(dim, groups),
        "size_m": [round(hi[i] - lo[i], 4) for i in range(3)],
        "groups": {g: {"parts": sorted(groups[g]), "faces": _face_count(dim, groups[g])}
                   for g in GROUP_NAMES},
        "warnings": warnings,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--up", default="Z", choices=["X", "Y", "Z", "x", "y", "z"])
    ap.add_argument("--min-frac", type=float, default=0.02)
    ap.add_argument("--tower-height", type=float, default=None,
                    help="scale the model so the Tower group is this tall (metres)")
    ap.add_argument("--rotor-r", type=float, default=DEFAULTS["rotor_r_min"])
    ap.add_argument("--nacelle-z", type=float, default=DEFAULTS["nacelle_z_min"])
    ap.add_argument("--blade-len", type=float, default=DEFAULTS["blade_len_min"])
    ap.add_argument("--nogui", action="store_true")
    a = ap.parse_args()

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    try:
        imp = import_step(a.path, up_axis=a.up, min_part_frac=a.min_frac)
        rep = group_model(a.tower_height, {"rotor_r_min": a.rotor_r,
                                           "nacelle_z_min": a.nacelle_z,
                                           "blade_len_min": a.blade_len})
    except (StepImportError, GroupingError) as e:
        print("ERROR:", e)
        gmsh.finalize()
        sys.exit(1)

    th = rep["thresholds"]
    print(f"Imported: {imp['volumes_before']} -> {imp['volumes_after']} volumes")
    print(f"Thresholds (x model height): rotor_r_min={th['rotor_r_min']}, "
          f"nacelle_z_min={th['nacelle_z_min']}, blade_len_min={th['blade_len_min']}")
    print(f"{'Group':<9}{'parts':>6}{'faces':>7}   part ids")
    total_faces = 0
    for g in GROUP_NAMES:
        info = rep["groups"][g]
        total_faces += info["faces"]
        print(f"{g:<9}{len(info['parts']):>6}{info['faces']:>7}   {info['parts']}")
    print("Total faces:", total_faces)
    if a.tower_height is not None:
        print(f"Scale factor {rep['factor']:.4f}; tower height now "
              f"{rep['tower_height_m']:.3f} m (asked for {a.tower_height})")
    else:
        print(f"Tower height (not scaled): {rep['tower_height_m']:.4f} m")
    print("Model size in metres (x, y, z):", rep["size_m"])
    for w in rep["warnings"]:
        print("WARNING:", w)

    if not a.nogui:
        for g in GROUP_NAMES:
            ents = [(rep["dim"], e) for e in rep["groups"][g]["parts"]]
            if ents:
                gmsh.model.setColor(ents, *COLOURS[g], recursive=True)
        gmsh.option.setNumber("Geometry.Surfaces", 1)
        gmsh.fltk.run()
    gmsh.finalize()