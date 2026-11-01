
"""Step: full-turbine gravity case G. Run: python run_gravity.py (after the mesh runs fine)"""

import os, pickle, numpy as np
import gmsh
from contracts import Settings
from solver import bcs
from solver.mesh import calculate_s6_areas
from solver.ccx_writer import write_inp, default_ref_nodes
from solver.ccx_runner import run_ccx
from solver import ccx_reader as R
from pathlib import Path
from solver import links, bcs


def build_full_mesh():
    from geometry.default_generator import load_params, build_default
    from solver.mesh import build_mesh

    gmsh.initialize()
    gmsh.model.add("wind_turbine")

    groups, thickness = build_default(
        load_params("data/default_turbine.json")
    )

    # TEMPORARY DIAGNOSTIC ONLY
    # thickness["Nacelle"] *= 3
    # thickness["Hub"] *= 3
    # print("\n--- TEMPORARY THICKNESS CHECK ---")
    # print("Nacelle:", thickness["Nacelle"], "m")
    # print("Hub:", thickness["Hub"], "m")

    mesh = build_mesh(
        groups, h=1.0, h_base=0.5,
        d_refine=6.0, order=2, thickness=thickness
    )

    gmsh.finalize()
    return mesh, thickness


if __name__ == "__main__":

    os.makedirs("out", exist_ok=True)

    # Always generate a fresh mesh (no full_mesh.pkl cache).
    mesh, thickness = build_full_mesh()

    S = Settings()
    S.validate()

    bcs.assign_node_sets(mesh)

    # -------------------------------------------------
    # HUB - NACELLE RIGID LINK
    # Coordinate-based patch selection
    # -------------------------------------------------

    def component_nodes(mesh, group):
        group_id = mesh.group_names.index(group)
        elements = mesh.elems[mesh.elem_group == group_id]
        return np.unique(elements)

    # Hub: select nodes near the rear pole
    hub_nodes = component_nodes(mesh, "Hub")

    hub_target = np.array([0.0, 3.5, 90.0])

    hub_distance = np.linalg.norm(
        mesh.nodes[hub_nodes] - hub_target,
        axis=1
    )

    pa = hub_nodes[hub_distance <= 1.0]

    # Nacelle: select nodes near the centre of its front plate
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
        print("X range:", mesh.nodes[pa, 0].min(), mesh.nodes[pa, 0].max())
        print("Y range:", mesh.nodes[pa, 1].min(), mesh.nodes[pa, 1].max())
        print("Z range:", mesh.nodes[pa, 2].min(), mesh.nodes[pa, 2].max())

    print("\n--- NACELLE PATCH COORDINATES ---")
    if len(pb):
        print("X range:", mesh.nodes[pb, 0].min(), mesh.nodes[pb, 0].max())
        print("Y range:", mesh.nodes[pb, 1].min(), mesh.nodes[pb, 1].max())
        print("Z range:", mesh.nodes[pb, 2].min(), mesh.nodes[pb, 2].max())

    # Expand each patch by one element row
    pa = links.add_rows(mesh, pa, 1, "Hub")
    pb = links.add_rows(mesh, pb, 1, "Nacelle")

    print("\n--- EXPANDED PATCHES ---")
    print("Hub patch nodes:", len(pa))
    print("Nacelle patch nodes:", len(pb))

    # Create the rigid link
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

    # Inspect shared nodes between component groups
    print("\n--- COMPONENT CONNECTION CHECK ---")

    group_nodes = {}

    for gi, name in enumerate(mesh.group_names):
        elems = mesh.elems[mesh.elem_group == gi]
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

    bcs.preflight(
        mesh,
        thickness,
        expected_base_radius=3.0,
        links=LINKS
    )

    n_out, n_in = R.check_outward(mesh)
    print(f"\ntower element normals: {n_out} outward, {n_in} inward")

    # expected weight from the TRUE curved S6 areas, per group
    area = calculate_s6_areas(mesh.nodes, mesh.elems)
    W = 0.0

    print("\n--- expected weight (S6 area x thickness x rho x g) ---")

    for gi, name in enumerate(mesh.group_names):

        # Use equivalent density for blades and steel density for other parts
        rho = 2050.0 if name.startswith("Blade_") else S.rho

        w = (
            area[mesh.elem_group == gi].sum()
            * thickness[name] * rho * 9.81
        )

        W += w
        print(f"{name:8s} {w/1e3:10.1f} kN")

    print(f"{'TOTAL':8s} {W/1e3:10.1f} kN")

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

    inp = write_inp(
        "out/G.inp", mesh, thickness, S,
        case="G",
        ref_nodes=ref_nodes,
        rigid_links=LINKS
    )

    dat = run_ccx(
        inp,
        ccx=r"C:\CalculiX\CalculiX-2.23.0-win-x64\CalculiX-2.23.0-win-x64\bin\ccx.exe"
    )

    extra_mass = 190622.0 + 53263.0
    total_weight = W + extra_mass * 9.81

    res = R.read_result(
        dat, mesh, "G",
        applied_force=(0, 0, -total_weight)
    )

    Fz = res.base_reaction_force[2]

    print(
        f"\nbase reaction  Fx={res.base_reaction_force[0]:.1f}  "
        f"Fy={res.base_reaction_force[1]:.1f}  Fz={Fz:.1f} N"
    )

    print(
        f"expected Fz = {total_weight:.1f} N   "
        f"difference = {100*(Fz - total_weight)/total_weight:+.3f} %"
    )

    print(
        "base reaction moment about origin (N m):",
        np.round(res.base_reaction_moment)
    )

    vm = R.von_mises(
        np.stack([res.stress_outer, res.stress_inner])
    )  # (2, E)

    print(
        "\n--- gravity only: max von Mises per group "
        "(MPa), outer / inner ---"
    )

    for gi, name in enumerate(mesh.group_names):
        m = mesh.elem_group == gi
        print(
            f"{name:8s} outer {vm[0][m].max()/1e6:8.1f}  "
            f"inner {vm[1][m].max()/1e6:8.1f}"
        )

    u = res.displacements

    print(
        f"\nmax displacement {np.linalg.norm(u, axis=1).max():.3f} m "
        f"at z = {mesh.nodes[np.linalg.norm(u, axis=1).argmax(), 2]:.1f} m"
    )

    # Find the node with maximum displacement
    disp = np.linalg.norm(u, axis=1)
    imax = np.argmax(disp)

    print("\n--- MAX DISPLACEMENT LOCATION ---")
    print("Node index:", imax)
    print("Original coordinates:", mesh.nodes[imax])
    print("Displacement vector:", u[imax])
    print("Displacement magnitude:", disp[imax])

    print("\n--- BLADE 1 DISPLACEMENT CHECK ---")

    for name in ["Blade_1", "Blade_2", "Blade_3"]:
        gi = mesh.group_names.index(name)
        element_ids = np.where(mesh.elem_group == gi)[0]

        node_ids = np.unique(mesh.elems[element_ids].flatten())

        blade_disp = np.linalg.norm(u[node_ids], axis=1)
        max_local = np.argmax(blade_disp)
        node_id = node_ids[max_local]

        print(
            f"{name}: max displacement = {blade_disp[max_local]:.3f} m, "
            f"at coordinates = {mesh.nodes[node_id]}"
        )

    print("\n--- BLADE ROOT AND TIP DISPLACEMENTS ---")

    for name in ["Blade_1", "Blade_2", "Blade_3"]:
        gi = mesh.group_names.index(name)
        element_ids = np.where(mesh.elem_group == gi)[0]
        node_ids = np.unique(mesh.elems[element_ids].flatten())

        blade_nodes = mesh.nodes[node_ids]

        # Distance from rotor axis (Y direction)
        radial_distance = np.sqrt(
            blade_nodes[:, 0]**2 + (blade_nodes[:, 2] - 90.0)**2
        )

        root_id = node_ids[np.argmin(radial_distance)]
        tip_id = node_ids[np.argmax(radial_distance)]

        print(f"\n{name}")

        for label, nid in [("Root", root_id), ("Tip", tip_id)]:
            print(
                f"{label}: position={mesh.nodes[nid]}, "
                f"displacement={u[nid]}, "
                f"magnitude={np.linalg.norm(u[nid]):.3f} m"
            )

    print("\n--- MAX DISPLACEMENT BY COMPONENT ---")

    for gi, name in enumerate(mesh.group_names):
        element_ids = np.where(mesh.elem_group == gi)[0]
        node_ids = np.unique(mesh.elems[element_ids].flatten())

        component_disp = np.linalg.norm(u[node_ids], axis=1)
        local_max = np.argmax(component_disp)
        node_id = node_ids[local_max]

        print(
            f"{name:10s}: {component_disp[local_max]:.4f} m "
            f"at {mesh.nodes[node_id]}"
        )

    pickle.dump(res, open("out/res_G.pkl", "wb"))
