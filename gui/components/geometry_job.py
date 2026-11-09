"""Runs in a SEPARATE PROCESS. No Qt here.

Two stages:
  stage="geometry": Member 1's build_default() + a quick, coarse display
      tessellation. Fast, just something to look at. No real meshing yet.
  stage="mesh": Member 1's build_default() + Member 2's solver.mesh.build_mesh()
      (the REAL analysis mesh), converted to display triangles. This is the
      literal mesh CalculiX solves on, not a separate approximation.
"""
import time
import traceback

import numpy as np


def _component_map(groups):
    return {
        "Tower": [n for n in groups if n.startswith("Tower_")],
        "Nacelle": ["Nacelle"],
        "Hub": ["Hub"],
        "TowerTopRing": ["TowerTopRing"],
        "Blade 1": ["Blade_1"],
        "Blade 2": ["Blade_2"],
        "Blade 3": ["Blade_3"],
    }


def run_job(config, queue, stage="geometry", mesh_size=1.0,
            mesh_base_size=0.5, mesh_refine_distance=6.0):
    import gmsh
    from geometry.default_generator import build_default

    try:
        t0 = time.time()
        queue.put(("progress", "Initialising Gmsh..."))
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)

        queue.put(("progress", "Building turbine surfaces..."))
        groups, thickness = build_default(config)
        queue.put(("progress", f"Geometry built in {time.time() - t0:.1f} s."))

        comp_map = _component_map(groups)

        if stage == "geometry":
            points, components, cell_counts, surface_counts, thick_by_comp, total_cells = \
                _display_tessellation(gmsh, groups, thickness, comp_map, queue)
        else:
            points, components, cell_counts, surface_counts, thick_by_comp, total_cells = \
                _real_mesh(gmsh, groups, thickness, comp_map, queue,
                           mesh_size, mesh_base_size, mesh_refine_distance)

        if not components:
            raise RuntimeError("No displayable surface elements were found.")

        queue.put(("done", {
            "points": points,
            "components": components,
            "total_cells": total_cells,
            "generation_time": time.time() - t0,
            "component_cell_counts": cell_counts,
            "component_surface_counts": surface_counts,
            "component_thickness": thick_by_comp,
            "stage": stage,
        }))
    except Exception:
        queue.put(("error", traceback.format_exc()))
    finally:
        try:
            gmsh.finalize()
        except Exception:
            pass


def _display_tessellation(gmsh, groups, thickness, comp_map, queue):
    """Fast, coarse triangulation - just for looking at the CAD shape.
    This is NOT the analysis mesh; Mesh Settings replaces it with the real one."""
    queue.put(("progress", "Preparing a quick preview..."))
    gmsh.option.setNumber("Mesh.MeshSizeMax", 8.0)
    gmsh.option.setNumber("Mesh.MeshSizeMin", 0.5)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 8)
    gmsh.model.mesh.generate(2)

    node_tags, coords, _ = gmsh.model.mesh.getNodes()
    if len(node_tags) == 0:
        raise RuntimeError("Gmsh generated no mesh nodes.")
    points = np.asarray(coords, dtype=np.float64).reshape(-1, 3)
    node_tags = np.asarray(node_tags, dtype=np.int64)
    lookup = np.full(int(node_tags.max()) + 1, -1, dtype=np.int64)
    lookup[node_tags] = np.arange(len(node_tags))

    components, total_cells = {}, 0
    cell_counts, surface_counts, thick_by_comp = {}, {}, {}

    for component, names in comp_map.items():
        chunks, cell_count, surface_count, thick_values = [], 0, 0, []
        for name in names:
            tags = groups.get(name, [])
            surface_count += len(tags)
            if name in thickness:
                thick_values.append(thickness[name])
            for tag in tags:
                types, _, conn = gmsh.model.mesh.getElements(2, int(tag))
                for etype, c in zip(types, conn):
                    n = gmsh.model.mesh.getElementProperties(int(etype))[3]
                    if n not in (3, 4):
                        continue
                    idx = lookup[np.asarray(c, dtype=np.int64)].reshape(-1, n)
                    counts = np.full((len(idx), 1), n, dtype=np.int64)
                    chunks.append(np.hstack([counts, idx]).ravel())
                    cell_count += len(idx)
        if chunks:
            components[component] = np.concatenate(chunks)
        total_cells += cell_count
        cell_counts[component] = cell_count
        surface_counts[component] = surface_count
        thick_by_comp[component] = thick_values

    return points, components, cell_counts, surface_counts, thick_by_comp, total_cells


def _real_mesh(gmsh, groups, thickness, comp_map, queue,
               mesh_size, mesh_base_size, mesh_refine_distance):
    """Member 2's actual analysis mesh (solver/mesh.py), converted to
    display triangles from the S6 corner nodes. This is the literal mesh
    that gets solved on - not a GUI approximation of it."""
    from solver.mesh import build_mesh

    queue.put(("progress", "Building the analysis mesh (solver/mesh.py)..."))
    mesh = build_mesh(
        groups,
        h=mesh_size,
        h_base=mesh_base_size,
        d_refine=mesh_refine_distance,
        order=2,
        thickness=thickness,
    )
    queue.put(("progress", f"Analysis mesh built: {mesh.n_nodes} nodes, {mesh.n_elems} elements."))

    points = mesh.nodes
    group_index = {name: i for i, name in enumerate(mesh.group_names)}

    components, total_cells = {}, 0
    cell_counts, surface_counts, thick_by_comp = {}, {}, {}

    for component, names in comp_map.items():
        chunks, cell_count, thick_values = [], 0, []
        for name in names:
            if name in thickness:
                thick_values.append(thickness[name])
            gi = group_index.get(name)
            if gi is None:
                continue
            sel = mesh.elem_group == gi
            if not sel.any():
                continue
            corners = mesh.elems[sel][:, :3]
            tri = np.hstack(
                [np.full((len(corners), 1), 3, dtype=np.int64), corners]
            ).ravel()
            chunks.append(tri)
            cell_count += len(corners)
        if chunks:
            components[component] = np.concatenate(chunks)
        total_cells += cell_count
        cell_counts[component] = cell_count
        surface_counts[component] = cell_count
        thick_by_comp[component] = thick_values

    return points, components, cell_counts, surface_counts, thick_by_comp, total_cells