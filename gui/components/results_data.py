"""Loads one solve's output folder (full_mesh.pkl + stress_strain_results.npz,
and optionally res_G.pkl/res_W.pkl for displacement) into a PyVista grid plus
the raw results dict, ready for the Results viewer.
"""
import pickle
from pathlib import Path

import numpy as np

from visualization.mesh_builder import build_turbine_mesh


class ResultsData:
    def __init__(self, mesh, group_properties, results, grid, displacement=None):
        self.mesh = mesh
        self.group_properties = group_properties
        self.results = results
        self.grid = grid
        self.displacement = displacement  # (N, 3) m, or None if not available

    @property
    def wind_speed(self):
        return float(self.results.get("wind_speed", 0.0))

    @property
    def wind_direction(self):
        return float(self.results.get("wind_direction", 0.0))

    @property
    def v_ref(self):
        return float(self.results.get("v_ref", 0.0))


def _combined_displacement(out_dir, results):
    """disp = disp_G + (v/v_ref)^2 * disp_W — the v^2 convention stated in
    StressAndStrain.py and run_analysis.py's docstrings. NOT independently
    confirmed for displacement specifically; verify with Member 2/3 before
    trusting absolute displacement values shown here."""
    g_path, w_path = out_dir / "res_G.pkl", out_dir / "res_W.pkl"
    if not g_path.is_file() or not w_path.is_file():
        return None
    try:
        with g_path.open("rb") as f:
            g_result = pickle.load(f)
        with w_path.open("rb") as f:
            w_result = pickle.load(f)
        v = float(results.get("wind_speed", 0.0))
        v_ref = float(results.get("v_ref", 1.0)) or 1.0
        scale = (v / v_ref) ** 2
        return np.asarray(g_result.displacements) + scale * np.asarray(w_result.displacements)
    except Exception:
        return None


def load_results_data(out_dir):
    """Returns a ResultsData, or None if the solve output isn't there."""
    out_dir = Path(out_dir)
    mesh_path = out_dir / "full_mesh.pkl"
    npz_path = out_dir / "stress_strain_results.npz"
    if not mesh_path.is_file() or not npz_path.is_file():
        return None

    with mesh_path.open("rb") as f:
        mesh_obj = pickle.load(f)
    mesh, group_properties = mesh_obj if isinstance(mesh_obj, tuple) else (mesh_obj, {})

    loaded = np.load(npz_path, allow_pickle=True)
    results = {k: loaded[k] for k in loaded.files}

    grid = build_turbine_mesh(mesh)
    displacement = _combined_displacement(out_dir, results)

    return ResultsData(mesh, group_properties, results, grid, displacement)