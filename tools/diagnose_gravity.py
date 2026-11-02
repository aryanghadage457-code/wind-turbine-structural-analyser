"""diagnose_gravity.py - find WHERE a turbine gravity result goes wrong. Read-only, numpy only.
 
    python tools/diagnose_gravity.py runs/turbine_G.inp runs/turbine_G.dat
 
Answers, from the files CalculiX already produced (nothing is re-solved):
  1. Is each group's thickness / material what we intended?  (parsed from the .inp)
  2. Mass, centre of mass and head overturning moment per group.
  3. Does each part move like a RIGID BODY?  (least-squares rigid fit u = t + w x r)
     If the whole head rotates rigidly while the tower barely moves, the tower-nacelle
     joint is the weak link, not the parts themselves.
  4. Implied rotational stiffness of the joints, compared with the tower.
  5. Are the shell normals consistent across the whole mesh (edge-direction test)?
  6. Is a small-displacement (linear) analysis still believable?
"""
import re
import sys
from collections import defaultdict
 
import numpy as np
 
 
# ----------------------------------------------------------------------------- parsing
def parse_inp(path):
    nodes, elems, egroup, names = {}, [], [], []
    sect, mode, E, rho = {}, None, None, None
    pending = None
    for raw in open(path, errors="replace"):
        s = raw.strip()
        if not s or s.startswith("**"):
            continue
        if s.startswith("*"):
            mode = s.split(",")[0].upper()
            pending = None
            if mode == "*ELEMENT":
                names.append(re.search(r"ELSET=([^,\s]+)", s, re.I).group(1))
            elif mode == "*SHELL SECTION":
                pending = (re.search(r"ELSET=([^,\s]+)", s, re.I).group(1),
                           re.search(r"MATERIAL=([^,\s]+)", s, re.I).group(1))
            continue
        p = [x.strip() for x in s.split(",")]
        if mode == "*NODE":
            nodes[int(p[0])] = [float(x) for x in p[1:4]]
        elif mode == "*ELEMENT":
            elems.append([int(x) for x in p[1:7]]); egroup.append(len(names) - 1)
        elif mode == "*SHELL SECTION" and pending:
            sect[pending[0].upper()] = (float(p[0]), pending[1])
        elif mode == "*ELASTIC":
            E = (float(p[0]), float(p[1]))
        elif mode == "*DENSITY":
            rho = float(p[0])
    ids = sorted(nodes)
    idx = {n: i for i, n in enumerate(ids)}
    X = np.array([nodes[n] for n in ids])
    conn = np.array([[idx[n] for n in e] for e in elems])
    return dict(X=X, conn=conn, egroup=np.array(egroup), names=names, sect=sect, E=E, rho=rho)
 
 
def parse_dat_displacements(path, n_nodes):
    U, mode = np.full((n_nodes, 3), np.nan), None
    for raw in open(path, errors="replace"):
        s = raw.strip().lower()
        if s.startswith("displacements"):
            mode = "U"; continue
        if s.startswith(("forces", "stresses", "total")):
            mode = None; continue
        p = raw.split()
        if mode == "U" and len(p) >= 4:
            try:
                U[int(p[0]) - 1] = [float(v) for v in p[1:4]]
            except ValueError:
                mode = None
    if np.isnan(U).any():
        raise ValueError("displacements missing for some nodes")
    return U
 
 
# ----------------------------------------------------------------------------- geometry
def t6_areas(X, conn):
    P = X[conn]; area = np.zeros(len(conn))
    for l1, l2 in ((1 / 6, 1 / 6), (2 / 3, 1 / 6), (1 / 6, 2 / 3)):
        l3 = 1 - l1 - l2
        d1 = np.array([4 * l1 - 1, 0, -(4 * l3 - 1), 4 * l2, -4 * l2, 4 * (l3 - l1)])
        d2 = np.array([0, 4 * l2 - 1, -(4 * l3 - 1), 4 * l1, 4 * (l3 - l2), -4 * l1])
        area += np.linalg.norm(np.cross(np.einsum("n,enj->ej", d1, P), np.einsum("n,enj->ej", d2, P)), axis=1) / 6
    return area
 
 
