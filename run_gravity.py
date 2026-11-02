
"""Step: Full-turbine gravity case G.

Run:
    python run_gravity.py

Run after confirming that the mesh generation works.
"""

import os
import pickle

import gmsh
import numpy as np

from pathlib import Path

from contracts import Settings
from solver import bcs, links
from solver.mesh import calculate_s6_areas
from solver.ccx_writer import write_inp, default_ref_nodes
from solver.ccx_runner import run_ccx
from solver import ccx_reader as R


# -------------------------------------------------
# CONFIGURATION
# -------------------------------------------------

# IMPORTANT:
# Replace this with the actual path to your CalculiX executable.
CCX_EXE = r"C:\calculix\CalculiX-2.23.0-win-x64\CalculiX-2.23.0-win-x64\bin\ccx.exe"


# -------------------------------------------------
# BUILD FULL TURBINE MESH
# -------------------------------------------------

def build_full_mesh():

    from geometry.default_generator import load_params, build_default
    from solver.mesh import build_mesh

    gmsh.initialize()
    gmsh.model.add("wind_turbine")

    try:
        groups, thickness = build_default(
            load_params("data/default_turbine.json")
        )

        # TEMPORARY DIAGNOSTIC ONLY
        # thickness["Nacelle"] *= 3
        # thickness["Hub"] *= 3

        mesh = build_mesh(
            groups,
            h=1.0,
            h_base=0.5,
            d_refine=6.0,
            order=2,
            thickness=thickness
        )

    finally:
        gmsh.finalize()

    return mesh, thickness


# -------------------------------------------------
# MAIN GRAVITY ANALYSIS
# -------------------------------------------------

