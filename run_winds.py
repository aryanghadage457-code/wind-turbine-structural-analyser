
"""Step: Full-turbine static wind case W.

Run:
    python run_wind.py

Run after confirming that the mesh generation and gravity case work.
"""

import os
import pickle

import gmsh
import numpy as np

from contracts import Settings
from solver import bcs, links
from solver.ccx_writer import write_inp
from solver.ccx_runner import run_ccx
from solver import ccx_reader as R

from solver.loads import orient_turbine, orientation_report, wind_loadset


# -------------------------------------------------
# CONFIGURATION
# -------------------------------------------------

# Replace with the actual path to your CalculiX executable.
CCX_EXE =r"C:\Users\banda\Downloads\CalculiX-2.23.0-win-x64\CalculiX-2.23.0-win-x64\bin\ccx.exe"


# -------------------------------------------------
# BUILD FULL TURBINE MESH
# -------------------------------------------------

def build_full_mesh(S):

    from geometry.default_generator import load_params, build_default
    from solver.mesh import build_mesh

    gmsh.initialize()
    gmsh.model.add("wind_turbine")

    try:
        groups, thickness = build_default(
            load_params("data/default_turbine.json")
        )

        mesh = build_mesh(
            groups,
            h=S.mesh_size,
            h_base=0.5,
            d_refine=6.0,
            order=2,
            thickness=thickness
        )

    finally:
        gmsh.finalize()

    return mesh, thickness


# -------------------------------------------------
# MAIN WIND ANALYSIS
# -------------------------------------------------

