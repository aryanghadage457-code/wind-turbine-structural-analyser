"""
contracts.py - frozen data contracts shared by all four members.

Rules (docs/conventions.md):
  * SI units only: m, kg, N, Pa, s, K.
  * +X East, +Y North, Z up. Tower base centre at the origin. Tension positive.
  * Load case: PARKED rotor only. No rotor thrust.
  * Nobody changes a field here without telling everyone.

Stress component order (6 values per element and surface):
    (xx, yy, zz, xy, xz, yz)
This is the order I believe CalculiX prints. MEMBER 2 MUST VERIFY IT AGAINST
THE MANUAL ON DAY 3 and also state: (a) which axes the stresses are in
(global or local), (b) which surface is "outer". Both load cases must be
reported in the SAME axes, because failure.py adds the tensors component-wise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np

STRESS_ORDER = ("xx", "yy", "zz", "xy", "xz", "yz")


def _check_shape(name: str, arr, shape_tail: tuple, n_first: Optional[int] = None):
    """Raise ValueError if arr is not an array with the expected shape."""
    arr = np.asarray(arr)
    if arr.ndim != len(shape_tail) + 1 or arr.shape[1:] != shape_tail:
        raise ValueError(f"{name}: expected shape (n, {', '.join(map(str, shape_tail))}), got {arr.shape}")
    if n_first is not None and arr.shape[0] != n_first:
        raise ValueError(f"{name}: expected {n_first} rows, got {arr.shape[0]}")


# ----------------------------------------------------------------------------
# Mesh  (produced by Member 2's mesh.py)
# ----------------------------------------------------------------------------
@dataclass
class Mesh:
    nodes: np.ndarray                 # (N, 3) metres
    elems: np.ndarray                 # (E, k) 0-based node indices, k = 3, 4, 6 or 8
    elem_group: np.ndarray            # (E,) int index into group_names
    group_names: list                 # e.g. ["Tower_1", "Tower_2", "Nacelle", "Hub", "Blade_1"]
    node_sets: Dict[str, np.ndarray] = field(default_factory=dict)
    # node_sets example: {"base": array of node indices, "ref_ring": ..., "ref_node": array([idx])}

    def __post_init__(self):
        self.nodes = np.asarray(self.nodes, dtype=float)
        self.elems = np.asarray(self.elems, dtype=int)
        self.elem_group = np.asarray(self.elem_group, dtype=int)
        _check_shape("Mesh.nodes", self.nodes, (3,))
        if self.elems.ndim != 2:
            raise ValueError("Mesh.elems must be 2D (E, k)")
        if self.elem_group.shape != (self.elems.shape[0],):
            raise ValueError("Mesh.elem_group must have one entry per element")
        if self.elems.size and (self.elems.min() < 0 or self.elems.max() >= len(self.nodes)):
            raise ValueError("Mesh.elems refers to a node index out of range (0-based indices expected)")
        if self.elem_group.size and self.elem_group.max() >= len(self.group_names):
            raise ValueError("Mesh.elem_group refers to a group index beyond group_names")

    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    @property
    def n_elems(self) -> int:
        return len(self.elems)


# ----------------------------------------------------------------------------
# GroupProps  (thickness per part, metres)
# ----------------------------------------------------------------------------
GroupProps = Dict[str, float]   # {"Tower_1": 0.027, "Tower_2": 0.022, ...}


def check_group_props(props: GroupProps, mesh: Mesh) -> None:
    """Every group in the mesh needs a positive thickness."""
    for name in mesh.group_names:
        if name not in props:
            raise ValueError(f"No thickness given for group '{name}'")
        if props[name] <= 0:
            raise ValueError(f"Thickness of '{name}' must be positive, got {props[name]}")


# ----------------------------------------------------------------------------
# Settings  (everything the GUI collects)
# ----------------------------------------------------------------------------
@dataclass
class Settings:
    # Material (single material for the whole structure)
    E: float = 210e9                  # Pa        PLACEHOLDER: set from materials.json
    nu: float = 0.3                   # -
    rho: float = 7850.0               # kg/m^3
    yield_strength: float = 345e6     # Pa

    # Wind (parked rotor)
    wind_bearing_deg: float = 0.0     # compass bearing wind comes FROM (0 = N, 90 = E)
    v_ref: float = 50.0               # m/s hub-height wind speed used in the single W solve
    shear_alpha: float = 0.14         # power-law exponent   PLACEHOLDER
    z_hub: float = 90.0               # m, reference height   PLACEHOLDER: from default_turbine.json
    air_pressure: float = 101325.0    # Pa
    air_temp: float = 288.15          # K
    Cd_tower: float = 1.0             # drag coefficient: tower, nacelle, hub   PLACEHOLDER
    Cd_blade: float = 0.5             # drag coefficient: feathered blades      PLACEHOLDER

    # Extra mass for internal machinery (applied as weight on the reference node, case G only)
    extra_mass_kg: float = 0.0

    # Analysis
    safety_factor: float = 1.5
    buckling_knockdown: float = 0.2   # kappa. PLACEHOLDER: take from EN 1993-1-6 / course notes
    mesh_size: float = 1.0            # m on the tower

    # Fixed for now. Kept so the contract never has to change if operating case is added later.
    load_case: str = "parked"

    @property
    def air_density(self) -> float:
        """rho_air = p / (287.05 * T)  [kg/m^3]"""
        return self.air_pressure / (287.05 * self.air_temp)

    def validate(self) -> None:
        """Raise ValueError with a clear message on bad input (GUI shows it)."""
        positives = {"E": self.E, "rho": self.rho, "yield_strength": self.yield_strength,
                     "v_ref": self.v_ref, "z_hub": self.z_hub, "air_pressure": self.air_pressure,
                     "air_temp": self.air_temp, "mesh_size": self.mesh_size,
                     "safety_factor": self.safety_factor}
        for name, val in positives.items():
            if not val > 0:
                raise ValueError(f"{name} must be positive, got {val}")
        if not (0.0 < self.nu < 0.5):
            raise ValueError(f"nu must be between 0 and 0.5, got {self.nu}")
        if self.extra_mass_kg < 0:
            raise ValueError("extra_mass_kg cannot be negative")
        if not np.isfinite(self.wind_bearing_deg):
            raise ValueError("wind_bearing_deg must be finite")
        if not np.isfinite(self.shear_alpha) or self.shear_alpha < 0:
            raise ValueError("shear_alpha must be finite and non-negative")
        if not np.isfinite(self.Cd_tower) or self.Cd_tower < 0 or not np.isfinite(self.Cd_blade) or self.Cd_blade < 0:
            raise ValueError("drag coefficients must be finite and non-negative")
        if self.safety_factor < 1.0:
            raise ValueError("safety_factor must be at least 1")
        if self.load_case != "parked":
            raise ValueError("Only the 'parked' load case is implemented")


# ----------------------------------------------------------------------------
# LoadSet  (produced by Member 3's loads.py, consumed by Member 2's ccx_writer.py)
# ----------------------------------------------------------------------------
@dataclass
class LoadSet:
    nodal_forces: np.ndarray          # (N, 3) N, surface wind force on each mesh node
    ref_node_force: np.ndarray        # (3,) N, machinery weight (case G); zero for case W
    ref_node_moment: np.ndarray       # (3,) N*m, zero unless a load is offset
    total_force: np.ndarray           # (3,) N, total applied force, for the checks
    base_moment: np.ndarray           # (3,) N*m about the base centre, for the checks
    case: str = "W"                   # "G" or "W"
    v_ref: Optional[float] = None     # m/s used for case W

    def __post_init__(self):
        self.nodal_forces = np.asarray(self.nodal_forces, dtype=float)
        _check_shape("LoadSet.nodal_forces", self.nodal_forces, (3,))
        for name in ("ref_node_force", "ref_node_moment", "total_force", "base_moment"):
            arr = np.asarray(getattr(self, name), dtype=float)
            if arr.shape != (3,):
                raise ValueError(f"LoadSet.{name} must have shape (3,), got {arr.shape}")
            setattr(self, name, arr)
        if self.case not in ("G", "W"):
            raise ValueError("LoadSet.case must be 'G' or 'W'")


# ----------------------------------------------------------------------------
# SolveResult  (produced by Member 2's ccx_reader.py, one per load case)
# ----------------------------------------------------------------------------
@dataclass
class SolveResult:
    case: str                         # "G" or "W"
    stress_outer: np.ndarray          # (E, 6) Pa, order = STRESS_ORDER
    stress_inner: Optional[np.ndarray]  # (E, 6) Pa, or None if CalculiX output cannot give it
    displacements: np.ndarray         # (N, 3) m
    base_reaction_force: np.ndarray   # (3,) N, summed over the base node set
    base_reaction_moment: np.ndarray  # (3,) N*m about the base centre
    applied_force: np.ndarray         # (3,) N, total applied force (copied from LoadSet)
    v_ref: Optional[float] = None     # m/s, for case W only
    metadata: dict = field(default_factory=dict)  # provenance; kept separate from engineering fields

    def __post_init__(self):
        self.stress_outer = np.asarray(self.stress_outer, dtype=float)
        _check_shape("SolveResult.stress_outer", self.stress_outer, (6,))
        n_e = self.stress_outer.shape[0]
        if self.stress_inner is not None:
            self.stress_inner = np.asarray(self.stress_inner, dtype=float)
            _check_shape("SolveResult.stress_inner", self.stress_inner, (6,), n_e)
        self.displacements = np.asarray(self.displacements, dtype=float)
        _check_shape("SolveResult.displacements", self.displacements, (3,))
        for name in ("base_reaction_force", "base_reaction_moment", "applied_force"):
            arr = np.asarray(getattr(self, name), dtype=float)
            if arr.shape != (3,):
                raise ValueError(f"SolveResult.{name} must have shape (3,), got {arr.shape}")
            setattr(self, name, arr)
        if self.case not in ("G", "W"):
            raise ValueError("SolveResult.case must be 'G' or 'W'")
        if not isinstance(self.metadata, dict):
            raise ValueError("SolveResult.metadata must be a dictionary")
        if self.v_ref is not None and (not np.isfinite(self.v_ref) or self.v_ref <= 0):
            raise ValueError("SolveResult.v_ref must be finite and positive when provided")


# ----------------------------------------------------------------------------
# FailureResult  (produced by Member 3's failure.py)
# ----------------------------------------------------------------------------
@dataclass
class FailureResult:
    v_fail: Optional[float]           # m/s hub speed at first yield (SF = 1); None if no failure found
    v_allow: Optional[float]          # m/s hub speed at yield / safety_factor
    governing_element: Optional[int]  # element index at v_fail
    governing_surface: Optional[str]  # "outer" or "inner"
    governing_location: Optional[np.ndarray]  # (3,) m, element centroid
    governing_group: Optional[str]    # e.g. "Tower_1"
    force_at_failure: Optional[np.ndarray]    # (3,) N total wind force at v_fail
    base_moment_at_failure: Optional[np.ndarray]  # (3,) N*m
    utilisation_curve: tuple          # (v array, utilisation array); utilisation = max von Mises / yield
    message: str = ""                 # e.g. "Fails under gravity alone", "No failure below 100 m/s"
