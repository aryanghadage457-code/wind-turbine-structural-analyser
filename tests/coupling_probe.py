"""coupling_probe.py - STANDALONE CalculiX test: does a connection across a gap TRANSMIT load?
(no repo imports; put it in tests/ and run:   python tests/coupling_probe.py --ccx "C:\\path\\to\\ccx.exe")
 
Model: two coaxial S6 shell tubes along Y (R = 1.5 m, t = 0.02 m, steel) separated by a 0.5 m GAP with NO
shared nodes. Tube A (y -8..0) is clamped at y = -8 (all 6 DOF). Tube B (y 0.5..8.5) carries a 1000 N
downward (-Z) force spread over its free end ring. Everything the load does has to cross the gap.
 
Variants (the connection across the gap):
  CONTROL     one continuous tube, no connection             -> reference tip deflection
  EQ3 / EQ6   node-to-node *EQUATION on the two facing rings (DOF 1-3 / DOF 1-6) -> sanity check of the test
  KIN_DEFAULT both END BANDS coupled to ONE reference node, *KINEMATIC, no DOF line
  KIN_16      same, *KINEMATIC with "1, 6"
  DIST_13     same, *DISTRIBUTING (element-face surfaces) with "1, 3"
  DIST_16     same, *DISTRIBUTING with "1, 6"
A variant PASSES when: CalculiX finishes, reaction Fz equals the applied 1000 N within 1%, and the tip
deflection is within a few tens of % of CONTROL (the bands are rigid, so some difference is normal).
FAIL / lost load = reaction near 0 or a huge deflection. Nothing here has been run by the author.
"""
import argparse, math, os, re, subprocess, sys
import numpy as np
 
R, T, E, NU = 1.5, 0.02, 210e9, 0.3
NT = 24                      # elements around the circumference
P_LOAD = 1000.0              # N, applied in -Z
GAP = (0.0, 0.5)             # tube A ends at y = 0.0, tube B starts at y = 0.5
BAND = 1.0                   # axial width of the coupled end bands (m)
 
 
def tube(y0, y1, nz, node0):
    """S6 tube along Y. Returns nodes (n,3), elements (m,6) with 0-based ids offset by node0."""
    pts = [[R * math.cos(2 * math.pi * i / NT), y0 + (y1 - y0) * j / nz, R * math.sin(2 * math.pi * i / NT)]
           for j in range(nz + 1) for i in range(NT)]
    idx = lambda i, j: j * NT + (i % NT)
    tri = []
    for j in range(nz):
        for i in range(NT):
            tri += [(idx(i, j), idx(i + 1, j), idx(i + 1, j + 1)), (idx(i, j), idx(i + 1, j + 1), idx(i, j + 1))]
    cache, els = {}, []
    for a, b, c in tri:
        mids = []
        for p, q in ((a, b), (b, c), (c, a)):
            k = (min(p, q), max(p, q))
            if k not in cache:
                m = (np.array(pts[p]) + np.array(pts[q])) / 2
                rr = math.hypot(m[0], m[2]); m[0] *= R / rr; m[2] *= R / rr   # keep mid-side nodes on the cylinder
                cache[k] = len(pts); pts.append(list(m))
            mids.append(cache[k])
        els.append([a, b, c] + mids)
    return np.array(pts), np.array(els) + node0
 
 
def build_variant(name):
    """Return (node array, [(elset, element array)], connection-lines function inputs)."""
    if name == "CONTROL":
        n, e = tube(-8.0, 8.5, 16, 0)
        return n, [("TUBEA", e)]
    na, ea = tube(-8.0, GAP[0], 8, 0)
    nb, eb = tube(GAP[1], 8.5, 8, len(na))
    return np.vstack([na, nb]), [("TUBEA", ea), ("TUBEB", eb)]
 
 
