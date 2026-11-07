
"""ccx_writer.py - write the CalculiX input file for the complete turbine (Member 2).
 
One file per load case:
    case "G": self-weight only        (gravity *DLOAD on every element)
    case "W": wind only               (nodal forces from a contracts.LoadSet, no gravity)
Fixed support, node sets and S6 shells come from the Mesh; thickness per group from `thickness`.
SI units. Node/element ids written to CalculiX = 0-based mesh index + 1.
"""
import os
import warnings
 
import numpy as np
 
from contracts import Mesh, Settings, LoadSet, check_group_props
from solver import bcs
from solver import links
from solver import rigid_head

 
G_ACC = 9.81
DEFAULT_BLADE_EI_FILE = "data/nrel5mw_blade_ei.csv"   # NREL 5-MW BlFract, FlpStff, EdgStff (N*m^2)
 
 
def _id_lines(ids, per_line=10):
    ids = [str(int(i)) for i in ids]
    return [", ".join(ids[i:i + per_line]) for i in range(0, len(ids), per_line)]
 
 
def write_inp(
    path, mesh: Mesh, thickness, settings: Settings,
    case="G", loads: LoadSet = None,
    write_frd=False,
    blade_ei_file=DEFAULT_BLADE_EI_FILE,
    blade_match="flap",
    blade_regions=12,
    stiff_groups=None,
    ref_point=None,
    ref_group="Nacelle",
    ref_mode="distribute",
    ref_nodes=None,
    rigid_links=None,
    extra_forces=None,
    rigid_head_groups=None
):
    """Write <path> (a .inp file). Returns the path.
 
    ref_mode: "distribute" (default) shares each extra weight over its group's nodes as nodal forces whose
    resultant acts exactly at the component's centre-of-mass point (statically exact for force and moment);
    "cload" shares it equally; "coupling" uses *COUPLING/*DISTRIBUTING (see warning in the section below).
 
    Extra (machinery) mass, two ways - never both:
      * ref_nodes=None (default): ONE reference node, mass = settings.extra_mass_kg, coupled to
        ref_group at ref_point (old behaviour, unchanged).
      * ref_nodes=[{"name": "NAC", "group": "Nacelle", "mass_kg": ..., "point": (x, y, z)}, ...]:
        one independent reference node per entry (see default_ref_nodes()). settings.extra_mass_kg
        must then be 0, otherwise the mass would be counted twice.
    """
    settings.validate()
    check_group_props(thickness, mesh)
    if mesh.elems.shape[1] != 6:
        raise ValueError("ccx_writer expects S6 (6-node) triangles")
    if case not in ("G", "W"):
        raise ValueError("case must be 'G' or 'W'")
    if case == "W" and (loads is None or loads.case != "W"):
        raise ValueError("case 'W' needs a LoadSet with case == 'W'")

    # --- Additional machinery forces
    extra = None
    if extra_forces is not None:
        extra = np.asarray(extra_forces, dtype=float)
        if extra.shape != (mesh.n_nodes, 3):
            raise ValueError(
                f"extra_forces must have shape ({mesh.n_nodes}, 3), "
                f"but received {extra.shape}"
            )
        if not np.all(np.isfinite(extra)):
            raise ValueError("extra_forces contains NaN or Inf.")
        if case != "G":
            raise ValueError(
                "Additional machinery forces are supported only for case G."
            )

    if "base" not in mesh.node_sets:
        bcs.assign_node_sets(mesh)
 
    names = [n.upper() for n in mesh.group_names]
    L = ["*HEADING", f"wind turbine, case {case}"]
 
    # --- nodes and elements
    L.append("*NODE")
    L += [f"{i + 1}, {x:.10g}, {y:.10g}, {z:.10g}" for i, (x, y, z) in enumerate(mesh.nodes)]
    for gi, name in enumerate(names):
        idx = np.where(mesh.elem_group == gi)[0]
        if len(idx) == 0:
            continue
        L.append(f"*ELEMENT, TYPE=S6, ELSET={name}")
        L += [f"{e + 1}, " + ", ".join(str(int(n) + 1) for n in mesh.elems[e]) for e in idx]
    present = [names[gi] for gi in np.unique(mesh.elem_group)]
    L.append("*ELSET, ELSET=EALL")
    L += _id_lines_names(present)
    L += ["*NSET, NSET=NALL, GENERATE", f"1, {mesh.n_nodes}"]
 
    # --- spanwise blade stiffness: None -> blades keep the single BLADE_EQ material (old behaviour)
    blade_plan = _plan_blade_regions(mesh, thickness, settings, blade_ei_file, blade_match, blade_regions)
    if blade_plan:
        L += _blade_region_elsets(blade_plan)
        _write_blade_report(path, blade_plan)
 
    # --- extra (machinery) mass: each weight m*g acts on its own reference node coupled to its shell group
    ref = _ref_setup(mesh, settings, case, loads, ref_point, ref_group, ref_mode, ref_nodes)
    if ref:
        L += _ref_definition(ref)
 
 
    # --- Materials
    # Tower, nacelle and hub retain the original steel properties.
    L += [
        "*MATERIAL, NAME=STEEL",
        "*ELASTIC",
        f"{settings.E:.10g}, {settings.nu:.10g}",
        "*DENSITY",
        f"{settings.rho:.10g}",
    ]
 
    # Blade equivalent material:
    # Same E and Poisson's ratio for this controlled test,
    # but reduced density to match the NREL blade mass.
    blade_rho = 2050.0
 
    L += [
        "*MATERIAL, NAME=BLADE_EQ",
        "*ELASTIC",
        f"{settings.E:.10g}, {settings.nu:.10g}",
        "*DENSITY",
        f"{blade_rho:.10g}",
    ]
 
    if blade_plan:
        L += _blade_region_materials(blade_plan, settings, blade_rho)
 
    # Optional stiffness sweep for load-transfer groups, e.g. stiff_groups={"Nacelle": 100, "Hub": 100}.
    # Young's modulus is multiplied by k; density and thickness (weight) are unchanged.
    stiff_groups = stiff_groups or {}
    for gname, k in stiff_groups.items():
        if gname not in mesh.group_names or gname.upper().startswith("BLADE_"):
            raise ValueError(f"stiff_groups: '{gname}' is not a non-blade group of this mesh")
        if not k > 0:
            raise ValueError(f"stiff_groups: factor for '{gname}' must be positive")
        L += [f"*MATERIAL, NAME={gname.upper()}_STIFF", "*ELASTIC",
              f"{settings.E * k:.10g}, {settings.nu:.10g}", "*DENSITY", f"{settings.rho:.10g}"]
 
    # --- Shell sections
    for name, gname in zip(names, mesh.group_names):
        if name not in present:
            continue
 
        if blade_plan and name in blade_plan["groups"]:
            continue                      # blade gets one shell section per spanwise region (below)
 
        material = "BLADE_EQ" if name.startswith("BLADE_") else "STEEL"
        if gname in stiff_groups:
            material = f"{name}_STIFF"
 
        L += [
            f"*SHELL SECTION, ELSET={name}, MATERIAL={material}",
            f"{thickness[gname]:.10g}",
        ]
 
    if blade_plan:
        L += _blade_region_sections(blade_plan, thickness)
 
    # --- fixed support: all 6 DOF on the base ring (text comes from bcs.py)
    L += bcs.boundary_lines(mesh, "base")
    # --- rigid links between component patches
    if rigid_head_groups:
        if ref_mode == "coupling":
            raise ValueError(
                "Rigid-head node IDs may conflict with reference nodes "
                "when ref_mode='coupling'. Use ref_mode='distribute'."
            )

        head_lines, head_info = rigid_head.rigid_head_lines(
            mesh,
            groups=rigid_head_groups,
            first_id=mesh.n_nodes + 1,
            ref_point=ref_point,
        )

        L += head_lines

        print(
            f"Rigid head created: {head_info['groups']}, "
            f"{head_info['n_nodes']} nodes, "
            f"{head_info['n_equations']} equations"
        )    
 
    # --- load step
    L += ["*STEP", "*STATIC"]

    if case == "G":
        # Gravity acts on every shell element.
        L += ["*DLOAD", f"EALL, GRAV, {G_ACC}, 0., 0., -1."]

        has_extra = extra is not None and np.any(extra)

        if ref or has_extra:
            L.append("*CLOAD")

            # Existing reference-node loads.
            if ref:
                L += _ref_cload_lines(ref)

            # Additional machinery forces, distributed over the selected nodes.
            if has_extra:
                for n in np.where(np.abs(extra).sum(axis=1) > 0)[0]:
                    for d in range(3):
                        if extra[n, d] != 0.0:
                            L.append(f"{n + 1}, {d + 1}, {extra[n, d]:.10g}")

    else:
        # Existing wind loading, unchanged.
        L.append("*CLOAD")
        f = loads.nodal_forces
        for n in np.where(np.abs(f).sum(axis=1) > 0)[0]:
            for d in range(3):
                if f[n, d] != 0.0:
                    L.append(f"{n + 1}, {d + 1}, {f[n, d]:.10g}")
        if ref:
            L += _ref_cload_lines(ref)
 
    # --- output requests (read by ccx_reader.py)
    L += ["*NODE PRINT, NSET=BASE, TOTALS=YES", "RF",
          "*NODE PRINT, NSET=NALL", "U",
          "*EL PRINT, ELSET=EALL", "S"]
    if write_frd:
        L += ["*NODE FILE", "U", "*EL FILE", "S"]
    L.append("*END STEP")
 
    with open(path, "w") as fh:
        fh.write("\n".join(L) + "\n")
    return path
 
 
