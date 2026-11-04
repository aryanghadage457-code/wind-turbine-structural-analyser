"""STEP importer (Member 1, part B).

Loads a STEP file into gmsh and brings it to the project conventions:
metres, Z up, tower base centre at the origin. Removes tiny parts
(bolts, bearings) by size.

Units: gmsh converts the units declared inside the STEP file to metres
while reading (Geometry.OCCTargetUnit = "M").

Library use:
    from step_import import import_step
    report = import_step("model.step", up_axis="Y")

Command line:
    python step_import.py "C:/step_test/model_b/Mini Wind Turbine.STEP" --up Y
    options: --min-frac 0.02   (remove parts smaller than 2 % of the model size)
             --nogui           (no window)
             --out cleaned.step
"""
import sys
import math
import argparse
import gmsh


class StepImportError(Exception):
    """Raised with a clear message when a file cannot be used."""


def _top_dim():
    """3 if the model has volumes, else 2 (surface-only files)."""
    return 3 if gmsh.model.getEntities(3) else 2


def _parts_bounds(dim=None):
    """Overall bounds from the per-part boxes (gmsh's whole-model box
    becomes inaccurate after rotations)."""
    dim = dim or _top_dim()
    lo, hi = [1e30] * 3, [-1e30] * 3
    for _, e in gmsh.model.getEntities(dim):
        b = gmsh.model.getBoundingBox(dim, e)
        for i in range(3):
            lo[i] = min(lo[i], b[i])
            hi[i] = max(hi[i], b[i + 3])
    return lo, hi


def _diag(b):
    return math.sqrt((b[3] - b[0]) ** 2 + (b[4] - b[1]) ** 2 + (b[5] - b[2]) ** 2)


def import_step(path, up_axis="Z", min_part_frac=0.02):
    """Import `path` into the current gmsh model and normalise it.
    gmsh.initialize() must already have been called.
    Returns a dict with a report of what was done."""
    up_axis = up_axis.upper()
    if up_axis not in ("X", "Y", "Z"):
        raise StepImportError(f"up_axis must be X, Y or Z, got '{up_axis}'")
    if not str(path).lower().endswith((".step", ".stp")):
        raise StepImportError("File must end in .step or .stp")

    gmsh.model.add("uploaded")
    gmsh.option.setString("Geometry.OCCTargetUnit", "M")   # file units -> metres
    try:
        gmsh.model.occ.importShapes(path)
        gmsh.model.occ.synchronize()
    except Exception as e:
        raise StepImportError(f"Could not read the STEP file: {e}") from e

    n_vol0 = len(gmsh.model.getEntities(3))
    n_surf0 = len(gmsh.model.getEntities(2))
    if n_surf0 == 0:
        raise StepImportError("The file loaded but contains no surfaces")
    report = {"volumes_before": n_vol0, "surfaces_before": n_surf0, "removed": []}

    # 1) remove tiny parts (bounding-box diagonal relative to whole model)
    if n_vol0 > 1:
        lo, hi = _parts_bounds(3)
        whole = _diag(lo + hi)
        small = []
        for _, v in gmsh.model.getEntities(3):
            d = _diag(gmsh.model.getBoundingBox(3, v))
            if d < min_part_frac * whole:
                small.append((3, v))
                report["removed"].append((v, round(d, 4)))
        if len(small) == n_vol0:
            raise StepImportError("All parts are smaller than the size threshold; "
                                  "lower min_part_frac")
        if small:
            gmsh.model.occ.remove(small, recursive=True)
            gmsh.model.occ.synchronize()

    top = _top_dim()

    # 2) up axis -> +Z
    if up_axis == "Y":      # rotate +90 deg about X: Y -> Z
        gmsh.model.occ.rotate(gmsh.model.getEntities(), 0, 0, 0, 1, 0, 0, math.pi / 2)
    elif up_axis == "X":    # rotate -90 deg about Y: X -> Z
        gmsh.model.occ.rotate(gmsh.model.getEntities(), 0, 0, 0, 0, 1, 0, -math.pi / 2)
    gmsh.model.occ.synchronize()

    # 3) put the base on z = 0 and its centre on the origin
    lo, hi = _parts_bounds(top)
    height = hi[2] - lo[2]
    base = [gmsh.model.getBoundingBox(top, e) for _, e in gmsh.model.getEntities(top)]
    base = [b for b in base if b[2] < lo[2] + 0.01 * height]
    cx = (min(b[0] for b in base) + max(b[3] for b in base)) / 2
    cy = (min(b[1] for b in base) + max(b[4] for b in base)) / 2
    gmsh.model.occ.translate(gmsh.model.getEntities(), -cx, -cy, -lo[2])
    gmsh.model.occ.synchronize()

    lo, hi = _parts_bounds(top)
    report.update({
        "volumes_after": len(gmsh.model.getEntities(3)),
        "surfaces_after": len(gmsh.model.getEntities(2)),
        "bounds_m": [round(v, 4) for v in lo + hi],
        "size_m": [round(hi[i] - lo[i], 4) for i in range(3)],
    })
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--up", default="Z", choices=["X", "Y", "Z", "x", "y", "z"])
    ap.add_argument("--min-frac", type=float, default=0.02)
    ap.add_argument("--nogui", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    try:
        rep = import_step(a.path, up_axis=a.up, min_part_frac=a.min_frac)
    except StepImportError as e:
        print("IMPORT ERROR:", e)
        gmsh.finalize()
        sys.exit(1)

    print(f"Volumes: {rep['volumes_before']} -> {rep['volumes_after']}")
    print(f"Surfaces: {rep['surfaces_before']} -> {rep['surfaces_after']}")
    print(f"Removed {len(rep['removed'])} small parts")
    for tag, size in rep['removed'][:10]:
        print(f"   removed part {tag}, size {size} m")
    if len(rep['removed']) > 10:
        print(f"   ... and {len(rep['removed']) - 10} more")
    print("Size in metres (x, y, z):", rep["size_m"])
    print("Bounds (xmin,ymin,zmin,xmax,ymax,zmax):", rep["bounds_m"])
    if a.out:
        gmsh.write(a.out)
        print("Wrote", a.out)
    if not a.nogui:
        gmsh.option.setNumber("Geometry.Surfaces", 1)
        gmsh.fltk.run()
    gmsh.finalize()