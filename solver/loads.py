"""loads.py - wind load on the PARKED turbine, case W (Member 2). SI units, contracts.LoadSet out.
 
Model (the one in the project plan / contracts):
  * wind blows toward d = (-sin b, -cos b, 0),  b = compass bearing the wind comes FROM (0 = N, 90 = E)
  * speed at height z: v(z) = v_ref * (z / z_hub)^alpha          (power-law shear, v_ref = hub-height speed)
  * dynamic pressure q = 0.5 * rho_air * Cd * v^2 ; Cd = Cd_blade for groups named Blade_*, else Cd_tower
  * only WINDWARD faces are loaded: projected area  dA_proj = max(0, -n.d) dA   (n = outward normal)
  * force on a face acts ALONG d (drag): dF = q * dA_proj * d
  * parked rotor: tower, nacelle, hub AND blades are loaded; no rotor thrust
All loads scale with v^2, so ONE solve at v_ref covers every speed (failure.py scales it).
 
Integration is done on the curved S6 surface (3-point rule) and the force is spread with the consistent S6
shape functions (corner nodes get 0, mid-side nodes 1/3 each for a uniform load), so the nodal forces carry
the same resultant AND moment as the distributed load. Element normals MUST point outward: call
orient_turbine(mesh) once, right after meshing, before ANY .inp is written (it reorders element nodes).
"""
import numpy as np
 
from contracts import Mesh, Settings, LoadSet
from solver.geom import FLIP_COLUMNS
 
GAUSS = ((1 / 6, 1 / 6), (2 / 3, 1 / 6), (1 / 6, 2 / 3))          # (l1, l2), weights 1/6 each
 
 
def wind_dir_vector(bearing_from_deg):
    """Unit vector the wind blows TOWARD. bearing 0 (from north) -> (0, -1, 0)."""
    b = np.radians(bearing_from_deg)
    return np.array([-np.sin(b), -np.cos(b), 0.0])
 
 
# ----------------------------------------------------------------------------- orientation
def fit_sphere(points):
    """Least-squares sphere through points: returns (centre (3,), radius)."""
    P = np.asarray(points, float)
    A = np.c_[2 * P, np.ones(len(P))]
    sol, *_ = np.linalg.lstsq(A, (P ** 2).sum(axis=1), rcond=None)
    c = sol[:3]
    return c, float(np.sqrt(max(sol[3] + c @ c, 0.0)))
 
 
def _reference_points(mesh, hub_center, refs):
    """Point 'inside' the body for every element: outward = away from it."""
    n_el = mesh.n_elems
    cen = mesh.nodes[mesh.elems[:, :3]].mean(axis=1)
    ref = np.zeros((n_el, 3))
    refs = refs or {}
    hub_nodes = np.unique(mesh.elems[mesh.elem_group == mesh.group_names.index("Hub")]) if "Hub" in mesh.group_names else None
    if hub_center is None and hub_nodes is not None:
        hub_center = fit_sphere(mesh.nodes[hub_nodes])[0]
    for gi, name in enumerate(mesh.group_names):
        sel = mesh.elem_group == gi
        if not sel.any():
            continue
        nodes = np.unique(mesh.elems[sel])
        if name in refs:
            ref[sel] = np.asarray(refs[name], float)
        elif name.startswith("Tower_"):                       # tower: its axis at the same height
            ref[sel] = np.c_[np.zeros(sel.sum()), np.zeros(sel.sum()), cen[sel, 2]]
        elif name == "Hub":                                   # hub: the sphere centre
            ref[sel] = hub_center
        elif name.startswith("Blade_"):                       # blade: its axis (hub centre -> tip)
            if hub_center is None:
                raise ValueError("Blade orientation needs a Hub group or hub_center=...")
            r = np.linalg.norm(mesh.nodes[nodes] - hub_center, axis=1)
            tip = mesh.nodes[nodes][r >= 0.98 * r.max()].mean(axis=0)
            a = (tip - hub_center) / np.linalg.norm(tip - hub_center)
            ref[sel] = hub_center + np.outer((cen[sel] - hub_center) @ a, a)
        else:                                                 # nacelle and others: centre of the bounding box
            lo, hi = mesh.nodes[nodes].min(axis=0), mesh.nodes[nodes].max(axis=0)
            ref[sel] = 0.5 * (lo + hi)
    return cen, ref
 
 
