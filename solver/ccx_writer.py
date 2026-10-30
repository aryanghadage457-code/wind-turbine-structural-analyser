import numpy as np

from contracts import Mesh, GroupProps, Settings, check_group_props

CCX_TYPE = {
    3: "S3",
    6: "S6"
}
def _id_lines(ids, per_line=10):
    """Comma-separated id lines for *NSET (ids are 1-based already)."""
    return [
        ", ".join(map(str, ids[i:i + per_line]))
        for i in range(0, len(ids), per_line)
    ]


def write_inp(path, mesh: Mesh, props: GroupProps, s: Settings, g=9.81):
    """Write a gravity-only (case G) CalculiX input file. SI units.
    Node id = index+1, element id = index+1."""

    check_group_props(props, mesh)

    k = mesh.elems.shape[1]

    if k not in CCX_TYPE:
        raise ValueError(f"Unsupported nodes per element: {k}")

    etype = CCX_TYPE[k]
    L = ["*NODE"]
    for i, (x, y, z) in enumerate(mesh.nodes, start=1):
        L.append(f"{i}, {x:.9e}, {y:.9e}, {z:.9e}")

    for gi, name in enumerate(mesh.group_names):
        L.append(f"*ELEMENT, TYPE={etype}, ELSET={name}")

        for e in np.where(mesh.elem_group == gi)[0]:
            conn = ", ".join(str(n + 1) for n in mesh.elems[e])
            L.append(f"{e + 1}, {conn}")

    L += ["*ELSET, ELSET=EALL, GENERATE", f"1, {mesh.n_elems}",
          "*NSET, NSET=NALL, GENERATE", f"1, {mesh.n_nodes}",
          "*NSET, NSET=BASE"]

    L += _id_lines((mesh.node_sets["base"] + 1).tolist())

    L += ["*MATERIAL, NAME=MAT",
          "*ELASTIC",
          f"{s.E:.6e}, {s.nu}",
          "*DENSITY",
          f"{s.rho}"]

    for name in mesh.group_names:
        L += [f"*SHELL SECTION, ELSET={name}, MATERIAL=MAT",
              f"{props[name]}"]

    L += ["*BOUNDARY", "BASE, 1, 6",
          "*STEP", "*STATIC",
          "*DLOAD", f"EALL, GRAV, {g}, 0., 0., -1."]
    L += ["*NODE PRINT, NSET=NALL", "U",
          "*NODE PRINT, NSET=BASE, TOTALS=ONLY", "RF",
          "*EL PRINT, ELSET=EALL", "S",
          "*END STEP"]

    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")