def rigid_fit(X, U):
    """Least-squares u_i ~ t + w x (x_i - c). Returns (w (rad), t, residual_rms / rms|u|)."""
    c = X.mean(0); r = X - c
    A = np.zeros((3 * len(X), 6))
    for k in range(3):
        A[k::3, k] = 1.0
    A[0::3, 4], A[0::3, 5] = r[:, 2], -r[:, 1]       # u_x = tx + wy*z - wz*y
    A[1::3, 3], A[1::3, 5] = -r[:, 2], r[:, 0]       # u_y = ty - wx*z + wz*x
    A[2::3, 3], A[2::3, 4] = r[:, 1], -r[:, 0]       # u_z = tz + wx*y - wy*x
    sol, *_ = np.linalg.lstsq(A, U.reshape(-1), rcond=None)
    res = U.reshape(-1) - A @ sol
    return sol[3:], sol[:3], float(np.sqrt(np.mean(res ** 2)) / max(np.sqrt(np.mean(U ** 2)), 1e-300))
 
 
def orientation_conflicts(conn, egroup, names):
    """Edges shared by exactly 2 elements that are traversed in the SAME direction by both."""
    de = np.concatenate([conn[:, [0, 1]], conn[:, [1, 2]], conn[:, [2, 0]]])
    own = np.tile(np.arange(len(conn)), 3)
    key = np.sort(de, axis=1); n = conn.max() + 1
    code = key[:, 0].astype(np.int64) * n + key[:, 1]
    order = np.argsort(code, kind="stable"); code_s = code[order]
    starts = np.r_[0, np.flatnonzero(np.diff(code_s)) + 1]
    counts = np.diff(np.r_[starts, len(code_s)])
    pair, tot = defaultdict(int), 0
    for s0 in starts[counts == 2]:
        a, b = order[s0], order[s0 + 1]
        tot += 1
        if tuple(de[a]) == tuple(de[b]):
            ga, gb = sorted((names[egroup[own[a]]], names[egroup[own[b]]]))
            pair[(ga, gb)] += 1
    return tot, dict(pair)
 
 