def _id_lines_names(names, per_line=8):
    return [", ".join(names[i:i + per_line]) for i in range(0, len(names), per_line)]
 
 
# ============================================================================
# Spanwise blade stiffness (added)
#
# Idea: the shell thickness and the blade density (2050 kg/m3) are NOT touched. Only Young's
# modulus changes from region to region so that the model's bending stiffness follows NREL:
#       E_eq(region) = EI_target(region) / I_model(region)
# EI_target : NREL 5-MW FlpStff (or EdgStff), N*m^2, averaged over the region as 1/mean(1/EI)
#             (keeps the region's flexibility), log-interpolated on BlFract.
# I_model   : second moment of area of the MESHED thin wall per region, taken from the element
#             centroids and areas:   I = sum(t * A_e * p^2) / region_length   (p = distance from
#             the section centroid in the plane normal to the blade axis). Its two principal
#             values I_min (thin direction ~ flapwise) and I_max (chordwise ~ edgewise) are
#             invariant to twist, so no hard-coded coordinates or station table is needed.
# LIMITATION: one isotropic E per region can match only ONE direction. The default matches
# flapwise (the wind-load direction); the other direction is reported, not matched. The elliptical
# shell is more anisotropic (I_max/I_min) than the real blade, so edgewise EI is usually too
# high. Shear webs, spar caps and laminate stacking are not represented.
# ============================================================================
def load_blade_ei(path):
    """Read the NREL blade EI table -> (blfract, flp, edg), N*m^2.
    Accepts a 3-column text/CSV file (BlFract, FlpStff, EdgStff) or an ElastoDyn/FAST blade .dat
    whose table has >= 6 columns (BlFract, pitch axis, twist, mass, FlpStff, EdgStff, ...)."""
    rows = []
    with open(path) as fh:
        for line in fh:
            try:
                v = [float(t) for t in line.replace(",", " ").split()]
            except ValueError:
                continue
            if len(v) == 3:
                rows.append((v[0], v[1], v[2]))
            elif len(v) >= 6:
                rows.append((v[0], v[4], v[5]))
    if len(rows) < 3:
        raise ValueError(f"{path}: found fewer than 3 table rows (BlFract, FlpStff, EdgStff)")
    x, flp, edg = np.array(sorted(rows)).T
    if x[0] < 0 or x[-1] > 1.0001 or np.any(np.diff(x) <= 0):
        raise ValueError(f"{path}: BlFract must increase strictly within 0..1")
    if np.any(flp <= 0) or np.any(edg <= 0) or max(flp.max(), edg.max()) < 1e7:
        raise ValueError(f"{path}: stiffness must be positive and in N*m^2 (root value is of order 1e10)")
    return x, flp, edg
 
 
