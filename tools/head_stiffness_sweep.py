"""head_stiffness_sweep.py - DIAGNOSTIC: is the blade-tip displacement caused by a flexible nacelle/hub load path?
 
Reruns the gravity case with Young's modulus of the Nacelle and Hub groups multiplied by k
(density and thickness unchanged, so the WEIGHT is identical in every run) and prints how the head moves.
 
    from tools.head_stiffness_sweep import sweep
    sweep(mesh, thickness, settings, params, factors=(1, 10, 100, 1000))
 
Reading the table
  joint_deg   rotation of (Nacelle + Hub) relative to the tower-top ring, degrees
  tip_max_m   largest blade-tip displacement
  nac_max_m   largest nacelle displacement (a roof sagging under hung machinery mass shows up here)
  If joint_deg and tip_max_m fall roughly like 1/k and then flatten, the flexible nacelle/hub load path is
  the cause, and the plateau value is what the blades themselves contribute.
  If they do NOT fall, the weak link is somewhere else (tower-top ring, hub-blade root): look at the
  relative rotations in tools/diagnose_gravity.py.
Needs CalculiX, so run it on your machine. It changes nothing in the project files.
"""
import os
import sys
 
import numpy as np
 
try:
    from tools.diagnose_gravity import rigid_fit
except ImportError:                                     # run from inside tools/
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from diagnose_gravity import rigid_fit
 
 
def metrics(mesh, U):
    """Head-motion numbers from a displacement field U (N,3)."""
    names, X = mesh.group_names, mesh.nodes
 
    def nodes_of(pred):
        ids = [i for i, n in enumerate(names) if pred(n)]
        return np.unique(mesh.elems[np.isin(mesh.elem_group, ids)]) if ids else np.array([], dtype=int)
 
    tower = nodes_of(lambda n: n.startswith("Tower_"))
    ring = tower[X[tower, 2] > X[tower, 2].max() - 0.3]
    core = nodes_of(lambda n: n in ("Nacelle", "Hub"))
    hub = nodes_of(lambda n: n == "Hub")
    w_core, _, res = rigid_fit(X[core], U[core])
    w_ring, _, _ = rigid_fit(X[ring], U[ring])
    hub_c = X[hub].mean(axis=0)
    tips = []
    for i, n in enumerate(names):
        if n.startswith("Blade_"):
            nb = np.unique(mesh.elems[mesh.elem_group == i])
            tips.append(np.linalg.norm(U[nb[np.argmax(np.linalg.norm(X[nb] - hub_c, axis=1))]]))
    nac = nodes_of(lambda n: n == "Nacelle")
    return dict(joint_deg=float(np.degrees(np.linalg.norm(w_core - w_ring))),
                core_nonrigid=float(res),
                tip_max_m=float(max(tips)) if tips else float("nan"),
                nac_max_m=float(np.linalg.norm(U[nac], axis=1).max()) if len(nac) else float("nan"),
                tower_top_m=float(np.linalg.norm(U[ring], axis=1).mean()))
 
 
def sweep(mesh, thickness, settings, params, factors=(1, 10, 100, 1000), groups=("Nacelle", "Hub"),
          workdir="runs/sweep", ccx=None, write_inp=None, run_ccx=None, read_dat=None,
          default_ref_nodes=None, **write_kwargs):
    """Run case G once per factor. Returns the list of metric dicts. Extra keyword arguments go to write_inp."""
    if write_inp is None:
        from solver.ccx_writer import write_inp, default_ref_nodes
        from solver.ccx_runner import run_ccx
        from solver.ccx_reader import read_dat
    os.makedirs(workdir, exist_ok=True)
    rows = []
    for k in factors:
        inp = os.path.join(workdir, f"G_k{int(k)}.inp")
        kw = dict(write_kwargs)
        if default_ref_nodes is not None and "ref_nodes" not in kw:
            kw["ref_nodes"] = default_ref_nodes(params)
        write_inp(inp, mesh, thickness, settings, case="G",
                  stiff_groups=None if k == 1 else {g: float(k) for g in groups}, **kw)
        dat = run_ccx(inp, ccx=ccx)
        U = read_dat(dat, mesh.n_nodes, mesh.n_elems)["U"]
        rows.append(dict(k=k, **metrics(mesh, U)))
    print(f"\n{'k':>6s} {'joint_deg':>10s} {'tip_max_m':>10s} {'nac_max_m':>10s} {'tower_top_m':>12s} {'core_nonrigid':>14s}")
    for r in rows:
        print(f"{r['k']:6g} {r['joint_deg']:10.3f} {r['tip_max_m']:10.3f} {r['nac_max_m']:10.3f} "
              f"{r['tower_top_m']:12.4f} {r['core_nonrigid']:14.1%}")
    return rows
