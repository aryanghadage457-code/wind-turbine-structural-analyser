"""ccx_writer.py - write the CalculiX input file for the complete turbine (Member 2).
 
One file per load case:
    case "G": self-weight only        (gravity *DLOAD on every element)
    case "W": wind only               (nodal forces from a contracts.LoadSet, no gravity)
Fixed support, node sets and S6 shells come from the Mesh; thickness per group from `thickness`.
SI units. Node/element ids written to CalculiX = 0-based mesh index + 1.
"""
import numpy as np
 
from contracts import Mesh, Settings, LoadSet, check_group_props
from solver import bcs
 
G_ACC = 9.81
 
 
def _id_lines(ids, per_line=10):
    ids = [str(int(i)) for i in ids]
    return [", ".join(ids[i:i + per_line]) for i in range(0, len(ids), per_line)]
 
 
def write_inp(path, mesh: Mesh, thickness, settings: Settings, case="G", loads: LoadSet = None,
              write_frd=False):
    """Write <path> (a .inp file). Returns the path."""
    settings.validate()
    check_group_props(thickness, mesh)
    if mesh.elems.shape[1] != 6:
        raise ValueError("ccx_writer expects S6 (6-node) triangles")
    if case not in ("G", "W"):
        raise ValueError("case must be 'G' or 'W'")
    if case == "G" and settings.extra_mass_kg > 0:
        raise NotImplementedError("extra_mass_kg > 0 needs the reference node (later step); set it to 0 for now")
    if case == "W" and (loads is None or loads.case != "W"):
        raise ValueError("case 'W' needs a LoadSet with case == 'W'")
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
 
    # --- material and shell sections (one per group = one thickness per part)
    L += ["*MATERIAL, NAME=STEEL", "*ELASTIC", f"{settings.E:.10g}, {settings.nu:.10g}",
          "*DENSITY", f"{settings.rho:.10g}"]
    for name, gname in zip(names, mesh.group_names):
        if name in present:
            L += [f"*SHELL SECTION, ELSET={name}, MATERIAL=STEEL", f"{thickness[gname]:.10g}"]
 
    # --- fixed support: all 6 DOF on the base ring (text comes from bcs.py)
    L += bcs.boundary_lines(mesh, "base")
 
    # --- load step
    L += ["*STEP", "*STATIC"]
    if case == "G":
        L += ["*DLOAD", f"EALL, GRAV, {G_ACC}, 0., 0., -1."]
    else:
        L.append("*CLOAD")
        f = loads.nodal_forces
        for n in np.where(np.abs(f).sum(axis=1) > 0)[0]:
            for d in range(3):
                if f[n, d] != 0.0:
                    L.append(f"{n + 1}, {d + 1}, {f[n, d]:.10g}")
 
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
 