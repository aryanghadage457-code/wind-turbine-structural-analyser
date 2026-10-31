"""Verify the tower-nacelle junction (Option B: open tower top).
Run from the project folder:  python verify_junction.py [params.json]
Run it AFTER editing data/default_turbine.json and geometry/default_generator.py.
Geometry only: no meshing, so it takes about a second.
"""
import sys, math
import gmsh
from geometry.default_generator import load_params, build_default

path = sys.argv[1] if len(sys.argv) > 1 else "data/default_turbine.json"
params = load_params(path)
sections = params["tower"]["sections"]
nac = params["nacelle"]
z_top = sections[-1]["z1"]
r_top = sections[-1]["d1"] / 2
disc_area = math.pi * r_top ** 2
floor_len = nac["y_front"] - nac["y_rear"]
expected_floor = nac["width"] * floor_len - disc_area

gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 0)
groups, thickness = build_default(params)
occ = gmsh.model.occ
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


# 1) nacelle width
nac_tags = groups.get("Nacelle", [])
xs = [gmsh.model.getBoundingBox(2, s) for s in nac_tags]
width_found = max(b[3] for b in xs) - min(b[0] for b in xs)
check("1. Nacelle width is 5.2 m",
      abs(nac["width"] - 5.2) < 1e-9 and abs(width_found - 5.2) < 1e-6,
      f"(JSON {nac['width']}, geometry {width_found:.4f})")

# 2) disc gone: no planar surface at z_top, centred on the axis, with area pi*r^2
discs = []
for _, s in gmsh.model.getEntities(2):
    if gmsh.model.getType(2, s) != "Plane":
        continue
    cx, cy, cz = occ.getCenterOfMass(2, s)
    if (abs(cz - z_top) < 1e-6 and math.hypot(cx, cy) < 1e-4
            and abs(occ.getMass(2, s) - disc_area) < 1e-3 * disc_area):
        discs.append(s)
check("2. Circular disc is no longer present", not discs,
      f"(found surfaces {discs})" if discs else f"(pi*r^2 = {disc_area:.4f} m2 not found)")

# 3) nacelle floor has a circular opening
floor = []
for s in nac_tags:
    xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(2, s)
    if abs(zmax - zmin) < 1e-6 and abs(zmin - z_top) < 1e-6:
        floor.append(s)
floor_ok = False
detail = f"(floor surfaces {floor})"
circle_curves = []
if len(floor) == 1:
    f = floor[0]
    area = occ.getMass(2, f)
    bnd = [c for _, c in gmsh.model.getBoundary([(2, f)], oriented=False)]
    circle_curves = [c for c in bnd if gmsh.model.getType(1, c) == "Circle"]
    floor_ok = abs(area - expected_floor) < 1e-3 and len(circle_curves) >= 1
    detail = (f"(area {area:.4f}, expected {expected_floor:.4f}; "
              f"{len(bnd)} boundary curves, {len(circle_curves)} circle)")
check("3. Nacelle floor is a rectangle with a circular opening", floor_ok, detail)

# 4) tower shell shares the circle with the floor
t4 = groups["Tower_%d" % len(sections)]
shared = []
if len(floor) == 1:
    t_curves = {c for s in t4 for _, c in gmsh.model.getBoundary([(2, s)], oriented=False)}
    f_curves = {c for _, c in gmsh.model.getBoundary([(2, floor[0])], oriented=False)}
    shared = [c for c in t_curves & f_curves if gmsh.model.getType(1, c) == "Circle"]
length_ok = bool(shared) and all(
    abs(occ.getMass(1, c) - 2 * math.pi * r_top) < 1e-4 for c in shared)
check("4. Tower_%d and nacelle floor share the circle" % len(sections), length_ok,
      f"(shared circle curves {shared})")

# 5) non-manifold curves (more than 2 faces on one curve)
nm = []
for _, c in gmsh.model.getEntities(1):
    up, _ = gmsh.model.getAdjacencies(1, c)
    if len(set(up)) > 2:
        nm.append((c, sorted(set(up))))
check("5. No non-manifold curves", not nm, f"(found {nm})" if nm else "")

# 6) groups and thickness
names = {f"Tower_{i+1}" for i in range(len(sections))} | {
    "Nacelle", "Hub", "Blade_1", "Blade_2", "Blade_3"}
exp_t = {f"Tower_{i+1}": s["t"] for i, s in enumerate(sections)}
exp_t.update({"Nacelle": nac["t"], "Hub": params["hub"]["t"]})
for k in (1, 2, 3):
    exp_t[f"Blade_{k}"] = params["blade"]["t"]
check("6a. All nine groups present", set(groups) == names, f"(diff {set(groups) ^ names})")
check("6b. Thickness values preserved", thickness == exp_t,
      "" if thickness == exp_t else f"(got {thickness})")

print()
print("Group summary:")
for n in sorted(groups):
    a = sum(occ.getMass(2, s) for s in groups[n])
    print(f"  {n:8s} surfaces={len(groups[n]):2d}  area={a:10.3f} m2  t={thickness[n]}")
print(f"\nExpected nacelle floor area: {nac['width']} x {floor_len} - {disc_area:.4f} = {expected_floor:.4f} m2")
print("\nALL CHECKS PASSED" if all(results) else "\nSOME CHECKS FAILED: paste this output back")
gmsh.finalize()