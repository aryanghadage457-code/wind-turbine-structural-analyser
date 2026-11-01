"""Upload check (Member 1, part B): is a user's STEP file usable?

Run it from the folder that holds step_import.py and grouping.py:
    python check_upload.py "model.step" --up Y --tower-height 87.6

Options
    --up X|Y|Z        which axis of the file points up (default Z)
    --tower-height M  scale so the tower is this tall in metres (default: no scaling)
    --min-frac F      remove parts smaller than F x model size (default 0.02)
    --size M          trial-mesh element size in metres (default: model height / 50)
    --rotor-r --nacelle-z --blade-len   grouping thresholds (see grouping.py)

What it checks (PASS / WARN / FAIL / INFO)
    file       exists, under the upload limit
    import     step_import.import_step, small parts removed (listed)
    grouping   grouping.group_model, blade count
    size       overall height, scale factor, proportions (unit-mix-up warnings)
    mesh       trial surface mesh: succeeds, time, triangle count, empty surfaces
    connect    connected bodies, gaps between parts, free (open) edges
    normals    for each surface of each solid: does its triangle normal point out of
               the solid? (probe test: step a little way along the normal and ask
               gmsh whether that point is inside the solid)
    rotor      which way the rotor faces (project convention: +Y at yaw 0)

Library use (gmsh.initialize() must already have been called):
    from check_upload import run_checks
    out = run_checks("model.step", up_axis="Y", tower_height=87.6)
    out["results"]        list of (level, text)
    out["faces_to_flip"]  surface tags whose triangle order must be reversed
"""
import os
import sys
import math
import time
import argparse

import numpy as np
import gmsh

from step_import import import_step, StepImportError, _top_dim, _parts_bounds
from grouping import group_model, GroupingError, DEFAULTS, GROUP_NAMES

MAX_FILE_MB = 50           # upload limit: change if the team decides differently
MAX_TRIANGLES = 400_000    # above this the solver will be slow
MAX_MESH_SECONDS = 60
MAX_PAIR_PARTS = 40        # the part-to-part gap check is skipped above this many parts
TOUCH_TOL_FRAC = 2e-4      # parts closer than this x model height count as touching
MAX_NORMALS_SECONDS = 120  # time budget for the normals probe test


# ------------------------------------------------------------ pure functions
def components_from_triangles(tris, n_nodes):
    """Connected components of a triangle mesh (triangles sharing a node).
    Returns one component label per triangle."""
    parent = list(range(n_nodes))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, c in tris.tolist():
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
        rc, ra = find(c), find(a)
        if rc != ra:
            parent[rc] = ra
    return np.array([find(a) for a in tris[:, 0].tolist()], dtype=np.int64)


def group_by_gap(n, dists, tol):
    """Union parts whose minimum distance is <= tol.
    dists: {(i, j): distance or None}. Returns (labels, gaps) where gaps maps a
    pair of group labels to (smallest distance, part i, part j)."""
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (i, j), d in dists.items():
        if d is not None and d <= tol:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri
    labels = [find(i) for i in range(n)]
    gaps = {}
    for (i, j), d in dists.items():
        if d is None or labels[i] == labels[j]:
            continue
        key = tuple(sorted((labels[i], labels[j])))
        if key not in gaps or d < gaps[key][0]:
            gaps[key] = (d, i, j)
    return labels, gaps