def _plan_blade_regions(mesh, thickness, settings, ei_file, match, n_reg):
    """Split every blade into n_reg spanwise regions and find E_eq for each. Returns None if the
    feature is off or cannot run (warning issued); otherwise a dict used by the writers below."""
    if not ei_file:
        return None
    if not os.path.isfile(ei_file):
        warnings.warn(f"blade EI table '{ei_file}' not found: blades keep uniform stiffness (BLADE_EQ)")
        return None
    if match not in ("flap", "edge"):
        raise ValueError("blade_match must be 'flap' or 'edge'")
    names = [n.upper() for n in mesh.group_names]
    blades = [gi for gi, n in enumerate(names) if n.startswith("BLADE_")]
    if not blades:
        return None
    if "HUB" not in names:
        warnings.warn("no Hub group: cannot find the blade axis, blades keep uniform stiffness")
        return None
    xb, flp, edg = load_blade_ei(ei_file)
    hub_c = mesh.nodes[np.unique(mesh.elems[mesh.elem_group == names.index("HUB")])].mean(axis=0)
    plan = {"groups": set(), "regions": [], "rows": []}
    d_xi = 1.0 / n_reg
 
    for gi in blades:
        name, gname = names[gi], mesh.group_names[gi]
        t = thickness[gname]
        eidx = np.where(mesh.elem_group == gi)[0]
        P = mesh.nodes[np.unique(mesh.elems[eidx])] - hub_c
        rad = np.linalg.norm(P, axis=1)
        axis = P[rad >= 0.98 * rad.max()].mean(axis=0)          # hub centre -> tip
        axis /= np.linalg.norm(axis)
        s_lo, s_hi = (P @ axis).min(), (P @ axis).max()          # root ... tip along the axis
        span = s_hi - s_lo
        cen = mesh.nodes[mesh.elems[eidx]].mean(axis=1) - hub_c
        xi = np.clip((cen @ axis - s_lo) / span, 0.0, 1.0)
        reg = np.minimum((xi * n_reg).astype(int), n_reg - 1)    # every element -> exactly one region
 
        tmp = np.array([1.0, 0, 0]) if abs(axis[0]) < 0.9 else np.array([0, 1.0, 0])
        u = np.cross(axis, tmp); u /= np.linalg.norm(u)
        v = np.cross(axis, u)
        c3 = mesh.nodes[mesh.elems[eidx][:, :3]]
        cr = np.cross(c3[:, 1] - c3[:, 0], c3[:, 2] - c3[:, 0])
        area = 0.5 * np.linalg.norm(cr, axis=1)
        wall = np.abs((cr / (2 * area)[:, None]) @ axis) < 0.9   # drops the flat tip cap
        pu, pv = cen @ u, cen @ v
        ax_e = (mesh.nodes[mesh.elems[eidx]] - hub_c) @ axis      # axial range of each element
        e_lo, e_hi = ax_e.min(axis=1), ax_e.max(axis=1)
 
        rows = []
        for r in range(n_reg):
            m = reg == r
            if not m.any():
                continue
            xs = np.linspace(r * d_xi, (r + 1) * d_xi, 21)
            tf = 1.0 / np.mean(1.0 / np.exp(np.interp(xs, xb, np.log(flp))))
            te = 1.0 / np.mean(1.0 / np.exp(np.interp(xs, xb, np.log(edg))))
            # share each element's area between the regions it overlaps (removes mesh-row rounding)
            r_lo, r_hi = s_lo + r * d_xi * span, s_lo + (r + 1) * d_xi * span
            ov = np.clip(np.minimum(e_hi, r_hi) - np.maximum(e_lo, r_lo), 0.0, None) / np.maximum(e_hi - e_lo, 1e-12)
            sel = wall & (ov > 0)
            i_min = i_max = E = np.nan
            if sel.sum() >= 6:
                w = t * area[sel] * ov[sel] / (d_xi * span)
                du = pu[sel] - np.sum(w * pu[sel]) / w.sum()
                dv = pv[sel] - np.sum(w * pv[sel]) / w.sum()
                C = np.array([[np.sum(w * du * du), np.sum(w * du * dv)],
                              [np.sum(w * du * dv), np.sum(w * dv * dv)]])
                i_min, i_max = np.linalg.eigvalsh(C)
                E = tf / i_min if match == "flap" else te / i_max
            rows.append(dict(blade=name, region=r + 1, set=f"{name}_R{r + 1:02d}", ids=eidx[m] + 1,
                             xi_lo=r * d_xi, xi_hi=(r + 1) * d_xi, flp_t=tf, edg_t=te,
                             i_min=i_min, i_max=i_max, E=E))
        if sum(len(q["ids"]) for q in rows) != len(eidx):
            raise ValueError(f"{name}: not every blade element was assigned to exactly one region")
        good = [q for q in rows if np.isfinite(q["E"])]
        if not good:
            raise ValueError(f"{name}: mesh too coarse to estimate blade section stiffness")
        for q in rows:                                           # thin regions borrow the nearest E
            if not np.isfinite(q["E"]):
                q["E"] = min(good, key=lambda g: abs(g["region"] - q["region"]))["E"]
                warnings.warn(f"{q['set']}: too few elements for I, E copied from the nearest region")
            if not (1e8 < q["E"] < 1e12):
                warnings.warn(f"{q['set']}: equivalent E = {q['E']:.3g} Pa is outside 1e8..1e12, check the EI table")
            q["flp_m"], q["edg_m"] = q["E"] * q["i_min"], q["E"] * q["i_max"]
        plan["groups"].add(name)
        plan["regions"] += rows
    plan["rows"] = plan["regions"]
    return plan
 
 
