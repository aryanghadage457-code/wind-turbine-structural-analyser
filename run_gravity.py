"""Step: full-turbine gravity case G. Run:  python run_gravity.py   (after the mesh runs fine)"""
import os, pickle, numpy as np
import gmsh
from contracts import Settings
from solver import bcs
from solver.mesh import calculate_s6_areas
from solver.ccx_writer import write_inp
from solver.ccx_runner import run_ccx
from solver import ccx_reader as R
 
 
def build_full_mesh():
    from geometry.default_generator import load_params, build_default
    from solver.mesh import build_mesh
    gmsh.initialize(); gmsh.model.add("wind_turbine")
    groups, thickness = build_default(load_params("data/default_turbine.json"))
    mesh = build_mesh(groups, h=1.0, h_base=0.5, d_refine=6.0, order=2, thickness=thickness)
    gmsh.finalize()
    return mesh, thickness
 
 
if __name__ == "__main__":
    os.makedirs("out", exist_ok=True)
    try:
        mesh, thickness = pickle.load(open("out/full_mesh.pkl", "rb"))     # cached mesh (made by run_mesh_only.py)
    except FileNotFoundError:
        mesh, thickness = build_full_mesh()
        pickle.dump((mesh, thickness), open("out/full_mesh.pkl", "wb"))
 
    S = Settings(); S.validate()
    bcs.assign_node_sets(mesh)
    bcs.preflight(mesh, thickness, expected_base_radius=3.0)                  # raises if the mesh is not safe
 
    n_out, n_in = R.check_outward(mesh)
    print(f"\ntower element normals: {n_out} outward, {n_in} inward")
 
    # expected weight from the TRUE curved S6 areas, per group
    area = calculate_s6_areas(mesh.nodes, mesh.elems)
    W = 0.0
    print("\n--- expected weight (S6 area x thickness x rho x g) ---")
    for gi, name in enumerate(mesh.group_names):
        w = area[mesh.elem_group == gi].sum() * thickness[name] * S.rho * 9.81
        W += w; print(f"{name:8s} {w/1e3:10.1f} kN")
    print(f"{'TOTAL':8s} {W/1e3:10.1f} kN")
 
    inp = write_inp("out/G.inp", mesh, thickness, S, case="G")
    dat = run_ccx(
        inp,
        ccx=r"C:\calculix\CalculiX-2.23.0-win-x64\CalculiX-2.23.0-win-x64\bin\ccx.exe"
    )
    res = R.read_result(dat, mesh, "G", applied_force=(0, 0, -W))
 
    Fz = res.base_reaction_force[2]
    print(f"\nbase reaction  Fx={res.base_reaction_force[0]:.1f}  Fy={res.base_reaction_force[1]:.1f}  Fz={Fz:.1f} N")
    print(f"expected Fz = {W:.1f} N   difference = {100*(Fz - W)/W:+.3f} %")
    print("base reaction moment about origin (N m):", np.round(res.base_reaction_moment))
 
    vm = R.von_mises(np.stack([res.stress_outer, res.stress_inner]))        # (2, E)
    print("\n--- gravity only: max von Mises per group (MPa), outer / inner ---")
    for gi, name in enumerate(mesh.group_names):
        m = mesh.elem_group == gi
        print(f"{name:8s} outer {vm[0][m].max()/1e6:8.1f}   inner {vm[1][m].max()/1e6:8.1f}")
    u = res.displacements
    print(f"\nmax displacement {np.linalg.norm(u, axis=1).max():.3f} m at z = {mesh.nodes[np.linalg.norm(u, axis=1).argmax(), 2]:.1f} m")
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
    pickle.dump(res, open("out/res_G.pkl", "wb"))
 