def edge_report(tris, n_nodes):
    """Classify mesh edges: free (1 triangle), shared (2), non-manifold (>2),
    and 'bad' = shared by two triangles that traverse it in the same direction."""
    a = tris.ravel()
    b = np.roll(tris, -1, axis=1).ravel()
    tri_of_edge = np.repeat(np.arange(len(tris)), 3)
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    key = lo.astype(np.int64) * n_nodes + hi
    sign = np.where(a < b, 1, -1)
    uniq, inv, counts = np.unique(key, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    sums = np.bincount(inv, weights=sign)
    return {"key": key, "inv": inv, "tri_of_edge": tri_of_edge, "uniq": uniq,
            "counts": counts, "free": counts == 1, "shared": counts == 2,
            "nonmanifold": counts > 2, "bad": (counts == 2) & (sums != 0)}


def signed_volume(coords, tris):
    """Volume enclosed by a closed, outward-oriented triangle set (divergence
    theorem). Negative if the triangles are ordered inward."""
    if len(tris) == 0:
        return 0.0
    A, B, C = coords[tris[:, 0]], coords[tris[:, 1]], coords[tris[:, 2]]
    return float(np.einsum("ij,ij->i", A, np.cross(B, C)).sum() / 6.0)


def probe_verdict(is_inside, point, normal, edge_len, fractions=(0.3, 0.1, 0.03)):
    """Does a triangle's normal point out of its solid?

    is_inside(xyz) -> bool tells whether a point is inside the solid.
    From the triangle centre, step a distance eps along +normal and along
    -normal. Exactly one of the two points should be inside the solid:
      the -normal point inside  -> the normal points outward
      the +normal point inside  -> the normal points inward
    A first, large step (0.3 x triangle size) is much bigger than the small gap
    between a curved surface and its flat triangles. Smaller steps are tried only
    if the solid is too thin for the large one. Returns 'outward', 'inward'
    or 'unclear'."""
    n = np.asarray(normal, dtype=float)
    ln = float(np.linalg.norm(n))
    if ln == 0.0 or edge_len <= 0.0:
        return "unclear"
    n = n / ln
    p = np.asarray(point, dtype=float)
    for f in fractions:
        eps = f * edge_len
        plus = bool(is_inside(p + eps * n))
        minus = bool(is_inside(p - eps * n))
        if plus != minus:
            return "inward" if plus else "outward"
    return "unclear"


def heading_from_plus_y(dx, dy):
    """Angle in degrees, counter-clockwise seen from above, from +Y to (dx, dy)."""
    return math.degrees(math.atan2(-dx, dy))


def size_warnings(size_m, factor, scaled):
    """Plausibility warnings for the final model size (unit mix-ups)."""
    sx, sy, sz = size_m
    out = []
    if sz < 5 or sz > 400:
        out.append(("WARN", f"overall height is {sz:.2f} m, unusual for a turbine; "
                            "check the units and the up axis"))
    if scaled and (factor > 50 or factor < 0.02):
        out.append(("WARN", f"scale factor {factor:.3g} is very large or small; the "
                            "file may have the wrong units (a factor near 1000 means "
                            "mm and m were mixed)"))
    if sz > 0:
        span = max(sx, sy) / sz
        if not 0.3 <= span <= 2.0:
            out.append(("WARN", f"widest horizontal size is {span:.2f} x the height; "
                                "a turbine is usually 0.5 to 1.5"))
    if not out:
        out.append(("PASS", f"size looks like a turbine: {sx:.1f} x {sy:.1f} x {sz:.1f} m"))
    return out


# ------------------------------------------------------------- gmsh helpers
def _surface_triangles(lut):
    """{surface tag: (n, 3) array of node indices} from the current 2D mesh."""
    out = {}
    for _, s in gmsh.model.getEntities(2):
        etypes, _, enodes = gmsh.model.mesh.getElements(2, s)
        blocks = []
        for et, nodes in zip(etypes, enodes):
            if et == 2:
                blocks.append(lut[np.array(nodes, dtype=np.int64)].reshape(-1, 3))
        out[s] = np.vstack(blocks) if blocks else np.zeros((0, 3), dtype=np.int64)
    return out


def bbox_gap(b1, b2):
    """Distance between two axis-aligned boxes (xmin, ymin, zmin, xmax, ymax, zmax).
    0 if they overlap. It never exceeds the true distance between the parts."""
    gx = max(0.0, max(b1[0], b2[0]) - min(b1[3], b2[3]))
    gy = max(0.0, max(b1[1], b2[1]) - min(b1[4], b2[4]))
    gz = max(0.0, max(b1[2], b2[2]) - min(b1[5], b2[5]))
    return math.sqrt(gx * gx + gy * gy + gz * gz)


def _pair_distances(dim, ents, far, progress=None):
    """Minimum distance between every pair of parts. Pairs whose boxes are more
    than `far` apart are not measured exactly: their box gap is used instead
    (a lower bound), which keeps this fast on complex solids."""
    boxes = [gmsh.model.getBoundingBox(dim, int(e)) for e in ents]
    d, n_exact = {}, 0
    pairs = [(i, j) for i in range(len(ents)) for j in range(i + 1, len(ents))]
    for k, (i, j) in enumerate(pairs):
        g = bbox_gap(boxes[i], boxes[j])
        if g > far:
            d[(i, j)] = g
            continue
        n_exact += 1
        try:
            d[(i, j)] = gmsh.model.occ.getDistance(dim, int(ents[i]), dim, int(ents[j]))[0]
        except Exception:
            d[(i, j)] = None
        if progress and n_exact % 10 == 0:
            progress(f"measured {n_exact} close pairs ({k + 1} of {len(pairs)} pairs looked at)")
    return d, n_exact, len(pairs)


def _centre(dim, e):
    b = gmsh.model.getBoundingBox(dim, e)
    return ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2)