if __name__ == "__main__":

    os.makedirs("out", exist_ok=True)

    # Always generate a fresh mesh.
    mesh, thickness = build_full_mesh()

    S = Settings()
    S.validate()

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

    print("\n--- HUB PATCH COORDINATES ---")

    if len(pa):
        print(
            "X range:",
            mesh.nodes[pa, 0].min(),
            mesh.nodes[pa, 0].max()
        )
        print(
            "Y range:",
            mesh.nodes[pa, 1].min(),
            mesh.nodes[pa, 1].max()
        )
        print(
            "Z range:",
            mesh.nodes[pa, 2].min(),
            mesh.nodes[pa, 2].max()
        )

    print("\n--- NACELLE PATCH COORDINATES ---")

    if len(pb):
        print(
            "X range:",
            mesh.nodes[pb, 0].min(),
            mesh.nodes[pb, 0].max()
        )
        print(
            "Y range:",
            mesh.nodes[pb, 1].min(),
            mesh.nodes[pb, 1].max()
        )
        print(
            "Z range:",
            mesh.nodes[pb, 2].min(),
            mesh.nodes[pb, 2].max()
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

    # -------------------------------------------------
    # EXPECTED WEIGHT
    # Using TRUE curved S6 areas
    # -------------------------------------------------

    area = calculate_s6_areas(
        mesh.nodes,
        mesh.elems
    )

    W = 0.0

    print(
        "\n--- expected weight "
        "(S6 area x thickness x rho x g) ---"
    )

    for gi, name in enumerate(mesh.group_names):

        # Equivalent density for blades;
        # steel density for other components.
        rho = (
            2050.0
            if name.startswith("Blade_")
            else S.rho
        )

        w = (
            area[mesh.elem_group == gi].sum()
            * thickness[name]
            * rho
            * 9.81
        )

        W += w

        print(f"{name:12s} {w / 1e3:10.1f} kN")

    print(f"{'TOTAL':12s} {W / 1e3:10.1f} kN")

    # -------------------------------------------------
    # REFERENCE MASS POSITIONS
    # -------------------------------------------------

    from geometry.default_generator import load_params

    params = load_params("data/default_turbine.json")

    ref_nodes = default_ref_nodes(params)

    print("\n--- REFERENCE MASS POSITIONS ---")

    for ref in ref_nodes:

        print(
            f"{ref['name']}: "
            f"mass = {ref['mass_kg']} kg, "
            f"COM = {ref['point']}"
        )

    # -------------------------------------------------
    # WRITE CALCULIX INPUT FILE
    # -------------------------------------------------

    inp = write_inp(
        "out/G.inp",
        mesh,
        thickness,
        S,
        case="G",
        ref_nodes=ref_nodes,
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

    extra_mass = 190622.0 + 53263.0

    total_weight = W + extra_mass * 9.81

    res = R.read_result(
        dat,
        mesh,
        "G",
        applied_force=(0, 0, -total_weight)
    )

    # -------------------------------------------------
    # BASE REACTIONS
    # -------------------------------------------------

    Fz = res.base_reaction_force[2]

    print(
        f"\nbase reaction "
        f"Fx={res.base_reaction_force[0]:.1f} "
        f"Fy={res.base_reaction_force[1]:.1f} "
        f"Fz={Fz:.1f} N"
    )

    print(
        f"expected Fz = {total_weight:.1f} N   "
        f"difference = "
        f"{100 * (Fz - total_weight) / total_weight:+.3f} %"
    )

    print(
        "base reaction moment about origin (N m):",
        np.round(res.base_reaction_moment)
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
        "\n--- gravity only: max von Mises per group "
        "(MPa), outer / inner ---"
    )

    for gi, name in enumerate(mesh.group_names):

        m = mesh.elem_group == gi

        print(
            f"{name:12s} "
            f"outer {vm[0][m].max() / 1e6:8.1f}  "
            f"inner {vm[1][m].max() / 1e6:8.1f}"
        )

    # -------------------------------------------------
    # DISPLACEMENTS
    # -------------------------------------------------

    u = res.displacements

    disp = np.linalg.norm(u, axis=1)

    imax = np.argmax(disp)

    print(
        f"\nmax displacement {disp[imax]:.3f} m "
        f"at z = {mesh.nodes[imax, 2]:.1f} m"
    )

    # -------------------------------------------------
    # MAXIMUM DISPLACEMENT LOCATION
    # -------------------------------------------------

    print("\n--- MAX DISPLACEMENT LOCATION ---")

    print("Node index:", imax)
    print("Original coordinates:", mesh.nodes[imax])
    print("Displacement vector:", u[imax])
    print("Displacement magnitude:", disp[imax])

    # -------------------------------------------------
    # BLADE DISPLACEMENT CHECK
    # -------------------------------------------------

    print("\n--- BLADE DISPLACEMENT CHECK ---")

    for name in ["Blade_1", "Blade_2", "Blade_3"]:

        gi = mesh.group_names.index(name)

        element_ids = np.where(
            mesh.elem_group == gi
        )[0]

        node_ids = np.unique(
            mesh.elems[element_ids].flatten()
        )

        blade_disp = np.linalg.norm(
            u[node_ids],
            axis=1
        )

        max_local = np.argmax(blade_disp)

        node_id = node_ids[max_local]

        print(
            f"{name}: max displacement = "
            f"{blade_disp[max_local]:.3f} m, "
            f"at coordinates = {mesh.nodes[node_id]}"
        )

    # -------------------------------------------------
    # BLADE ROOT AND TIP DISPLACEMENTS
    # -------------------------------------------------

    print("\n--- BLADE ROOT AND TIP DISPLACEMENTS ---")

    for name in ["Blade_1", "Blade_2", "Blade_3"]:

        gi = mesh.group_names.index(name)

        element_ids = np.where(
            mesh.elem_group == gi
        )[0]

        node_ids = np.unique(
            mesh.elems[element_ids].flatten()
        )

        blade_nodes = mesh.nodes[node_ids]

        # Distance from rotor axis (Y direction).
        radial_distance = np.sqrt(
            blade_nodes[:, 0] ** 2
            + (blade_nodes[:, 2] - 90.0) ** 2
        )

        root_id = node_ids[
            np.argmin(radial_distance)
        ]

        tip_id = node_ids[
            np.argmax(radial_distance)
        ]

        print(f"\n{name}")

        for label, nid in [
            ("Root", root_id),
            ("Tip", tip_id)
        ]:

            print(
                f"{label}: "
                f"position={mesh.nodes[nid]}, "
                f"displacement={u[nid]}, "
                f"magnitude={np.linalg.norm(u[nid]):.3f} m"
            )

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

    with open("out/res_G.pkl", "wb") as f:
        pickle.dump(res, f)

    print("\nGravity analysis completed.")
    print("Results saved to out/res_G.pkl")