def _blade_region_elsets(plan):
    L = []
    for q in plan["regions"]:
        L.append(f"*ELSET, ELSET={q['set']}")
        L += _id_lines(q["ids"])
    return L
 
 
def _blade_region_materials(plan, settings, blade_rho):
    L = []
    for q in plan["regions"]:
        L += [f"*MATERIAL, NAME={q['set']}", "*ELASTIC", f"{q['E']:.10g}, {settings.nu:.10g}",
              "*DENSITY", f"{blade_rho:.10g}"]
    return L
 
 
def _blade_region_sections(plan, thickness):
    L = []
    for q in plan["regions"]:
        gname = next(g for g in thickness if g.upper() == q["blade"])
        L += [f"*SHELL SECTION, ELSET={q['set']}, MATERIAL={q['set']}", f"{thickness[gname]:.10g}"]
    return L
 
 
def _write_blade_report(path, plan):
    """<job>_blade_ei.csv: target vs model EI per region, for the validation table."""
    out = os.path.splitext(path)[0] + "_blade_ei.csv"
    with open(out, "w") as fh:
        fh.write("blade,region,xi_lo,xi_hi,n_elems,E_eq_Pa,I_min_m4,I_max_m4,"
                 "FlpStff_target,FlpStff_model,EdgStff_target,EdgStff_model,flp_ratio,edg_ratio\n")
        for q in plan["regions"]:
            fh.write(f"{q['blade']},{q['region']},{q['xi_lo']:.4f},{q['xi_hi']:.4f},{len(q['ids'])},"
                     f"{q['E']:.6g},{q['i_min']:.6g},{q['i_max']:.6g},{q['flp_t']:.6g},{q['flp_m']:.6g},"
                     f"{q['edg_t']:.6g},{q['edg_m']:.6g},{q['flp_m'] / q['flp_t']:.4f},"
                     f"{q['edg_m'] / q['edg_t']:.4f}\n")
    return out
 
 