def _mean_centre(dim, ents):
    cs = [_centre(dim, e) for e in ents]
    if not cs:
        return None
    return tuple(sum(c[i] for c in cs) / len(cs) for i in range(3))


def _surface_verdict(volume, tris, coords, n_samples=3):
    """Probe a few triangles of one surface against its solid. Returns
    'outward', 'inward' or 'unclear' (majority of the decisive samples)."""
    if tris is None or len(tris) == 0:
        return "unclear"

    def inside(p):
        return gmsh.model.isInside(3, int(volume), [float(p[0]), float(p[1]), float(p[2])]) > 0

    picks = sorted(set([0, len(tris) // 2, len(tris) - 1]))[:n_samples]
    votes = {"outward": 0, "inward": 0}
    for i in picks:
        A, B, C = coords[tris[i]]
        normal = np.cross(B - A, C - A)
        size = (np.linalg.norm(B - A) + np.linalg.norm(C - B) + np.linalg.norm(A - C)) / 3.0
        r = probe_verdict(inside, (A + B + C) / 3.0, normal, size)
        if r in votes:
            votes[r] += 1
    if votes["outward"] == votes["inward"]:
        return "unclear"
    return "outward" if votes["outward"] > votes["inward"] else "inward"


def _probe_normals(ents, surf_tris, coords, budget, progress=None):
    """Test every (solid, surface) pair. Returns (verdicts, owners, finished):
    verdicts {(volume, surface): verdict}; owners {surface: number of solids using it}."""
    t0 = time.time()
    todo, owners = [], {}
    for v in ents:
        bnd = gmsh.model.getBoundary([(3, v)], combined=False, oriented=False, recursive=False)
        for _, s in bnd:
            s = abs(s)
            owners[s] = owners.get(s, 0) + 1
            todo.append((v, s))
    verdicts, finished = {}, True
    for k, (v, s) in enumerate(todo):
        if time.time() - t0 > budget:
            finished = False
            break
        verdicts[(v, s)] = _surface_verdict(v, surf_tris.get(s), coords)
        if progress and (k + 1) % 50 == 0:
            progress(f"tested {k + 1} of {len(todo)} surfaces")
    return verdicts, owners, finished, len(todo)


# --------------------------------------------------------------- main checks
def run_checks(path, up_axis="Z", tower_height=None, min_frac=0.02, size=0.0,
               thresholds=None, echo=False):
    results = []
    out = {"results": results, "faces_to_flip": []}

    def add(level, text):
        results.append((level, text))
        if echo:
            print(f"{level:<5} {text}", flush=True)

    def step(text):
        if echo:
            print(f"...   {text}", flush=True)

    # ---- file
    if not os.path.isfile(path):
        add("FAIL", f"File not found: {path}")
        return out
    mb = os.path.getsize(path) / 1e6
    if mb > MAX_FILE_MB:
        add("FAIL", f"File is {mb:.1f} MB; the upload limit is {MAX_FILE_MB} MB")
        return out
    add("PASS", f"File found, {mb:.2f} MB (limit {MAX_FILE_MB} MB)")

    # ---- import
    step("importing the STEP file")
    try:
        imp = import_step(path, up_axis=up_axis, min_part_frac=min_frac)
    except StepImportError as e:
        add("FAIL", f"Import: {e}")
        return out
    add("PASS", f"Imported: {imp['volumes_before']} -> {imp['volumes_after']} volumes, "
                f"{imp['surfaces_before']} -> {imp['surfaces_after']} surfaces")
    if imp["removed"]:
        shown = ", ".join(f"{t} ({s} m)" for t, s in imp["removed"][:8])
        more = " ..." if len(imp["removed"]) > 8 else ""
        add("INFO", f"Removed {len(imp['removed'])} parts under {min_frac:.0%} of the model "
                    f"size: {shown}{more}. Make sure none of them is the hub or a blade.")

    # ---- grouping
    step("grouping parts" + (f" and scaling to a {tower_height} m tower" if tower_height else ""))
    try:
        rep = group_model(tower_height, thresholds)
    except GroupingError as e:
        add("FAIL", f"Grouping: {e}")
        return out
    parts_text = ", ".join(f"{g} {len(rep['groups'][g]['parts'])} parts/"
                           f"{rep['groups'][g]['faces']} faces" for g in GROUP_NAMES)
    add("PASS", "Grouped: " + parts_text)
    for w in rep["warnings"]:
        add("WARN", w)
    n_blades = len(rep["groups"]["Blades"]["parts"])
    if n_blades != 3:
        add("WARN", f"{n_blades} blade parts found; a 3-blade turbine is expected "
                    "(try --blade-len or --rotor-r)")

    # ---- size
    for level, text in size_warnings(rep["size_m"], rep["factor"], tower_height is not None):
        add(level, text)
    H = rep["size_m"][2]
    dim = rep["dim"]

    # ---- trial mesh
    h = size if size > 0 else H / 50.0
    gmsh.option.setNumber("Mesh.MeshSizeMax", h)
    gmsh.option.setNumber("Mesh.MeshSizeMin", h / 20.0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)
    step(f"building a trial surface mesh (element size {h:.2f} m); this can take a minute")
    t0 = time.time()
    try:
        gmsh.model.mesh.generate(2)
    except Exception as e:
        add("FAIL", f"Trial mesh failed at element size {h:.2f} m: {e}. "
                    "Try a larger --size, or the file has surfaces gmsh cannot mesh")
        return out
    secs = time.time() - t0

    ntags, ncoords, _ = gmsh.model.mesh.getNodes()
    if len(ntags) == 0:
        add("FAIL", "Trial mesh produced no nodes")
        return out
    coords = np.array(ncoords, dtype=float).reshape(-1, 3)
    lut = np.full(int(max(ntags)) + 1, -1, dtype=np.int64)
    lut[np.array(ntags, dtype=np.int64)] = np.arange(len(ntags))
    surf_tris = _surface_triangles(lut)
    non_empty = [t for t in surf_tris.values() if len(t)]
    if not non_empty:
        add("FAIL", "Trial mesh has no surface triangles")
        return out
    all_tris = np.vstack(non_empty)
    empty = sorted(s for s, t in surf_tris.items() if len(t) == 0)

    msg = f"Trial mesh at {h:.2f} m: {len(all_tris)} triangles in {secs:.1f} s"
    if empty:
        add("WARN", f"{msg}; {len(empty)} surfaces got no triangles (tags {empty[:10]})")
    elif len(all_tris) > MAX_TRIANGLES:
        add("WARN", f"{msg}; more than {MAX_TRIANGLES}, use a larger element size")
    elif secs > MAX_MESH_SECONDS:
        add("WARN", f"{msg}; slower than {MAX_MESH_SECONDS} s, use a larger element size")
    else:
        add("PASS", msg)

    # ---- connectivity
    step("checking connectivity and gaps")
    labels = components_from_triangles(all_tris, len(coords))
    n_comp = len(np.unique(labels))
    er = edge_report(all_tris, len(coords))
    n_free = int(er["free"].sum())
    ents = [e for _, e in gmsh.model.getEntities(dim)]

    if n_comp == 1:
        add("PASS", "One connected body in the mesh")
    elif len(ents) > MAX_PAIR_PARTS:
        add("WARN", f"{n_comp} separate bodies in the mesh ({len(ents)} parts: too many "
                    "for the part-to-part gap check)")
    else:
        step(f"measuring distances between {len(ents)} parts")
        dists, n_exact, n_pairs = _pair_distances(dim, ents, 0.1 * H, step)
        step(f"done: {n_exact} close pairs measured exactly, {n_pairs - n_exact} far pairs skipped")
        tol = TOUCH_TOL_FRAC * H
        glabels, gaps = group_by_gap(len(ents), dists, tol)
        n_groups = len(set(glabels))
        if n_groups == 1:
            add("WARN", f"{n_comp} separate bodies in the mesh, but every part touches "
                        f"another (gap <= {tol:.3f} m). They are not merged, so the mesh "
                        "shares no nodes between them: fuse them, or Member 2 must tie them")
        else:
            worst = sorted(gaps.values())[:3]
            where = "; ".join(f"parts {ents[i]} and {ents[j]}: {d:.3f} m" for d, i, j in worst)
            add("WARN", f"The parts form {n_groups} groups separated by gaps. Closest gaps: "
                        f"{where}. A gap this big means the model is not one connected structure")
    if dim == 3:
        if n_free == 0:
            add("PASS", "All surfaces are watertight (no free edges)")
        else:
            add("WARN", f"{n_free} free edges: some solids are not watertight")
    else:
        zs = np.unique(np.round(coords[er["uniq"][er["free"]] // len(coords), 2], 2)) \
            if n_free else []
        add("INFO", f"{n_free} free edges" + (f" at heights z = {list(zs)[:8]}" if n_free else ""))

    # ---- normals
    if dim == 3:
        step("testing which way the surface normals point (probe test; can take a minute)")
        try:
            verdicts, owners, finished, n_todo = _probe_normals(
                ents, surf_tris, coords, MAX_NORMALS_SECONDS, step)
        except Exception as e:
            verdicts = None
            add("WARN", f"Normals could not be tested ({type(e).__name__}: {e})")
        if verdicts is not None:
            total = len(verdicts)
            n_out = sum(1 for x in verdicts.values() if x == "outward")
            n_unc = sum(1 for x in verdicts.values() if x == "unclear")
            flips = sorted(s for (v, s), x in verdicts.items()
                           if x == "inward" and owners.get(s, 0) == 1)
            shared_inward = sorted(s for (v, s), x in verdicts.items()
                                   if x == "inward" and owners.get(s, 0) > 1)
            out["faces_to_flip"] = flips
            summary = (f"{total} surfaces tested: {n_out} outward, {len(flips)} inward, "
                       f"{n_unc} could not be judged (thin parts)")
            if not finished:
                add("WARN", f"Normals test stopped after {MAX_NORMALS_SECONDS} s with "
                            f"{total} of {n_todo} surfaces tested: {summary}")
            elif flips:
                add("WARN", f"{summary}. Surfaces pointing into their solid (reverse their "
                            f"triangles): {flips[:15]}")
            elif total and n_unc > 0.5 * total:
                add("WARN", f"{summary}. Most surfaces could not be judged, so the "
                            "normals are not confirmed")
            else:
                add("PASS", f"Normals point out of the solid: {summary}")
            n_shared = sum(1 for n in owners.values() if n > 1)
            if n_shared:
                add("INFO", f"{n_shared} faces are shared by two solids (internal faces); "
                            "remove them for a shell model of the outer skin"
                            + (f". Inward for one of the two solids: {shared_inward[:10]}"
                               if shared_inward else ""))
    else:
        n_bad = int(er["bad"].sum())
        if n_bad == 0:
            add("PASS", f"Triangle orientation is consistent ({int(er['shared'].sum())} "
                        "shared edges)")
        else:
            add("FAIL", f"{n_bad} inconsistent edges: some surfaces are ordered the "
                        "opposite way from their neighbours")
        free_z = np.unique(np.round(coords[er["uniq"][er["free"]] // len(coords), 2], 2)) \
            if n_free else []
        if n_free == 0 or (len(free_z) and np.all(np.abs(free_z) < 1e-3)):
            vol = signed_volume(coords, all_tris)
            add("PASS" if vol > 0 else "FAIL",
                f"Enclosed volume from the normals is {vol:.1f} m3 "
                f"({'outward' if vol > 0 else 'INWARD'})")
        else:
            add("INFO", "Outward/inward cannot be judged globally: the model is open "
                        "somewhere other than z = 0")

    # ---- rotor direction
    hub = _mean_centre(dim, rep["groups"]["Hub"]["parts"])
    nac = _mean_centre(dim, rep["groups"]["Nacelle"]["parts"])
    if hub is None:
        add("WARN", "No Hub group, so the rotor direction cannot be determined")
    else:
        ref = nac if nac is not None else (0.0, 0.0, 0.0)
        dx, dy = hub[0] - ref[0], hub[1] - ref[1]
        if math.hypot(dx, dy) < 1e-3 * H:
            add("WARN", "The hub is directly above the nacelle/tower axis, so the rotor "
                        "direction cannot be determined")
        else:
            theta = heading_from_plus_y(dx, dy)
            if abs(theta) <= 10:
                add("PASS", f"Rotor faces +Y (within {abs(theta):.1f} degrees), as the project expects")
            else:
                add("WARN", f"Rotor faces {theta:.0f} degrees counter-clockwise from +Y "
                            f"(seen from above). Rotate the model by {-theta:.0f} degrees "
                            "about Z so it matches the project convention")
    return out


def main():
    ap = argparse.ArgumentParser(description="Check a user's STEP file")
    ap.add_argument("path")
    ap.add_argument("--up", default="Z", choices=["X", "Y", "Z", "x", "y", "z"])
    ap.add_argument("--tower-height", type=float, default=None)
    ap.add_argument("--min-frac", type=float, default=0.02)
    ap.add_argument("--size", type=float, default=0.0)
    ap.add_argument("--rotor-r", type=float, default=DEFAULTS["rotor_r_min"])
    ap.add_argument("--nacelle-z", type=float, default=DEFAULTS["nacelle_z_min"])
    ap.add_argument("--blade-len", type=float, default=DEFAULTS["blade_len_min"])
    a = ap.parse_args()

    print(f"check_upload: {a.path}", flush=True)
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    try:
        out = run_checks(a.path, up_axis=a.up, tower_height=a.tower_height,
                         min_frac=a.min_frac, size=a.size,
                         thresholds={"rotor_r_min": a.rotor_r, "nacelle_z_min": a.nacelle_z,
                                     "blade_len_min": a.blade_len}, echo=True)
    finally:
        gmsh.finalize()

    if out["faces_to_flip"]:
        print(f"\nfaces_to_flip ({len(out['faces_to_flip'])}): {out['faces_to_flip']}")
    n = {k: sum(1 for lv, _ in out["results"] if lv == k) for k in ("PASS", "WARN", "FAIL")}
    print(f"\n{n['PASS']} PASS, {n['WARN']} WARN, {n['FAIL']} FAIL")
    sys.exit(1 if n["FAIL"] else 0)


if __name__ == "__main__":
    main()