if __name__ == "__main__":

    os.makedirs("out", exist_ok=True)

    # Always generate a fresh mesh.
    S = Settings()
    S.validate()
    mesh, thickness = build_full_mesh(S)

    

    # IMPORTANT:
    # Apply the same element orientation procedure
    # in run_gravity.py and run_wind.py.
    orient_turbine(mesh)
    print("\n--- ELEMENT ORIENTATION REPORT ---")
    report = orientation_report(mesh)

    for group, result in report.items():
        print(group, result)
    bcs.assign_node_sets(mesh)

    # -------------------------------------------------
    # COMPONENT NODE HELPER
    # -------------------------------------------------

    def component_nodes(mesh, group):

        group_id = mesh.group_names.index(group)

        elements = mesh.elems[
            mesh.elem_group == group_id
        ]

        return np.unique(elements)

    # -------------------------------------------------
    # HUB - NACELLE RIGID LINK
    # Coordinate-based patch selection
    # -------------------------------------------------

    # Hub: select nodes near the rear pole.
    hub_nodes = component_nodes(mesh, "Hub")

    hub_target = np.array([0.0, 3.5, 90.0])

    hub_distance = np.linalg.norm(
        mesh.nodes[hub_nodes] - hub_target,
        axis=1
    )

    pa = hub_nodes[hub_distance <= 1.0]

    # Nacelle: select nodes near the centre of its front plate.
    nacelle_nodes = component_nodes(mesh, "Nacelle")

    nacelle_xyz = mesh.nodes[nacelle_nodes]

    pb = nacelle_nodes[
        (np.abs(nacelle_xyz[:, 1] - 3.0) < 1e-5) &
        (np.abs(nacelle_xyz[:, 0]) <= 1.0) &
        (np.abs(nacelle_xyz[:, 2] - 90.0) <= 1.0)
    ]

    print("\n--- INITIAL PATCH SELECTION ---")
    print("Hub patch nodes:", len(pa))
    print("Nacelle patch nodes:", len(pb))

    if len(pa) == 0 or len(pb) == 0:
        raise RuntimeError(
            "Hub or Nacelle rigid-link patch selection failed."
        )

    # Expand each patch by one element row.
    pa = links.add_rows(mesh, pa, 1, "Hub")
    pb = links.add_rows(mesh, pb, 1, "Nacelle")

    print("\n--- EXPANDED PATCHES ---")
    print("Hub patch nodes:", len(pa))
    print("Nacelle patch nodes:", len(pb))

    # Create the rigid link.
    LINKS = [
        links.make_link(
            mesh,
            "HUB_NACELLE",
            "Hub",
            pa,
            "Nacelle",
            pb
        )
    ]

    print("\nHub-Nacelle rigid link created successfully.")

    # -------------------------------------------------
    # COMPONENT CONNECTION CHECK
    # -------------------------------------------------

    print("\n--- COMPONENT CONNECTION CHECK ---")

    group_nodes = {}

    for gi, name in enumerate(mesh.group_names):

        elems = mesh.elems[
            mesh.elem_group == gi
        ]

        group_nodes[name] = set(elems.flatten())

    for i, name1 in enumerate(mesh.group_names):

        for name2 in mesh.group_names[i + 1:]:

            shared = group_nodes[name1] & group_nodes[name2]

            if shared:
                print(
                    f"{name1:10s} <-> {name2:10s}: "
                    f"{len(shared)} shared nodes"
                )
            else:
                print(
                    f"{name1:10s} <-> {name2:10s}: "
                    "NO shared nodes"
                )

    # -------------------------------------------------
    # TOWER TOP RING CONNECTION CHECK
    # -------------------------------------------------

    print("\n--- TOWER TOP RING CONNECTION CHECK ---")

    tower_top_nodes = component_nodes(mesh, "Tower_4")
    ring_nodes = component_nodes(mesh, "TowerTopRing")
    nacelle_nodes = component_nodes(mesh, "Nacelle")

    shared_tower_ring = np.intersect1d(
        tower_top_nodes,
        ring_nodes
    )

    shared_ring_nacelle = np.intersect1d(
        ring_nodes,
        nacelle_nodes
    )

    print(
        "Tower_4 <-> TowerTopRing shared nodes:",
        len(shared_tower_ring)
    )

    print(
        "TowerTopRing <-> Nacelle shared nodes:",
        len(shared_ring_nacelle)
    )

    if len(shared_tower_ring) == 0:
        raise RuntimeError(
            "Tower_4 and TowerTopRing are not connected."
        )

    if len(shared_ring_nacelle) == 0:
        raise RuntimeError(
            "TowerTopRing and Nacelle are not connected."
        )

    # -------------------------------------------------
    # PREFLIGHT CHECKS
    # -------------------------------------------------

    bcs.preflight(
        mesh,
        thickness,
        expected_base_radius=3.0,
        links=LINKS
    )

    # -------------------------------------------------
    # ELEMENT NORMAL CHECK
    # -------------------------------------------------

    n_out, n_in = R.check_outward(mesh)

    print(
        f"\ntower element normals: "
        f"{n_out} outward, {n_in} inward"
    )

    if n_in != 0:
        raise RuntimeError(
            "Inward tower element normals detected. "
            "Check orient_turbine() and the mesh."
        )

    # -------------------------------------------------
    # GENERATE WIND LOADS
    # -------------------------------------------------

    print("\n--- WIND LOAD GENERATION ---")

    wind_loads, component_report = wind_loadset(
        mesh,
        S,
        info=True
    )

    print("\n--- COMPONENT WIND LOAD REPORT ---")
    print(component_report)

    print("\n--- TOTAL WIND LOAD ---")

    print(
        "Total Fx:",
        wind_loads.total_force[0],
        "N"
    )

    print(
        "Total Fy:",
        wind_loads.total_force[1],
        "N"
    )

    print(
        "Total Fz:",
        wind_loads.total_force[2],
        "N"
    )

    print(
        "Base moment:",
        wind_loads.base_moment,
        "N m"
    )

    print(
        "Reference wind speed:",
        wind_loads.v_ref,
        "m/s"
    )

    # -------------------------------------------------
    # WRITE CALCULIX INPUT FILE
    # -------------------------------------------------

    inp = write_inp(
        "out/W.inp",
        mesh,
        thickness,
        S,
        case="W",
        loads=wind_loads,
        rigid_links=LINKS
    )

    # -------------------------------------------------
    # RUN CALCULIX
    # -------------------------------------------------

    dat = run_ccx(
        inp,
        ccx=CCX_EXE
    )

    # -------------------------------------------------
    # READ RESULTS
    # -------------------------------------------------

    res = R.read_result(
        dat,
        mesh,
        "W",
        applied_force=wind_loads.total_force,
        v_ref=S.v_ref
    )

    # -------------------------------------------------
    # BASE REACTION CHECK
    # -------------------------------------------------

    print("\n--- BASE REACTION CHECK ---")

    print(
        "Applied force:",
        np.round(wind_loads.total_force, 2),
        "N"
    )

    print(
        "Base reaction force:",
        np.round(res.base_reaction_force, 2),
        "N"
    )

    print(
        "Base reaction moment:",
        np.round(res.base_reaction_moment, 2),
        "N m"
    )

    force_balance = (
        wind_loads.total_force
        + res.base_reaction_force
    )

    print(
        "Force balance (should be near zero):",
        np.round(force_balance, 2),
        "N"
    )

    # -------------------------------------------------
    # VON MISES STRESS
    # -------------------------------------------------

    vm = R.von_mises(
        np.stack([
            res.stress_outer,
            res.stress_inner
        ])
    )

    print(
        "\n--- WIND ONLY: MAX VON MISES PER GROUP "
        "(MPa), OUTER / INNER ---"
    )

    for gi, name in enumerate(mesh.group_names):

        m = mesh.elem_group == gi

        print(
            f"{name:12s} "
            f"outer {vm[0][m].max() / 1e6:8.2f}  "
            f"inner {vm[1][m].max() / 1e6:8.2f}"
        )

    # -------------------------------------------------
    # DISPLACEMENTS
    # -------------------------------------------------

    u = res.displacements

    disp = np.linalg.norm(u, axis=1)

    imax = np.argmax(disp)

    print(
        f"\nMaximum displacement: "
        f"{disp[imax]:.4f} m "
        f"at z = {mesh.nodes[imax, 2]:.2f} m"
    )

    print("\n--- MAX DISPLACEMENT LOCATION ---")

    print("Node index:", imax)
    print("Original coordinates:", mesh.nodes[imax])
    print("Displacement vector:", u[imax])

    # -------------------------------------------------
    # MAXIMUM DISPLACEMENT BY COMPONENT
    # -------------------------------------------------

    print("\n--- MAX DISPLACEMENT BY COMPONENT ---")

    for gi, name in enumerate(mesh.group_names):

        element_ids = np.where(
            mesh.elem_group == gi
        )[0]

        node_ids = np.unique(
            mesh.elems[element_ids].flatten()
        )

        component_disp = np.linalg.norm(
            u[node_ids],
            axis=1
        )

        local_max = np.argmax(component_disp)

        node_id = node_ids[local_max]

        print(
            f"{name:12s}: "
            f"{component_disp[local_max]:.4f} m "
            f"at {mesh.nodes[node_id]}"
        )

    # -------------------------------------------------
    # SAVE RESULTS
    # -------------------------------------------------

    with open("out/res_W.pkl", "wb") as f:
        pickle.dump(res, f)

    # Save the mesh used for this wind analysis.
    with open("out/wind_mesh.pkl", "wb") as f:
        pickle.dump(mesh, f)

    print("\nWind analysis completed.")
    print("Results saved to out/res_W.pkl")
    print("Mesh saved to out/wind_mesh.pkl")