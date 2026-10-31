"""Open a STEP file in gmsh, print facts, and save them to step_report.txt.
Usage:  python view_step.py <file.step> [-nogui]
"""
import sys, time, traceback
import gmsh

lines = []
def say(msg):
    print(msg, flush=True)
    lines.append(str(msg))

def save():
    with open("step_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

args = [a for a in sys.argv[1:] if not a.startswith("-")]
if not args:
    sys.exit("Give a STEP file path")
path = args[0]

gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 1)
say(f"Loading {path} ... (big files can take several minutes)")
try:
    t0 = time.time()
    gmsh.model.occ.importShapes(path)
    gmsh.model.occ.synchronize()
    say(f"Loaded in {time.time() - t0:.1f} s")
except BaseException:
    say("FAILED to load:")
    say(traceback.format_exc())
    save()
    gmsh.finalize()
    sys.exit(1)

say(f"Bodies (volumes): {len(gmsh.model.getEntities(3))}")
say(f"Surfaces: {len(gmsh.model.getEntities(2))}")
say(f"Curves: {len(gmsh.model.getEntities(1))}")
if gmsh.model.getEntities(2):
    x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(-1, -1)
    say(f"Size x {x1-x0:.2f}, y {y1-y0:.2f}, z {z1-z0:.2f}  (file units)")
save()
say("Report saved to step_report.txt")

if "-nogui" not in sys.argv:
    gmsh.option.setNumber("Geometry.Surfaces", 1)
    gmsh.fltk.run()
gmsh.finalize()