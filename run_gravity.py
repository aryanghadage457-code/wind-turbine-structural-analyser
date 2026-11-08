
"""Step: Full-turbine gravity case G.

Run:
    python run_gravity.py

Run after confirming that the mesh generation works.
"""

import os
import pickle

import gmsh
import numpy as np
from solver.loads import orient_turbine

from pathlib import Path

from contracts import Settings
from solver import bcs, links
from solver.mesh import calculate_s6_areas
from solver.ccx_writer import (
    write_inp,
    default_ref_nodes,
    element_thickness
)
from solver.ccx_runner import run_ccx
from solver import ccx_reader as R
from analysis_metadata import geometry_fingerprint, mesh_fingerprint, file_fingerprint, make_metadata, atomic_pickle


# -------------------------------------------------
# CONFIGURATION
# -------------------------------------------------

# IMPORTANT:
# Replace this with the actual path to your CalculiX executable.
CCX_EXE =r"C:\CalculiX\CalculiX-2.23.0-win-x64\CalculiX-2.23.0-win-x64\bin\ccx.exe"
OUT_DIR = Path(os.environ.get("TURBINE_OUT", "out")).resolve()
CONFIG_PATH = Path(os.environ.get("TURBINE_CONFIG", "data/default_turbine.json")).resolve()
# -------------------------------------------------
# NREL BLADE MASS + EI MATCHING
# -------------------------------------------------

BLADE_TABLE = "data/NRELOffshrBsline5MW_Blade.dat"

BLADE_KW = dict(
    blade_ei_file=BLADE_TABLE,
    blade_mass_match=True,
    blade_mass_factor=1.04536
)


# -------------------------------------------------
# BUILD FULL TURBINE MESH
# -------------------------------------------------

def build_full_mesh(S, config_path=None):

    from geometry.default_generator import load_params, build_default
    from solver.mesh import build_mesh

    gmsh.initialize()
    gmsh.model.add("wind_turbine")

    try:
        groups, thickness = build_default(
            load_params(config_path or CONFIG_PATH)
        )

        # TEMPORARY DIAGNOSTIC ONLY
        # thickness["Nacelle"] *= 3
        # thickness["Hub"] *= 3

        mesh = build_mesh(
            groups,
            h=S.mesh_size,
            h_base=float(os.environ.get("TURBINE_MESH_BASE_SIZE", 0.5)),
            d_refine=float(os.environ.get("TURBINE_MESH_REFINE_DISTANCE", 6.0)),
            order=int(os.environ.get("TURBINE_MESH_ORDER", 2)),
            thickness=thickness
        )

    finally:
        gmsh.finalize()

    return mesh, thickness


# -------------------------------------------------
# MAIN GRAVITY ANALYSIS
# -------------------------------------------------

