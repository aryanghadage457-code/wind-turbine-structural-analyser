"""Geometry check (Member 1): tower area vs hand formula, and surface normals.

Usage (from the main project folder):
    python check_geometry.py [config.json] [mesh_size_m]

Checks
  1. AREA     each Tower_i area = pi * mean diameter * slant length
  2. NORMALS  tower, nacelle and hub triangles face away from their own centre
  3. ORIENT   neighbouring triangles agree on direction across every shared edge
              (if one part is outward and the orientation is consistent over
              the one connected body, the blades are outward too)
  4. VOLUME   signed enclosed volume is positive (only when the model is open
              at z = 0 and nowhere else, because the z = 0 plane passes
              through the origin)
"""
import sys
import math
import collections

import numpy as np
import gmsh

from geometry.default_generator import load_params, build_default


# ---------------------------------------------------------------- pure maths
def triangle_arrays(coords, tris):
    A, B, C = coords[tris[:, 0]], coords[tris[:, 1]], coords[tris[:, 2]]
    normal = np.cross(B - A, C - A)          # length = 2 * area
    centre = (A + B + C) / 3.0
    return A, B, C, normal, centre


def edge_report(tris, n_nodes):
    """Classify every mesh edge. Returns a dict of numpy arrays."""
    a = tris.ravel()
    b = np.roll(tris, -1, axis=1).ravel()           # edges (t0,t1),(t1,t2),(t2,t0)
    tri_of_edge = np.repeat(np.arange(len(tris)), 3)
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    key = lo.astype(np.int64) * n_nodes + hi
    sign = np.where(a < b, 1, -1)
    uniq, inv, counts = np.unique(key, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    sums = np.bincount(inv, weights=sign)
    return {
        "key": key, "inv": inv, "tri_of_edge": tri_of_edge, "uniq": uniq,
        "counts": counts,
        "bad": (counts == 2) & (sums != 0),    # two triangles, same direction
        "shared": counts == 2,
        "free": counts == 1,
        "nonmanifold": counts > 2,
    }


def signed_volume(coords, tris):
    A, B, C, _, _ = triangle_arrays(coords, tris)
    return float(np.einsum("ij,ij->i", A, np.cross(B, C)).sum() / 6.0)


# ---------------------------------------------------------------------- main
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    path = args[0] if args else "data/default_turbine.json"
    size = float(args[1]) if len(args) > 1 else 3.0

    failures = []

    def report(ok, text):
        print(("PASS  " if ok else "FAIL  ") + text)
        if not ok:
            failures.append(text)

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    params = load_params(path)
    build_default(params)

    parts = {}                                   # name -> surface tags
    for dim, ptag in gmsh.model.getPhysicalGroups(2):
        name = gmsh.model.getPhysicalName(dim, ptag)
        parts[name] = [int(s) for s in
                       gmsh.model.getEntitiesForPhysicalGroup(dim, ptag)]
    print("Parts:", ", ".join(sorted(parts)))

    sections = params["tower"]["sections"]

    # ---- 1. area check (exact CAD areas, no mesh needed)
    print("\n--- 1. Area: tower sections vs pi x mean diameter x slant length")
    tower_volume = 0.0
    for i, s in enumerate(sections):
        name = f"Tower_{i + 1}"
        r0, r1 = s["d0"] / 2, s["d1"] / 2
        h = s["z1"] - s["z0"]
        tower_volume += math.pi * h / 3 * (r0 * r0 + r0 * r1 + r1 * r1)
        if name not in parts:
            report(False, f"{name}: not found in the model")
            continue
        slant = math.hypot(h, r0 - r1)
        expected = math.pi * (s["d0"] + s["d1"]) / 2 * slant
        actual = sum(gmsh.model.occ.getMass(2, t) for t in parts[name])
        err = abs(actual - expected) / expected * 100
        report(err < 0.1, f"{name}: model {actual:.3f} m2, hand {expected:.3f} m2, "
                          f"difference {err:.4f} %")

    # ---- mesh (needed for the normals checks)
    gmsh.option.setNumber("Mesh.MeshSizeMax", size)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)
    gmsh.option.setNumber("Mesh.MeshSizeMin", 0.15)
    gmsh.model.mesh.generate(2)

    ntags, ncoords, _ = gmsh.model.mesh.getNodes()
    coords = np.array(ncoords, dtype=float).reshape(-1, 3)
    lut = np.full(int(max(ntags)) + 1, -1, dtype=np.int64)
    lut[np.array(ntags, dtype=np.int64)] = np.arange(len(ntags))

    names = sorted(parts)
    tri_blocks, surf_blocks, grp_blocks = [], [], []
    for gi, name in enumerate(names):
        for s in parts[name]:
            etypes, _, enodes = gmsh.model.mesh.getElements(2, s)
            for et, nodes in zip(etypes, enodes):
                if et != 2:
                    print(f"note: surface {s} ({name}) has non-triangle "
                          f"elements, skipped")
                    continue
                t = lut[np.array(nodes, dtype=np.int64)].reshape(-1, 3)
                tri_blocks.append(t)
                surf_blocks.append(np.full(len(t), s))
                grp_blocks.append(np.full(len(t), gi))
    tris = np.vstack(tri_blocks)
    surf_of = np.concatenate(surf_blocks)
    grp_of = np.concatenate(grp_blocks)
    surf_name = {s: n for n, ss in parts.items() for s in ss}
    print(f"\nMesh: {len(tris)} triangles at max element size {size} m")

    A, B, C, normal, centre = triangle_arrays(coords, tris)

    # ---- 2. normals face away from each part's own centre
    print("\n--- 2. Normals: do the triangles face outward?")
    yaw = math.radians(float(params.get("yaw_deg", 0.0)))
    cs, sn = math.cos(yaw), math.sin(yaw)

    def rotate(p):
        return np.array([p[0] * cs - p[1] * sn, p[0] * sn + p[1] * cs, p[2]])

    z_top = sections[-1]["z1"]
    nac, hub = params.get("nacelle"), params.get("hub")
    for gi, name in enumerate(names):
        m = grp_of == gi
        if name.startswith("Tower_"):
            ref = centre[m] * np.array([1.0, 1.0, 0.0])
            what = "away from the tower axis"
        elif name == "Nacelle" and nac:
            c = rotate(np.array([0.0, (nac["y_rear"] + nac["y_front"]) / 2,
                                 z_top + nac["height"] / 2]))
            ref = centre[m] - c
            what = "away from the nacelle centre"
        elif name == "Hub" and hub and nac:
            c = rotate(np.array([0.0, hub["overhang"],
                                 z_top + nac["height"] / 2]))
            ref = centre[m] - c
            what = "away from the hub centre"
        else:
            continue                              # blades: see check 3
        frac = float((np.einsum("ij,ij->i", normal[m], ref) > 0).mean())
        note = "  <-- normals point INWARD" if frac < 0.5 else ""
        report(frac > 0.999, f"{name}: {frac * 100:.1f} % of triangles face "
                             f"{what}{note}")

    # ---- 3. orientation consistent across shared edges
    print("\n--- 3. Orientation: neighbouring triangles agree across shared edges")
    er = edge_report(tris, len(coords))
    n_shared, n_bad = int(er["shared"].sum()), int(er["bad"].sum())
    report(n_bad == 0, f"{n_bad} inconsistent edges out of {n_shared} shared edges")
    if n_bad:
        by_key = collections.defaultdict(set)
        for o in np.where(er["bad"][er["inv"]])[0]:
            by_key[int(er["key"][o])].add(int(surf_of[er["tri_of_edge"][o]]))
        pairs = collections.Counter(tuple(sorted(v)) for v in by_key.values())
        print("      surfaces meeting at inconsistent edges (most edges first):")
        for pair, n in pairs.most_common(10):
            label = " / ".join(f"{surf_name[s]} (surface {s})" for s in pair)
            print(f"        {n:5d} edges: {label}")
    if er["nonmanifold"].any():
        print(f"note: {int(er['nonmanifold'].sum())} edges are shared by more "
              f"than 2 triangles")

    # ---- 4. signed volume
    print("\n--- 4. Volume: enclosed volume from the normals")
    free_nodes = er["uniq"][er["free"]] // len(coords)
    free_z = np.unique(np.round(coords[free_nodes, 2], 2)) if len(free_nodes) else []
    if len(free_z) and np.all(np.abs(free_z) < 1e-3):
        vol = signed_volume(coords, tris)
        report(vol > 0, f"enclosed volume {vol:.1f} m3 "
                        f"(tower interior alone is {tower_volume:.1f} m3)")
    else:
        print(f"skipped: free edges at z = {list(free_z)}; the volume formula "
              f"only works when the only opening is at z = 0")

    print("\n" + ("ALL PASS" if not failures
                  else f"{len(failures)} CHECK(S) FAILED"))
    gmsh.finalize()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()