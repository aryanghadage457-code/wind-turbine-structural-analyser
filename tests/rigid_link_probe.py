"""rigid_link_probe.py - two more connection variants for the gap test (run after coupling_probe.py).
 
Put it in tests/ next to coupling_probe.py and run:
    python tests/rigid_link_probe.py --ccx "C:\\path\\to\\ccx.exe"          (add --dry to only write the .inp files)
 
The model is the same as coupling_probe.py: two coaxial S6 tubes with a 0.5 m gap, tube A clamped, a 1000 N
load on the free end of tube B. Both end bands (1 m wide each side of the gap) are linked through ONE
reference node at the middle of the gap:
 
  RB_ONE : both bands in a single *RIGID BODY (REF NODE + ROT NODE)
  EQ_RB  : the same rigid-body kinematics written by hand as *EQUATION, u_i = u_ref + theta x (x_i - x_ref),
           with theta = the three DOF of a second "rotation node". No special keyword is needed.
 
PASS = CalculiX finishes, base reaction Fz = 1000 N within 1 %, and the tip deflection is below CONTROL
(rigid bands make it stiffer; EQ3 gave 0.92 of CONTROL). Nothing here has been run by the author: the
keyword syntax is from memory, so a *ERROR line in the log is a valid answer ("not supported as written").
"""
import argparse
import math
import os
import subprocess
 
import numpy as np
 
import coupling_probe as cp
 
 
def write_job2(path, name):
    nodes, sets = cp.build_variant(name)
    N = len(nodes)
    ids = lambda mask: [str(int(i) + 1) for i in np.where(mask)[0]]
    chunk = lambda v, n=10: [", ".join(v[i:i + n]) for i in range(0, len(v), n)]
    L = ["*HEADING", f"rigid link probe {name}", "*NODE"]
    L += [f"{i + 1}, {x:.10g}, {y:.10g}, {z:.10g}" for i, (x, y, z) in enumerate(nodes)]
    off = 0
    for es, el in sets:
        L.append(f"*ELEMENT, TYPE=S6, ELSET={es}")
        L += [f"{off + k + 1}, " + ", ".join(str(int(n) + 1) for n in row) for k, row in enumerate(el)]
        off += len(el)
    L += ["*NSET, NSET=NALL, GENERATE", f"1, {N}"]
    L += ["*NSET, NSET=BASE"] + chunk(ids(nodes[:, 1] < -8.0 + 1e-6))
    top = ids(nodes[:, 1] > 8.5 - 1e-6)
    L += ["*NSET, NSET=LOADRING"] + chunk(top)
    L += ["*MATERIAL, NAME=STEEL", "*ELASTIC", f"{cp.E:.10g}, {cp.NU}"]
    for es, _ in sets:
        L += [f"*SHELL SECTION, ELSET={es}, MATERIAL=STEEL", f"{cp.T}"]
    L += ["*BOUNDARY", "BASE, 1, 6"]
 
    ea, eb = sets[0][1], sets[1][1]
    cen = lambda e: nodes[e[:, :3]].mean(axis=1)
    pa = np.unique(ea[cen(ea)[:, 1] >= cp.GAP[0] - cp.BAND])
    pb = np.unique(eb[cen(eb)[:, 1] <= cp.GAP[1] + cp.BAND])
    patch = np.unique(np.concatenate([pa, pb]))
    ref, rot = N + 1, N + 2
    yref = 0.5 * (cp.GAP[0] + cp.GAP[1])
    L += ["*NODE", f"{ref}, 0.0, {yref}, 0.0", f"{rot}, 0.0, {yref}, 0.0"]
    if name == "RB_ONE":
        L += ["*NSET, NSET=PATCH"] + chunk([str(int(i) + 1) for i in patch])
        L += [f"*RIGID BODY, NSET=PATCH, REF NODE={ref}, ROT NODE={rot}"]
    elif name == "EQ_RB":
        L.append("*EQUATION")
        for i in patch:
            rx, ry, rz = nodes[i][0], nodes[i][1] - yref, nodes[i][2]
            n = int(i) + 1
            # u = u_ref + theta x r :  ux = urx + ty*rz - tz*ry ; uy = ury + tz*rx - tx*rz ; uz = urz + tx*ry - ty*rx
            L += ["4", f"{n}, 1, 1., {ref}, 1, -1., {rot}, 2, {-rz:.10g}, {rot}, 3, {ry:.10g}"]
            L += ["4", f"{n}, 2, 1., {ref}, 2, -1., {rot}, 3, {-rx:.10g}, {rot}, 1, {rz:.10g}"]
            L += ["4", f"{n}, 3, 1., {ref}, 3, -1., {rot}, 1, {-ry:.10g}, {rot}, 2, {rx:.10g}"]
    else:
        raise ValueError(name)
    L += ["*STEP", "*STATIC", "*CLOAD"]
    L += [f"{n}, 3, {-cp.P_LOAD / len(top):.10g}" for n in top]
    L += ["*NODE PRINT, NSET=BASE, TOTALS=YES", "RF", "*NODE PRINT, NSET=NALL", "U", "*END STEP"]
    with open(path, "w") as fh:
        fh.write("\n".join(L) + "\n")
    return nodes, top
 
 
def run(name, ccx, workdir):
    job = f"probe_{name}"
    inp = os.path.join(workdir, job + ".inp")
    nodes, top = write_job2(inp, name)
    if ccx is None:
        return dict(name=name, status="written only (--dry)")
    for ext in (".dat", ".frd", ".sta", ".cvg"):
        p = os.path.join(workdir, job + ext)
        if os.path.exists(p):
            os.remove(p)
    r = subprocess.run([ccx, job], cwd=workdir, capture_output=True, text=True, timeout=600)
    out = (r.stdout or "") + (r.stderr or "")
    open(os.path.join(workdir, job + ".log"), "w").write(out)
    dat = os.path.join(workdir, job + ".dat")
    err = [l.strip() for l in out.splitlines() if "*error" in l.lower() or "singular" in l.lower()]
    if r.returncode != 0 or not os.path.exists(dat) or os.path.getsize(dat) == 0:
        return dict(name=name, status="FAILED: " + (err[0][:100] if err else f"exit {r.returncode}, no .dat"))
    U, tot = cp.read_dat(dat)
    uz = float(np.mean([U[int(i)][2] for i in top])) if U else float("nan")
    return dict(name=name, status="ran", Fz=None if tot is None else tot[2], uz=uz)
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccx", default=os.environ.get("CCX_PATH"))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--out", default="out/probe2")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ccx = None if a.dry else (a.ccx or "ccx")
    res = [run(n, ccx, a.out) for n in ("RB_ONE", "EQ_RB")]
    print(f"\napplied load {-cp.P_LOAD:.0f} N (-Z). CONTROL tip from coupling_probe.py was about -3.57e-05 m; EQ3 gave 0.92 of it.")
    print(f"{'variant':8s} {'result':46s} {'base Fz (N)':>12s} {'tip uz (m)':>12s}")
    for r in res:
        if r["status"] != "ran":
            print(f"{r['name']:8s} {r['status']}"); continue
        ok = r["Fz"] is not None and abs(r["Fz"] - cp.P_LOAD) < 0.01 * cp.P_LOAD
        print(f"{r['name']:8s} {'PASS (reaction = load)' if ok else 'FAIL: load not transmitted':46s} "
              f"{r['Fz'] if r['Fz'] is not None else float('nan'):12.1f} {r['uz']:12.4e}")
    print("\nSend me this table and, for any FAILED variant, the first lines of out/probe2/probe_<NAME>.log")
 
 
if __name__ == "__main__":
    main()
 