def _flipped(mesh, hub_center, refs):
    cen, ref = _reference_points(mesh, hub_center, refs)
    p = mesh.nodes[mesh.elems[:, :3]]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    return np.einsum("ij,ij->i", n, cen - ref) < 0
 
 
def orientation_report(mesh, hub_center=None, refs=None):
    """{group: (n_outward, n_inward)} without changing the mesh."""
    bad = _flipped(mesh, hub_center, refs)
    return {nm: (int((~bad[mesh.elem_group == gi]).sum()), int(bad[mesh.elem_group == gi].sum()))
            for gi, nm in enumerate(mesh.group_names)}
 
 
def orient_turbine(mesh, hub_center=None, refs=None):
    """Flip (in place) every element whose normal points inward. Returns {group: number flipped}.
 
    Reference point per part: tower -> its axis; hub -> fitted sphere centre; blade -> its axis; others
    (nacelle) -> bounding-box centre. Pass refs={"Nacelle": (x, y, z)} to override a part.
    CHANGES element node order: do it before writing the first .inp and keep that mesh for G and W.
    """
    bad = _flipped(mesh, hub_center, refs)
    k = mesh.elems.shape[1]
    if bad.any():
        mesh.elems[bad] = mesh.elems[bad][:, FLIP_COLUMNS[k]]
    return {nm: int(bad[mesh.elem_group == gi].sum()) for gi, nm in enumerate(mesh.group_names)}
 
 
# ----------------------------------------------------------------------------- wind load
def _t6_terms():
    """Shape values N (3,6) and tangent weights d1, d2 (3,6) at the 3 Gauss points."""
    N, D1, D2 = [], [], []
    for l1, l2 in GAUSS:
        l3 = 1 - l1 - l2
        N.append([l1 * (2 * l1 - 1), l2 * (2 * l2 - 1), l3 * (2 * l3 - 1), 4 * l1 * l2, 4 * l2 * l3, 4 * l3 * l1])
        D1.append([4 * l1 - 1, 0, -(4 * l3 - 1), 4 * l2, -4 * l2, 4 * (l3 - l1)])
        D2.append([0, 4 * l2 - 1, -(4 * l3 - 1), 4 * l1, 4 * (l3 - l2), -4 * l1])
    return np.array(N), np.array(D1), np.array(D2)
 
 
def cd_per_element(mesh, s: Settings):
    cd = np.array([s.Cd_blade if n.startswith("Blade") else s.Cd_tower for n in mesh.group_names])
    return cd[mesh.elem_group]
 
 