# ============================================================================
# Reference nodes for the extra (machinery) masses (added; now one node PER COMPONENT)
#   case G : each node carries F = (0, 0, -mass_kg * g). Shell self-weight stays in the *DLOAD
#            (gravity on EALL); reference nodes belong to no element, so nothing is counted twice.
#   case W : the extra masses carry no load (wind only), so no reference node is written, unless the
#            old single-node path is used with loads.ref_node_force != 0.
#   ref_mode "distribute" (default): no extra node. The weight is applied as nodal forces on all nodes of the
#            group, with weights chosen (minimum change from an equal share) so that their resultant acts at
#            the component's point: sum(w) = 1 and sum(w_i * x_i) = point. Same force AND same moment
#            as a point weight at the centre of mass.
#   ref_mode "coupling": WARNING - tested with CalculiX 2.21: a *CLOAD on the reference node of a
#            *COUPLING (DISTRIBUTING or KINEMATIC) did NOT reach the supports (base reaction = 0 in
#            tests/coupling_probe.py), so the extra weight was silently lost. Check Fz of the base
#            reaction against the expected weight before using this mode. Node (id = n_nodes + k) at its point (default: centroid of the group's
#            nodes) tied to ALL nodes of its group with *COUPLING + *DISTRIBUTING (translations).
#            Nodes shared with a neighbouring component (joint rings) are part of the ring too.
#   ref_mode "cload"   : fallback, no extra node: the same force is shared equally over the group's
#            nodes. Statically equivalent; use it if CalculiX rejects the coupling.
# Reference nodes are numbered above n_nodes, so they are not in NALL and ccx_reader.py never sees them.
# ============================================================================
# CalculiX 2.21 rejects *DISTRIBUTING on a NODE surface ("a nodal surface is not allowed"), so the coupling
# surface is the element-face surface of the group's own shell set. SPOS = face on the positive-normal side.
SHELL_FACE = "SPOS"
NREL_EXTRA_MASS_KG = {"Nacelle": 190_622.0, "Hub": 53_263.0}
# = NREL target (nacelle 240,000 kg, hub 56,780 kg) minus the shell mass of THIS model (project values).
# NREL targets and the centre-of-mass positions below are NOT independently verified here: check them
# in the gross-properties table of NREL/TP-500-38060 (and its ElastoDyn input data).
NACELLE_CM_REL_TOWER_TOP = (0.0, -1.9, 1.75)   # (x, y, dz): 1.9 m DOWNWIND of the tower axis (rotor faces +Y,
                                               # so downwind = -Y) and 1.75 m above the yaw bearing (tower top)
 
 