if __name__ == "__main__":

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Always generate a fresh mesh.
    S = Settings()
    params = __import__("json").loads(CONFIG_PATH.read_text(encoding="utf-8"))
    S.mesh_size = float(os.environ.get("TURBINE_MESH_SIZE", S.mesh_size))
    S.z_hub = float(params["tower"]["sections"][-1]["z1"]) + float(params["nacelle"]["height"]) / 2.0
    S.validate()
    mesh, thickness = build_full_mesh(S, CONFIG_PATH)

    # Apply consistent element orientation.
    orient_turbine(mesh)

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

    z_top = float(params["tower"]["sections"][-1]["z1"])
    nac = params["nacelle"]
    hub_cfg = params["hub"]
    hub_target = np.array([0.0, float(hub_cfg["overhang"]) - float(hub_cfg["diameter"]) / 2.0, z_top + float(nac["height"]) / 2.0])

    hub_distance = np.linalg.norm(
        mesh.nodes[hub_nodes] - hub_target,
        axis=1
    )

    pa = hub_nodes[hub_distance <= 1.0]

    # Nacelle: select nodes near the centre of its front plate.
    nacelle_nodes = component_nodes(mesh, "Nacelle")

    nacelle_xyz = mesh.nodes[nacelle_nodes]

    pb = nacelle_nodes[
        (np.abs(nacelle_xyz[:, 1] - float(nac["y_front"])) < 1e-5) &
        (np.abs(nacelle_xyz[:, 0]) <= float(nac["width"]) / 2.0) &
        (np.abs(nacelle_xyz[:, 2] - (z_top + float(nac["height"]) / 2.0)) <= float(nac["height"]) / 2.0)
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

    tower_group = f"Tower_{len(params['tower']['sections'])}"
    tower_top_nodes = component_nodes(mesh, tower_group)
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
        f"{tower_group} <-> TowerTopRing shared nodes:",
        len(shared_tower_ring)
    )

    print(
        "TowerTopRing <-> Nacelle shared nodes:",
        len(shared_ring_nacelle)
    )

    if len(shared_tower_ring) == 0:
        raise RuntimeError(
            f"{tower_group} and TowerTopRing are not connected."
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
        expected_base_radius=float(params["tower"]["sections"][0]["d0"]) / 2.0,
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

    # Calculate the actual thickness assigned to every element.
    # Blade elements get their NREL-based regional thickness.
    # Other components retain their original thickness.

    t_el = element_thickness(
        mesh,
        thickness,
        S,
        **BLADE_KW
    )

    print(
        "\n--- expected weight "
        "(S6 area x element thickness x rho x g) ---"
    )

    for gi, name in enumerate(mesh.group_names):

        mask = mesh.elem_group == gi

        rho = (
            2050.0
            if name.startswith("Blade_")
            else S.rho
        )

        w = np.sum(
            area[mask]
            * t_el[mask]
            * rho
            * 9.81
        )

        W += w

        if name.startswith("Blade_"):
            print(
                f"{name:12s} {w / 1e3:10.1f} kN "
                f"(thickness: {t_el[mask].min()*1000:.2f}–"
                f"{t_el[mask].max()*1000:.2f} mm)"
            )
        else:
            print(f"{name:12s} {w / 1e3:10.1f} kN")

    print(f"{'TOTAL':12s} {W / 1e3:10.1f} kN")
    # -------------------------------------------------
    # REFERENCE MASS POSITIONS
    # -------------------------------------------------

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
        str(OUT_DIR / "G.inp"),
        mesh,
        thickness,
        S,
        case="G",
        ref_nodes=ref_nodes,
        rigid_head_groups=("Nacelle", "Hub"),
        **BLADE_KW
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

    # Provenance is attached only after CalculiX completed and the result reader succeeded.
    res.metadata = make_metadata(
        case="G", geometry_hash=geometry_fingerprint(CONFIG_PATH),
        mesh_hash=mesh_fingerprint(mesh), solver={"executable": CCX_EXE or os.environ.get("CCX_PATH") or "PATH lookup",
                "input_file_sha256": file_fingerprint(inp), "solver_version": "see CalculiX .log"},
        material={"E_Pa": S.E, "nu": S.nu, "rho_kg_m3": S.rho, "yield_strength_Pa": S.yield_strength},
        settings={"mesh_size_m": S.mesh_size,
                  "mesh_base_size_m": float(os.environ.get("TURBINE_MESH_BASE_SIZE", 0.5)),
                  "mesh_refine_distance_m": float(os.environ.get("TURBINE_MESH_REFINE_DISTANCE", 6.0)),
                  "mesh_order": int(os.environ.get("TURBINE_MESH_ORDER", 2)),
                  "load_case": S.load_case, "extra_mass_kg": 190622.0 + 53263.0}
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
            + (blade_nodes[:, 2] - (z_top + float(nac["height"]) / 2.0)) ** 2
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

        # -------------------------------------------------
    # SAVE MESH AND RESULTS
    # -------------------------------------------------

    # Save the exact mesh used for this analysis.
    with open(str(OUT_DIR / "full_mesh.pkl"), "wb") as f:
        pickle.dump((mesh, thickness), f)

    # Save gravity solver results.
    atomic_pickle(OUT_DIR / "res_G.pkl", res)

    print("\nMesh saved to out/full_mesh.pkl")
    print("Results saved to out/res_G.pkl")