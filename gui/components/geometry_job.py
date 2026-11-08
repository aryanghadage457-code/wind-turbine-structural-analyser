"""Runs in a SEPARATE PROCESS. No Qt here.

Builds the turbine with Member 1's build_default(), meshes the surfaces with
Member 1's tested settings, and sends plain numpy arrays back on a queue.
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


def run_job(config, queue):
    import gmsh
    from geometry.default_generator import build_default

    try:
        t0 = time.time()
        queue.put(("progress", "Initialising Gmsh..."))
        gmsh.initialize()
        gmsh.option.setNumber("General.Terminal", 0)

        queue.put(("progress", "Building turbine surfaces..."))
        groups, thickness = build_default(config)
        queue.put(("progress", f"Geometry built in {time.time() - t0:.1f} s. Meshing..."))

        # Member 1's tested settings (about 3 s for the default turbine)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 3.0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)
        gmsh.option.setNumber("Mesh.MeshSizeMin", 0.15)

        t1 = time.time()
        gmsh.model.mesh.generate(2)
        queue.put(("progress", f"Surface mesh done in {time.time() - t1:.1f} s. Extracting..."))

        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        if len(node_tags) == 0:
            raise RuntimeError("Gmsh generated no mesh nodes.")
        points = np.asarray(coords, dtype=np.float64).reshape(-1, 3)
        node_tags = np.asarray(node_tags, dtype=np.int64)
        lookup = np.full(int(node_tags.max()) + 1, -1, dtype=np.int64)
        lookup[node_tags] = np.arange(len(node_tags))

        comp_map = _component_map(groups)
        components, total_cells = {}, 0
        cell_counts, surface_counts, thickness_by_component = {}, {}, {}

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
            thickness_by_component[component] = thick_values

        if not components:
            raise RuntimeError("No displayable surface elements were found.")

        queue.put(("done", {
            "points": points,
            "components": components,          # {name: flat PyVista faces array}
            "total_cells": total_cells,
            "generation_time": time.time() - t0,
            "component_cell_counts": cell_counts,
            "component_surface_counts": surface_counts,
            "component_thickness": thickness_by_component,
        }))
    except Exception:
        queue.put(("error", traceback.format_exc()))
    finally:
        try:
            gmsh.finalize()
        except Exception:
            pass