def default_ref_nodes(params, nacelle_mass_kg=NREL_EXTRA_MASS_KG["Nacelle"], hub_mass_kg=NREL_EXTRA_MASS_KG["Hub"],
                      nacelle_cm=NACELLE_CM_REL_TOWER_TOP, hub_cm=None):
    """Two reference-node specs from the turbine parameters (data/default_turbine.json as a dict).
    Positions are configurable: nacelle_cm = (x, y, dz above the tower top); hub_cm = absolute (x, y, z),
    default = hub sphere centre (0, overhang, z_top + nacelle height / 2)."""
    z_top = params["tower"]["sections"][-1]["z1"]
    hub_c = (0.0, float(params["hub"]["overhang"]), z_top + float(params["nacelle"]["height"]) / 2.0)
    return [dict(name="NAC", group="Nacelle", mass_kg=float(nacelle_mass_kg),
                 point=(nacelle_cm[0], nacelle_cm[1], z_top + nacelle_cm[2])),
            dict(name="HUB", group="Hub", mass_kg=float(hub_mass_kg),
                 point=tuple(hub_cm) if hub_cm is not None else hub_c)]
 
 
def _ref_names(tag):
    if tag is None:                                   # old single-node names (unchanged)
        return dict(node="REFNODE", ring="REFRING", surf="REFSURF", coup="REFCOUPLING")
    return dict(node=f"REF_{tag}_NODE", ring=f"REF_{tag}_RING", surf=f"REF_{tag}_SURF", coup=f"REF_{tag}_COUP")
 
 
