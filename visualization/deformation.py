
import numpy as np
import pyvista as pv


def apply_deformation(grid, displacements, scale=1.0):
    """
    Apply nodal displacements to a PyVista mesh.

    Parameters
    ----------
    grid : pv.UnstructuredGrid
        Original turbine mesh.

    displacements : numpy.ndarray
        Nodal displacement array of shape (N, 3), in metres.

    scale : float
        Deformation magnification factor.

    Returns
    -------
    pv.UnstructuredGrid
        New mesh with deformation applied.
    """

    displacements = np.asarray(displacements, dtype=float)

    if displacements.shape != (grid.n_points, 3):
        raise ValueError(
            f"Expected displacement shape "
            f"({grid.n_points}, 3), got {displacements.shape}"
        )

    if not np.all(np.isfinite(displacements)):
        raise ValueError("Displacements contain invalid values.")

    if not np.isscalar(scale) or not np.isfinite(scale) or scale < 0:
      raise ValueError("Scale must be a finite, non-negative scalar.")

    deformed_grid = grid.copy(deep=True)

    deformed_grid.points = (
        grid.points + scale * displacements
    )

    deformed_grid.point_data["displacement_magnitude"] = (
        np.linalg.norm(displacements, axis=1)
    )

    return deformed_grid
