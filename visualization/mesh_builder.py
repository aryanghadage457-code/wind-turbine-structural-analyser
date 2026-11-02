
import numpy as np
import pyvista as pv

from vtk import VTK_QUADRATIC_TRIANGLE


def build_turbine_mesh(mesh):
    """
    Convert the existing CalculiX S6 shell mesh
    into a PyVista UnstructuredGrid.

    Parameters
    ----------
    mesh : contracts.Mesh
        Existing Member 2 mesh object.

    Returns
    -------
    pv.UnstructuredGrid
    """

    nodes = np.asarray(mesh.nodes, dtype=float)
    elements = np.asarray(mesh.elems, dtype=np.int64)
    if len(elements) == 0:
     raise ValueError("Mesh contains no elements.")

    if nodes.ndim != 2 or nodes.shape[1] != 3:
        raise ValueError("Expected node coordinates with shape (N, 3).")

    if elements.ndim != 2 or elements.shape[1] != 6:
        raise ValueError("Expected six-node S6 shell elements.")

    if elements.min() < 0 or elements.max() >= len(nodes):
        raise ValueError("Element connectivity contains invalid node indices.")

    # PyVista cell format:
    # [6, node1, node2, node3, node4, node5, node6]
    cells = np.column_stack((
        np.full(len(elements), 6, dtype=np.int64),
        elements
    )).ravel()

    cell_types = np.full(
        len(elements),
        VTK_QUADRATIC_TRIANGLE,
        dtype=np.uint8
    )

    grid = pv.UnstructuredGrid(
        cells,
        cell_types,
        nodes
    )

    # Preserve original element group information.
    grid.cell_data["group_id"] = np.asarray(mesh.elem_group)

    grid.field_data["group_names"] = np.asarray(
        mesh.group_names, dtype=str
    )

    return grid