def _ref_setup(mesh, settings, case, loads, ref_point, ref_group, ref_mode, ref_nodes=None):
    """Return a list of reference-node dicts (empty list = none needed)."""
    if ref_mode not in ("coupling", "cload", "distribute"):
        raise ValueError("ref_mode must be 'distribute', 'cload' or 'coupling'")
    specs = []                                        # (tag, group, force vector, point or None)
    if ref_nodes:
        if case == "G" and settings.extra_mass_kg > 0:
            raise ValueError("extra mass given twice: settings.extra_mass_kg > 0 AND ref_nodes. Use only one of them.")
        if case == "W":
            if loads is not None and np.any(np.asarray(loads.ref_node_force)):
                raise ValueError("loads.ref_node_force != 0 cannot be combined with ref_nodes")
            return []                                 # wind case: the extra masses carry no load
        seen = set()
        for r in ref_nodes:
            tag = str(r["name"]).upper()
            if not tag.replace("_", "").isalnum() or tag in seen:
                raise ValueError(f"ref_nodes: name '{r['name']}' must be unique letters/digits/underscore")
            seen.add(tag)
            if r["mass_kg"] < 0:
                raise ValueError(f"ref_nodes: mass of '{tag}' cannot be negative")
            if r["mass_kg"] > 0:
                specs.append((tag, r["group"], np.array([0.0, 0.0, -r["mass_kg"] * G_ACC]), r.get("point")))
    else:                                             # old single-node path
        if case == "G":
            f = np.array([0.0, 0.0, -settings.extra_mass_kg * G_ACC])
        else:
            f = np.asarray(loads.ref_node_force, dtype=float)
            if np.any(np.asarray(loads.ref_node_moment) != 0):
                raise NotImplementedError("ref_node_moment != 0 is not supported yet (only a force on the reference node)")
        if np.any(f):
            specs.append((None, ref_group, f, ref_point))
    refs = []
    for tag, group, f, point in specs:
        if group not in mesh.group_names:
            raise ValueError(f"ref group '{group}' is not a group of this mesh")
        nodes = np.unique(mesh.elems[mesh.elem_group == mesh.group_names.index(group)])
        pt = mesh.nodes[nodes].mean(axis=0) if point is None else np.asarray(point, dtype=float)
        lo, hi = mesh.nodes[nodes].min(axis=0), mesh.nodes[nodes].max(axis=0)
        if np.any(pt < lo - 0.5) or np.any(pt > hi + 0.5):
            warnings.warn(f"reference point {np.round(pt, 3)} lies outside the bounding box of group '{group}'")
        w = None
        if ref_mode == "distribute":
            w = _centroid_weights(mesh.nodes[nodes], pt)
            if w.min() < -2.0 / len(nodes):
                warnings.warn(f"'{group}': some distribution weights are negative (min {w.min() * len(nodes):.2f} x equal share); "
                              "the point is far from the group's node centroid")
        refs.append(dict(tag=tag, group=group, force=f, nodes=nodes, point=pt, mode=ref_mode, weights=w,
                         id=mesh.n_nodes + 1 + len(refs), names=_ref_names(tag)))
    return refs
 
 
def _centroid_weights(X, p):
    """Weights w (sum 1, sum w_i x_i = p) closest to an equal share: w = 1/N + A^T (A A^T)^-1 [0, p - centroid]."""
    N = len(X)
    A = np.vstack([np.ones(N), X.T])
    lam = np.linalg.solve(A @ A.T, np.concatenate([[0.0], np.asarray(p, float) - X.mean(axis=0)]))
    return 1.0 / N + A.T @ lam
 
 
def _ref_definition(refs):
    L = []
    for r in refs:
        if r["mode"] != "coupling":
            continue
        n, (x, y, z) = r["names"], r["point"]
        L += (["*NODE", f"{r['id']}, {x:.10g}, {y:.10g}, {z:.10g}",
               f"*NSET, NSET={n['node']}", str(r["id"]), f"*NSET, NSET={n['ring']}"]
              + _id_lines(r["nodes"] + 1)
              + [f"*SURFACE, NAME={n['surf']}, TYPE=ELEMENT", f"{r['group'].upper()}, {SHELL_FACE}",
                 f"*COUPLING, REF NODE={r['id']}, SURFACE={n['surf']}, CONSTRAINT NAME={n['coup']}",
                 "*DISTRIBUTING", "1, 3"])
    return L
 
 
def _ref_cload_lines(refs):
    L = []
    for r in refs:
        if r["mode"] == "coupling":
            L += [f"{r['id']}, {d + 1}, {r['force'][d]:.10g}" for d in range(3) if r["force"][d] != 0.0]
        else:
            w = r["weights"] if r["mode"] == "distribute" else np.full(len(r["nodes"]), 1.0 / len(r["nodes"]))
            for n, wi in zip(r["nodes"], w):
                L += [f"{n + 1}, {d + 1}, {wi * r['force'][d]:.10g}" for d in range(3) if r["force"][d] != 0.0]
    return L
