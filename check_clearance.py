"""Exact minimum distances between parts (no mesh needed).
Usage: python check_clearance.py [config.json]
A blade should touch ONLY the hub. Any other pair that is very close (or 0) is suspect.
"""
import sys, itertools
import gmsh
from geometry.default_generator import load_params, build_default

path = sys.argv[1] if len(sys.argv) > 1 else "data/default_turbine.json"
gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 0)
build_default(load_params(path))          # builds and tags the model

parts = {}                                 # tag name -> list of surface ids
for dim, ptag in gmsh.model.getPhysicalGroups(2):
    parts[gmsh.model.getPhysicalName(dim, ptag)] = gmsh.model.getEntitiesForPhysicalGroup(dim, ptag)

def min_dist(a, b):
    best = None
    for s1 in parts[a]:
        for s2 in parts[b]:
            d = gmsh.model.occ.getDistance(2, int(s1), 2, int(s2))[0]
            best = d if best is None else min(best, d)
    return best

names = sorted(parts)
print("Parts:", ", ".join(names))
print(f"{'pair':22s} min distance (m)")
for a, b in itertools.combinations(names, 2):
    d = min_dist(a, b)
    note = ""
    if d < 1e-6:
        note = "touching (shared edge)"
    elif d < 0.3:
        note = "<-- close, check"
    print(f"{a + ' / ' + b:22s} {d:10.4f}  {note}")
gmsh.finalize()