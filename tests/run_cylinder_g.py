import subprocess, os
import numpy as np
import gmsh
from contracts import Settings
from solver.mesh import make_cylinder, build_mesh
from solver.ccx_writer import write_inp

D, L_, t = 2.0, 20.0, 0.02
s = Settings()
gmsh.initialize(); gmsh.model.add("cyl")
groups, base_curves, area = make_cylinder(D, L_)
mesh = build_mesh(
    groups,
    base_curves,
    area,
    h=0.5,
    order=2,
    orientation="cylinder_z"
)

gmsh.finalize()

os.makedirs("runs", exist_ok=True)
write_inp("runs/cylG.inp", mesh, {"Tower_1": t}, s, g=9.81)
r = subprocess.run(["ccx", "cylG"], cwd="runs", capture_output=True, text=True)
print(r.stdout[-1500:]); print(r.stderr[-500:])

W = s.rho * 9.81 * np.pi * D * L_ * t
print(f"Expected weight: {W:.1f} N")