def write_job(path, name):
    nodes, sets = build_variant(name)
    N = len(nodes)
    L = ["*HEADING", f"coupling probe {name}", "*NODE"]
    L += [f"{i + 1}, {x:.10g}, {y:.10g}, {z:.10g}" for i, (x, y, z) in enumerate(nodes)]
    for es, el in sets:
        L.append(f"*ELEMENT, TYPE=S6, ELSET={es}")
        L += [f"{k + 1 + sum(len(s[1]) for s in sets[:sets.index((es, el))])}, " + ", ".join(str(int(n) + 1) for n in row)
              for k, row in enumerate(el)]
    L += ["*NSET, NSET=NALL, GENERATE", f"1, {N}"]
    ids = lambda mask: [str(int(i) + 1) for i in np.where(mask)[0]]
    chunk = lambda v, n=10: [", ".join(v[i:i + n]) for i in range(0, len(v), n)]
    L += ["*NSET, NSET=BASE"] + chunk(ids(nodes[:, 1] < -8.0 + 1e-6))
    top = ids(nodes[:, 1] > 8.5 - 1e-6)
    L += ["*NSET, NSET=LOADRING"] + chunk(top)
    L += ["*MATERIAL, NAME=STEEL", "*ELASTIC", f"{E:.10g}, {NU}"]
    for es, _ in sets:
        L += [f"*SHELL SECTION, ELSET={es}, MATERIAL=STEEL", f"{T}"]
    L += ["*BOUNDARY", "BASE, 1, 6"]
 
    if name != "CONTROL":
        ya = nodes[:, 1]
        ringA = np.where(np.abs(ya - GAP[0]) < 1e-6)[0]; ringB = np.where(np.abs(ya - GAP[1]) < 1e-6)[0]
        ang = lambda i: math.atan2(nodes[i, 2], nodes[i, 0])
        ringA = sorted(ringA, key=ang); ringB = sorted(ringB, key=ang)
        assert len(ringA) == len(ringB), "facing rings must have the same node count"
        if name in ("EQ3", "EQ6"):
            L.append("*EQUATION")
            for a, b in zip(ringA, ringB):
                for d in range(1, (3 if name == "EQ3" else 6) + 1):
                    L += ["2", f"{a + 1}, {d}, 1., {b + 1}, {d}, -1."]
        else:
            ea = sets[0][1]; eb = sets[1][1]
            cen = lambda e: nodes[e[:, :3]].mean(axis=1)
            pa = np.where(cen(ea)[:, 1] >= GAP[0] - BAND)[0]; pb = np.where(cen(eb)[:, 1] <= GAP[1] + BAND)[0]
            ref = N + 1
            L += ["*NODE", f"{ref}, 0.0, {(GAP[0] + GAP[1]) / 2}, 0.0"]
            if name.startswith("KIN"):
                for tag, e, sel in (("A", ea, pa), ("B", eb, pb)):
                    nn = np.unique(e[sel]); L += [f"*NSET, NSET=PATCH{tag}"] + chunk([str(int(i) + 1) for i in nn])
                    L += [f"*SURFACE, NAME=SURF{tag}, TYPE=NODE", f"PATCH{tag}"]
                dof = ["1, 6"] if name == "KIN_16" else []
                for tag in "AB":
                    L += [f"*COUPLING, REF NODE={ref}, SURFACE=SURF{tag}, CONSTRAINT NAME=COUP{tag}", "*KINEMATIC"] + dof
            else:   # DIST_13 / DIST_16: element-face surfaces (a node surface is not allowed for *DISTRIBUTING)
                offA = 0; offB = len(ea)
                for tag, sel, off in (("A", pa, offA), ("B", pb, offB)):
                    L += [f"*ELSET, ELSET=PEL{tag}"] + chunk([str(int(k) + 1 + off) for k in sel])
                    L += [f"*SURFACE, NAME=SURF{tag}, TYPE=ELEMENT", f"PEL{tag}, SPOS"]
                dof = "1, 6" if name == "DIST_16" else "1, 3"
                for tag in "AB":
                    L += [f"*COUPLING, REF NODE={ref}, SURFACE=SURF{tag}, CONSTRAINT NAME=COUP{tag}", "*DISTRIBUTING", dof]
    L += ["*STEP", "*STATIC", "*CLOAD"]
    L += [f"{n}, 3, {-P_LOAD / len(top):.10g}" for n in top]
    L += ["*NODE PRINT, NSET=BASE, TOTALS=YES", "RF", "*NODE PRINT, NSET=NALL", "U", "*END STEP"]
    with open(path, "w") as fh:
        fh.write("\n".join(L) + "\n")
    return nodes, top
 
 