def wind_loadset(mesh: Mesh, s: Settings, bearing_deg=None, v_ref=None, info=False):
    """Case-W LoadSet for the wind at v_ref (default s.v_ref) from bearing (default s.wind_bearing_deg).
 
    info=True also returns {group: dict(area_proj, force, Cd)} for the report.
    """
    s.validate()
    bearing = s.wind_bearing_deg if bearing_deg is None else bearing_deg
    v_ref = s.v_ref if v_ref is None else v_ref
    d = wind_dir_vector(bearing)
    rho = s.air_density
    k = mesh.elems.shape[1]
    X = mesh.nodes[mesh.elems]                                     # (E, k, 3)
    cd = cd_per_element(mesh, s)
    F_nodes = np.zeros((mesh.n_nodes, 3))
    f_el = np.zeros((mesh.n_elems, 3))
    a_el = np.zeros(mesh.n_elems)
 
    if k == 6:
        N, D1, D2 = _t6_terms()
        for g in range(3):
            xg = np.einsum("n,enj->ej", N[g], X)                   # Gauss point position
            t1 = np.einsum("n,enj->ej", D1[g], X)
            t2 = np.einsum("n,enj->ej", D2[g], X)
            dAn = np.cross(t1, t2)                                 # outward normal * 2*dA (weight 1/6 gives area)
            proj = np.maximum(0.0, -(dAn @ d)) / 6.0               # windward projected area of this Gauss cell
            v = v_ref * (np.maximum(xg[:, 2], 1e-6) / s.z_hub) ** s.shear_alpha
            fg = (0.5 * rho * cd * v ** 2 * proj)[:, None] * d[None, :]       # (E, 3) force of this Gauss cell
            for i in range(6):
                np.add.at(F_nodes, mesh.elems[:, i], N[g, i] * fg)
            f_el += fg
            a_el += proj
    elif k == 3:                                                   # S3: one point, force shared by the 3 corners
        p0, p1, p2 = X[:, 0], X[:, 1], X[:, 2]
        dAn = np.cross(p1 - p0, p2 - p0)
        proj = np.maximum(0.0, -(dAn @ d)) / 2.0
        zc = X[:, :, 2].mean(axis=1)
        v = v_ref * (np.maximum(zc, 1e-6) / s.z_hub) ** s.shear_alpha
        f_el = (0.5 * rho * cd * v ** 2 * proj)[:, None] * d[None, :]
        a_el = proj
        for i in range(3):
            np.add.at(F_nodes, mesh.elems[:, i], f_el / 3.0)
    else:
        raise ValueError(f"wind_loadset supports S3/S6, got {k} nodes per element")
 
    z3 = np.zeros(3)
    ls = LoadSet(nodal_forces=F_nodes, ref_node_force=z3, ref_node_moment=z3,
                 total_force=F_nodes.sum(axis=0), base_moment=np.cross(mesh.nodes, F_nodes).sum(axis=0),
                 case="W", v_ref=float(v_ref))
    if not info:
        return ls
    rep = {}
    for gi, nm in enumerate(mesh.group_names):
        m = mesh.elem_group == gi
        rep[nm] = dict(area_proj=float(a_el[m].sum()), force=f_el[m].sum(axis=0), Cd=float(cd[m][0]) if m.any() else 0.0)
    return ls, rep
 
 
# ----------------------------------------------------------------------------- independent hand checks
def tower_hand_force(sections, s: Settings, bearing_deg=None, v_ref=None, n=4000):
    """Tower drag from the section table, no mesh: integral of 0.5 rho Cd D(z) v(z)^2 dz. Returns the force vector (N)."""
    d = wind_dir_vector(s.wind_bearing_deg if bearing_deg is None else bearing_deg)
    v_ref = s.v_ref if v_ref is None else v_ref
    tot = 0.0
    for sec in sections:
        z = np.linspace(sec["z0"], sec["z1"], n)
        D = sec["d0"] + (sec["d1"] - sec["d0"]) * (z - sec["z0"]) / (sec["z1"] - sec["z0"])
        slope = np.hypot(1.0, 0.5 * (sec["d1"] - sec["d0"]) / (sec["z1"] - sec["z0"]))   # slant: dA = D*dz*slope, projected = D*dz
        v = v_ref * (np.maximum(z, 1e-6) / s.z_hub) ** s.shear_alpha
        tot += np.trapezoid(0.5 * s.air_density * s.Cd_tower * D * v ** 2, z)
    return tot * d
 
 
def box_hand_force(width_x, length_y, height, z_centre, s: Settings, bearing_deg=None, v_ref=None):
    """Drag on a closed box (nacelle): frontal silhouette area = height * (width*|dy| + length*|dx|), speed at z_centre."""
    d = wind_dir_vector(s.wind_bearing_deg if bearing_deg is None else bearing_deg)
    v_ref = s.v_ref if v_ref is None else v_ref
    v = v_ref * (z_centre / s.z_hub) ** s.shear_alpha
    area = height * (width_x * abs(d[1]) + length_y * abs(d[0]))
    return 0.5 * s.air_density * s.Cd_tower * v ** 2 * area * d
 