# ----------------------------------------------------------------------------- report
def main(inp, dat, g=9.81):
    m = parse_inp(inp); X, conn, eg, names = m["X"], m["conn"], m["egroup"], m["names"]
    U = parse_dat_displacements(dat, len(X))
    print(f"nodes {len(X)}, elements {len(conn)}, groups {names}")
    print(f"material: E,nu = {m['E']}, rho = {m['rho']}\n")
 
    A = t6_areas(X, conn)
    print("1) SECTION / MASS TABLE")
    print(f"{'group':10s}{'elems':>7s}{'t [mm]':>8s}{'material':>10s}{'area m2':>10s}{'mass t':>9s}   centre of mass (x, y, z)")
    mass, cg = {}, {}
    for gi, nm in enumerate(names):
        sel = eg == gi
        t, mat = m["sect"].get(nm.upper(), (np.nan, "MISSING"))
        mass[nm] = m["rho"] * t * A[sel].sum()
        cen = X[conn[sel][:, :3]].mean(1); cg[nm] = np.average(cen, axis=0, weights=A[sel])
        print(f"{nm:10s}{sel.sum():7d}{t * 1e3:8.1f}{mat:>10s}{A[sel].sum():10.1f}{mass[nm] / 1e3:9.1f}   "
              f"({cg[nm][0]:7.2f},{cg[nm][1]:7.2f},{cg[nm][2]:7.2f})")
    tot = sum(mass.values()); print(f"{'TOTAL':10s}{'':25s}{'':10s}{tot / 1e3:9.1f}   weight {tot * g / 1e6:.3f} MN")
 
    tow = [n for n in names if n.startswith("Tower_")]; head = [n for n in names if not n.startswith("Tower_")]
    tt = np.unique(conn[np.isin(eg, [names.index(n) for n in tow])]); zt = X[tt, 2].max()
    top = tt[X[tt, 2] > zt - 0.3]; c0 = np.array([0.0, 0.0, zt])
    M = sum((np.cross(cg[n] - c0, [0, 0, -mass[n] * g]) for n in head), np.zeros(3))
    print(f"\n2) HEAD LOAD about the tower-top centre (0, 0, {zt:.1f}): "
          f"Mx = {M[0] / 1e6:.2f} MN*m, My = {M[1] / 1e6:.2f} MN*m, vertical = {sum(mass[n] for n in head) * g / 1e6:.3f} MN")
 
    print("\n3) RIGID-BODY FIT per part (w = rotation, rad; 'resid' = share of the motion that is NOT rigid)")
    fits = {}
    for nm in names:
        nodes = np.unique(conn[eg == names.index(nm)])
        w, t, r = rigid_fit(X[nodes], U[nodes]); fits[nm] = w
        print(f"{nm:10s} |u|max {np.linalg.norm(U[nodes], axis=1).max():8.4f} m   w = ({w[0]:8.4f},{w[1]:8.4f},{w[2]:8.4f})  "
              f"|w| = {np.linalg.norm(w):.4f} rad = {np.degrees(np.linalg.norm(w)):.2f} deg   resid {r:6.1%}")
    if head:
        hn = np.unique(conn[np.isin(eg, [names.index(n) for n in head])])
        wh, th, rh = rigid_fit(X[hn], U[hn]); wr, tr, rr = rigid_fit(X[top], U[top])
        print(f"{'HEAD (all)':10s} |u|max {np.linalg.norm(U[hn], axis=1).max():8.4f} m   w = ({wh[0]:8.4f},{wh[1]:8.4f},{wh[2]:8.4f})  "
              f"|w| = {np.linalg.norm(wh):.4f} rad = {np.degrees(np.linalg.norm(wh)):.2f} deg   resid {rh:6.1%}")
        print(f"{'tower top':10s} {'':17s} w = ({wr[0]:8.4f},{wr[1]:8.4f},{wr[2]:8.4f})  ({len(top)} nodes within 0.3 m of the top)")
        dj = wh - wr
        print(f"\n4) JOINT: head rotates {np.degrees(np.linalg.norm(dj)):.2f} deg relative to the tower-top ring")
        if np.linalg.norm(M) > 0 and np.linalg.norm(dj) > 1e-9:
            k = np.linalg.norm(M) / np.linalg.norm(dj)
            zs = X[tt, 2]; Rtop = np.hypot(X[top, 0], X[top, 1]).mean()
            EI = m["E"][0] * np.pi * Rtop ** 3 * m["sect"][tow[-1].upper()][0]
            print(f"   implied joint stiffness M/dtheta = {k:.3e} N*m/rad ; tower EI/L ~ {EI / zt:.3e} N*m/rad "
                  f"(joint is {k / (EI / zt):.1%} of the tower's own)")
        for a, b in (("Nacelle", "Hub"),) + tuple(("Hub", n) for n in head if n.startswith("Blade")):
            if a in fits and b in fits:
                print(f"   relative rotation {a}->{b}: {np.degrees(np.linalg.norm(fits[b] - fits[a])):.2f} deg")
 
    print("\n5) SHELL NORMAL CONSISTENCY (edges shared by 2 elements, same direction = conflict)")
    n2, conf = orientation_conflicts(conn, eg, names)
    print(f"   shared edges {n2}, conflicting {sum(conf.values())}")
    for (a, b), c in sorted(conf.items(), key=lambda kv: -kv[1])[:12]:
        print(f"   {a} - {b}: {c}")
 
    umax = np.linalg.norm(U, axis=1).max(); size = np.ptp(X[:, 2])
    wmax = max(np.linalg.norm(w) for w in fits.values())
    print(f"\n6) LINEARITY: max |u| = {umax:.3f} m = {umax / size:.1%} of the structure height; largest part rotation {np.degrees(wmax):.2f} deg")
    print("   rule of thumb: linear small-displacement theory is reliable for rotations below ~3 deg "
          "and displacements of 1-2 % of the size. Above that, the numbers are not physical.")
 
 
if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
 