FLT = r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[Ee][-+]?\d+)?"
 
 
def read_dat(path):
    U, tot, mode = {}, None, None
    for raw in open(path, errors="replace"):
        s = raw.strip().lower()
        if not s:
            continue
        if s.startswith("displacements"):
            mode = "U"; continue
        if s.startswith("forces"):
            mode = None; continue
        if s.startswith("total force"):
            mode = "T"; continue
        v = re.findall(FLT, raw)
        if mode == "U" and len(v) == 4:
            U[int(v[0])] = [float(x) for x in v[1:]]
        elif mode == "T" and len(v) == 3:
            tot = [float(x) for x in v]; mode = None
    return U, tot
 
 
def run(name, ccx, workdir):
    job = f"probe_{name}"; inp = os.path.join(workdir, job + ".inp")
    nodes, top = write_job(inp, name)
    if ccx is None:
        return dict(name=name, status="written only (--dry)", nodes=len(nodes))
    for ext in (".dat", ".frd", ".sta", ".cvg"):
        if os.path.exists(os.path.join(workdir, job + ext)):
            os.remove(os.path.join(workdir, job + ext))
    r = subprocess.run([ccx, job], cwd=workdir, capture_output=True, text=True, timeout=600)
    out = (r.stdout or "") + (r.stderr or "")
    open(os.path.join(workdir, job + ".log"), "w").write(out)
    dat = os.path.join(workdir, job + ".dat")
    err = [l.strip() for l in out.splitlines() if "*error" in l.lower() or "singular" in l.lower()]
    if r.returncode != 0 or not os.path.exists(dat) or os.path.getsize(dat) == 0:
        return dict(name=name, status="FAILED: " + (err[0][:90] if err else f"exit {r.returncode}, no .dat"))
    U, tot = read_dat(dat)
    uz = float(np.mean([U[int(i)][2] for i in top])) if U else float("nan")
    return dict(name=name, status="ran", Fz=None if tot is None else tot[2], uz=uz,
                warn=[l.strip()[:90] for l in out.splitlines() if "*warning" in l.lower()][:2])
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccx", default=os.environ.get("CCX_PATH"), help="full path to ccx / ccx.exe (or set CCX_PATH)")
    ap.add_argument("--dry", action="store_true", help="only write the .inp files")
    ap.add_argument("--out", default="out/probe")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ccx = None if a.dry else (a.ccx or "ccx")
    names = ["CONTROL", "EQ3", "EQ6", "KIN_DEFAULT", "KIN_16", "DIST_13", "DIST_16"]
    res = [run(n, ccx, a.out) for n in names]
    I = math.pi * R ** 3 * T; A = 2 * math.pi * R * T; G = E / (2 * (1 + NU)); L = 16.5
    hand = -P_LOAD * L ** 3 / (3 * E * I) - P_LOAD * L / (G * A / 2)
    print(f"\nhand tip deflection (bending + shear) = {hand:.4e} m   applied load = {-P_LOAD:.0f} N (-Z)")
    ctrl = next((r.get("uz") for r in res if r["name"] == "CONTROL" and r.get("uz") is not None), None)
    print(f"{'variant':12s} {'result':50s} {'base Fz (N)':>13s} {'tip uz (m)':>12s} {'vs CONTROL':>11s}")
    for r in res:
        if r["status"] != "ran":
            print(f"{r['name']:12s} {r['status']}"); continue
        fz = r["Fz"]; ok = fz is not None and abs(fz - P_LOAD) < 0.01 * P_LOAD
        ratio = "" if not ctrl else f"{r['uz'] / ctrl:11.2f}"
        print(f"{r['name']:12s} {'PASS (reaction = load)' if ok else 'FAIL: load not transmitted / reaction wrong':50s} "
              f"{fz if fz is not None else float('nan'):13.1f} {r['uz']:12.4e} {ratio:>11s}")
        for w in r["warn"]:
            print(f"{'':12s}   warning: {w}")
    print("\nSend me this table and, for any FAILED variant, the first lines of out/probe/probe_<NAME>.log")
 
 
if __name__ == "__main__":
    main()
 