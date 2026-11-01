"""
StressAndStrain.py - combined gravity + wind stress and strain post-processing (Member 3).

    sigma_total = sigma_G + (v / v_ref)^2 * sigma_W            (component-wise, per surface)

Everything below was derived from the ACTUAL project files (contracts.py, solver/ccx_reader.py,
solver/ccx_writer.py, out/res_G.pkl, out/G.dat, out/G.inp). Verified facts and consequences:

 1. SolveResult.stress_outer / stress_inner are (E, 6) arrays in Pa, order STRESS_ORDER =
    (xx, yy, zz, xy, xz, yz). The CalculiX .dat header confirms
    "(elem, integ.pnt., sxx, syy, szz, sxy, sxz, syz)". Shear entries are TENSOR components sigma_ij.
 2. The stresses are in each element's LOCAL SHELL AXES (axis 3 = element normal), NOT global axes.
    Confirmed numerically on the tower: median local syy = -11.7 MPa (= axial W/(pi D t)), sxx ~ 0.
    Consequence: G and W stresses may be added component-wise only because both runs use the same
    mesh and node order, hence identical local axes per element. This module checks every
    dimension it can; the SolveResult has no "frame" flag, so same-frame is an input assumption.
    Principal VALUES and invariants are frame independent; principal DIRECTIONS are reported in the
    element-local axes (optionally converted to global with element_local_axes()).
 3. Surface values are linear extrapolations through the thickness from the mean of the 3 in-plane
    integration points of each of 3 layers (ccx_reader.surface_stresses). The raw 9 integration-point
    values are NOT stored in SolveResult (they exist only in the .dat file).
 4. "outer" = the +normal side of the element (right-hand rule on the corner-node order). I verified
    that the element normals point outward on all groups of the actual mesh, so outer = outward.
 5. Element row i of the stress arrays = mesh element index i = CalculiX element id i + 1.
 6. E, nu and thickness are NOT part of SolveResult. Settings holds one E/nu, but the real gravity run
    gave the blades a different Young's modulus per spanwise region (3.6 GPa ... 133 GPa, an
    equivalent-stiffness model). The per-element values are recovered from the CalculiX input
    file (MaterialProps.from_inp). Strains therefore use the same E and nu CalculiX used.

Through-thickness assumption (strain):
    The shell is a thin plate: sigma_zz (local) should be ~0 (plane stress). In the actual result it
    is ~0 on the tower (|szz| < 1.1 MPa vs ~12 MPa in-plane) but reaches several hundred MPa at local
    hot spots (nacelle/hub, due to the expanded-solid shell treatment near concentrated loads).
      strain_model="plane_stress" (default): sigma_zz is NOT used in Hooke's law (taken as 0, the shell
          assumption). eps_zz = -nu/E (sxx + syy) follows from it. Transverse shears sxz, syz are kept
          (Reissner-Mindlin shell), eps_xz = sxz/(2G).
      strain_model="full_3d": all six components enter Hooke's law (exact inverse of CalculiX's 3D law).
    The per-element ratio |szz| / von Mises is reported so you can see where the two models differ.
    STRESS quantities (principal, von Mises, ...) always use all six stored components, exactly like
    Member 2's von_mises(), so results are comparable.

Shear-strain convention:
    strain (E, 6) holds TENSORIAL strain eps_ij in STRAIN_ORDER (xx, yy, zz, xy, xz, yz).
    engineering_shear (E, 3) holds gamma_xy, gamma_xz, gamma_yz = 2 * eps_ij.
    Principal strains and invariants use the tensorial strain; max_shear_strain = eps1 - eps3
    (engineering value, = 2 * tensorial max shear).

Equivalent strain:
    eps_eq = 1/(1+nu) * sqrt(1/2 [(e1-e2)^2 + (e2-e3)^2 + (e3-e1)^2])   (elastic von Mises equivalent
    strain with the material's nu). For linear elasticity this equals von_mises(stress used) / E.

Units: SI. Stress Pa, strain dimensionless (m/m), I1 [Pa], J2 [Pa^2], J3 [Pa^3]. Tension positive.

Quick use:
    from StressAndStrain import *
    g   = load_solve_result("out/res_G.pkl")
    mat = MaterialProps.from_inp("out/G.inp", n_elems=g.stress_outer.shape[0])
    res = calculate_stress_and_strain(g, make_zero_wind_result(g), wind_speed=0.0, material=mat)
    print(res.report())
Future (real wind from Member 2) - same call, nothing else changes:
    res = calculate_stress_and_strain(g, wind_result_W, wind_speed=25.0, material=mat)
"""
from __future__ import annotations

import os
import pickle
import re
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

import numpy as np

from contracts import STRESS_ORDER, Mesh, Settings, SolveResult

# ----------------------------------------------------------------------------
# Conventions
# ----------------------------------------------------------------------------
STRAIN_ORDER = STRESS_ORDER            # (xx, yy, zz, xy, xz, yz); shear entries are TENSORIAL eps_ij
SURFACES = ("outer", "inner")
STRAIN_MODELS = ("plane_stress", "full_3d")
_IDX = {name: i for i, name in enumerate(STRESS_ORDER)}   # never hard-code the component positions
SIGMA_ZZ_FLAG_RATIO = 0.05             # |szz| / von Mises above this flags a plane-stress violation

UNITS: Dict[str, str] = {
    "stress": "Pa", "stress_gravity": "Pa", "stress_wind_scaled": "Pa",
    "principal": "Pa", "principal_dirs": "- (unit vectors, element-local axes)",
    "von_mises": "Pa", "max_shear": "Pa", "mean_stress": "Pa",
    "I1": "Pa", "J2": "Pa^2", "J3": "Pa^3",
    "strain": "- (m/m, tensorial shear)", "engineering_shear": "- (rad, gamma = 2 eps_ij)",
    "principal_strain": "-", "max_shear_strain": "- (engineering, eps1 - eps3)",
    "equivalent_strain": "-", "sigma_zz_ratio": "-",
}


# ----------------------------------------------------------------------------
# Material / section data per element
# ----------------------------------------------------------------------------
@dataclass
class MaterialProps:
    """Isotropic linear-elastic properties PER ELEMENT (so spanwise-varying blade E is supported)."""
    E: np.ndarray                          # (n_elems,) Pa
    nu: np.ndarray                         # (n_elems,) -
    thickness: Optional[np.ndarray] = None  # (n_elems,) m, informational (not needed for strain)
    source: str = "unspecified"

    def __post_init__(self):
        self.E = np.asarray(self.E, dtype=float)
        self.nu = np.asarray(self.nu, dtype=float)
        if self.E.ndim != 1 or self.nu.shape != self.E.shape:
            raise ValueError(f"MaterialProps: E and nu must be 1-D arrays of equal length, got {self.E.shape}, {self.nu.shape}")
        if not (np.isfinite(self.E).all() and (self.E > 0).all()):
            raise ValueError("MaterialProps: every Young's modulus must be finite and positive")
        if not (np.isfinite(self.nu).all() and (self.nu >= 0).all() and (self.nu < 0.5).all()):
            raise ValueError("MaterialProps: every Poisson's ratio must satisfy 0 <= nu < 0.5")
        if self.thickness is not None:
            self.thickness = np.asarray(self.thickness, dtype=float)
            if self.thickness.shape != self.E.shape:
                raise ValueError("MaterialProps: thickness must have one value per element")

    @property
    def n_elems(self) -> int:
        return len(self.E)

    @classmethod
    def uniform(cls, E: float, nu: float, n_elems: int, source: str = "uniform") -> "MaterialProps":
        return cls(np.full(n_elems, float(E)), np.full(n_elems, float(nu)), None, source)

    @classmethod
    def from_settings(cls, settings: Settings, n_elems: int) -> "MaterialProps":
        """One E/nu for every element (contracts.Settings). NOT correct for the actual gravity run,
        whose blades use per-region E; use from_inp for that."""
        return cls.uniform(settings.E, settings.nu, n_elems, source="contracts.Settings (uniform)")

    @classmethod
    def from_inp(cls, inp_path: str, n_elems: int) -> "MaterialProps":
        """Recover per-element E, nu and shell thickness from the CalculiX input file that produced
        the result (ccx_writer.write_inp). Element id k in the file = mesh row k-1."""
        return read_inp_element_properties(inp_path, n_elems)


def _expand_ids(tokens: List[str], sets: Dict[str, set], generate: bool) -> set:
    """Integer element ids and/or names of previously defined sets -> set of ids."""
    out: set = set()
    if generate:
        v = [int(float(t)) for t in tokens]
        for k in range(0, len(v) - len(v) % 3, 3):
            out.update(range(v[k], v[k + 1] + 1, v[k + 2]))
        if len(v) % 3 == 2:
            out.update(range(v[-2], v[-1] + 1))
        return out
    for t in tokens:
        if re.fullmatch(r"[+-]?\d+", t):
            out.add(int(t))
        else:
            key = t.upper()
            if key not in sets:
                raise ValueError(f"inp parser: element set '{t}' is referenced before it is defined")
            out |= sets[key]
    return out


def read_inp_element_properties(inp_path: str, n_elems: int) -> MaterialProps:
    """Parse *ELEMENT/*ELSET/*MATERIAL/*ELASTIC/*SHELL SECTION of a CalculiX .inp (as written by
    ccx_writer.py). Raises if any element has no (or two) shell sections, or non-isotropic elasticity."""
    if not os.path.isfile(inp_path):
        raise FileNotFoundError(f"CalculiX input file not found: {inp_path}")
    elsets: Dict[str, set] = {}
    materials: Dict[str, tuple] = {}
    sections: List[tuple] = []            # (elset, material, thickness)
    kw, params, cur_mat, cur_sec = None, {}, None, None
    cont_elem: Optional[int] = None       # element whose node list continues on the next line
    with open(inp_path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("**"):
                continue
            if line.startswith("*"):
                parts = [p.strip() for p in line[1:].split(",")]
                kw = parts[0].upper()
                params = {}
                for p in parts[1:]:
                    k, _, v = p.partition("=")
                    params[k.strip().upper()] = v.strip().upper()
                cont_elem = None
                if kw == "MATERIAL":
                    cur_mat = params.get("NAME")
                elif kw == "ELASTIC":
                    if params.get("TYPE", "ISOTROPIC") not in ("ISO", "ISOTROPIC"):
                        raise ValueError("inp parser: only isotropic *ELASTIC is supported")
                elif kw == "SHELL SECTION":
                    cur_sec = (params.get("ELSET"), params.get("MATERIAL"))
                continue
            tok = [t.strip() for t in line.rstrip(",").split(",") if t.strip()]
            if kw == "ELEMENT":
                if cont_elem is None:
                    cont_elem = int(tok[0])
                    elsets.setdefault(params.get("ELSET", "_NOSET"), set()).add(cont_elem)
                if not line.endswith(","):
                    cont_elem = None
            elif kw == "ELSET":
                name = params["ELSET"]
                elsets.setdefault(name, set()).update(_expand_ids(tok, elsets, "GENERATE" in params))
            elif kw == "ELASTIC":
                materials[cur_mat] = (float(tok[0]), float(tok[1]))
            elif kw == "SHELL SECTION":
                sections.append((cur_sec[0], cur_sec[1], float(tok[0])))
    E = np.full(n_elems, np.nan)
    nu = np.full(n_elems, np.nan)
    th = np.full(n_elems, np.nan)
    for elset, mat, t in sections:
        if elset not in elsets:
            raise ValueError(f"inp parser: shell section refers to unknown element set '{elset}'")
        if mat not in materials:
            raise ValueError(f"inp parser: shell section refers to material '{mat}' without *ELASTIC data")
        idx = np.fromiter((i - 1 for i in elsets[elset]), dtype=int)
        if idx.size and (idx.min() < 0 or idx.max() >= n_elems):
            raise ValueError(f"inp parser: element set '{elset}' has ids outside 1..{n_elems}; wrong n_elems?")
        if np.isfinite(E[idx]).any():
            raise ValueError(f"inp parser: section '{elset}' overlaps elements that already have a section")
        E[idx], nu[idx], th[idx] = materials[mat][0], materials[mat][1], t
    if np.isnan(E).any():
        raise ValueError(f"inp parser: {int(np.isnan(E).sum())} of {n_elems} elements have no shell section "
                         f"(wrong file or wrong n_elems?)")
    return MaterialProps(E, nu, th, source=f"CalculiX input file {os.path.basename(inp_path)}")


def resolve_material(material, n_elems: int) -> MaterialProps:
    """Accept MaterialProps, contracts.Settings (uniform) or {'E':..,'nu':..}. Never invents values."""
    if material is None:
        raise ValueError("No material given. Young's modulus and Poisson's ratio are not stored in SolveResult; "
                         "pass MaterialProps.from_inp('out/G.inp', n), a Settings object, or {'E':..,'nu':..}.")
    if isinstance(material, MaterialProps):
        mp = material
    elif isinstance(material, Settings):
        mp = MaterialProps.from_settings(material, n_elems)
    elif isinstance(material, dict):
        if "E" not in material or "nu" not in material:
            raise ValueError("material dict needs both 'E' (Pa) and 'nu'")
        mp = MaterialProps.uniform(material["E"], material["nu"], n_elems, source="user dict (uniform)")
    else:
        raise TypeError(f"material must be MaterialProps, Settings or dict, got {type(material).__name__}")
    if mp.n_elems != n_elems:
        raise ValueError(f"material has {mp.n_elems} elements but the results have {n_elems}")
    return mp


# ----------------------------------------------------------------------------
# Tensor helpers (pure functions, reusable by other Member 3 modules)
# ----------------------------------------------------------------------------
def stress_to_tensor(s6: np.ndarray) -> np.ndarray:
    """(..., 6) in STRESS_ORDER -> (..., 3, 3) symmetric tensor (tensorial shear entries)."""
    s6 = np.asarray(s6, dtype=float)
    if s6.shape[-1] != 6:
        raise ValueError(f"expected last dimension 6 (xx,yy,zz,xy,xz,yz), got shape {s6.shape}")
    T = np.empty(s6.shape[:-1] + (3, 3))
    T[..., 0, 0], T[..., 1, 1], T[..., 2, 2] = s6[..., _IDX["xx"]], s6[..., _IDX["yy"]], s6[..., _IDX["zz"]]
    T[..., 0, 1] = T[..., 1, 0] = s6[..., _IDX["xy"]]
    T[..., 0, 2] = T[..., 2, 0] = s6[..., _IDX["xz"]]
    T[..., 1, 2] = T[..., 2, 1] = s6[..., _IDX["yz"]]
    return T


def wind_scale_factor(wind_speed: float, v_ref: float) -> float:
    """(v / v_ref)^2 : wind pressure (hence stress of this linear model) scales with speed squared."""
    if not (np.isfinite(wind_speed) and wind_speed >= 0):
        raise ValueError(f"wind_speed must be finite and >= 0, got {wind_speed}")
    if not (v_ref is not None and np.isfinite(v_ref) and v_ref > 0):
        raise ValueError(f"reference wind speed v_ref must be finite and > 0, got {v_ref}")
    return float((wind_speed / v_ref) ** 2)


def combine_stress(sigma_g: np.ndarray, sigma_w: np.ndarray, wind_speed: float, v_ref: float) -> np.ndarray:
    """sigma_total = sigma_G + (v/v_ref)^2 sigma_W, all six components, same surface only."""
    sigma_g, sigma_w = np.asarray(sigma_g, float), np.asarray(sigma_w, float)
    if sigma_g.shape != sigma_w.shape:
        raise ValueError(f"cannot combine stress arrays of shapes {sigma_g.shape} and {sigma_w.shape}")
    return sigma_g + wind_scale_factor(wind_speed, v_ref) * sigma_w


def principal_decomposition(s6: np.ndarray):
    """Eigen-decomposition of the stress (or strain) tensor, sorted DESCENDING.
    Returns values (..., 3) [s1 >= s2 >= s3] and directions (..., 3, 3) whose COLUMN i is the unit
    vector of value i, in the same axes as the input components (sign of each vector is arbitrary)."""
    w, v = np.linalg.eigh(stress_to_tensor(s6))
    return w[..., ::-1], v[..., :, ::-1]


def stress_invariants(s6: np.ndarray):
    """I1 = tr(s) [Pa];  J2 = 1/2 dev:dev [Pa^2];  J3 = det(dev) [Pa^3];  also mean stress I1/3 and
    von Mises sqrt(3 J2). Computed from the full tensor (deviator = s - I1/3 * Identity)."""
    T = stress_to_tensor(s6)
    I1 = np.trace(T, axis1=-2, axis2=-1)
    mean = I1 / 3.0
    dev = T - mean[..., None, None] * np.eye(3)
    J2 = 0.5 * np.einsum("...ij,...ij->...", dev, dev)
    J3 = np.linalg.det(dev)
    vm = np.sqrt(np.maximum(3.0 * J2, 0.0))
    return I1, mean, J2, J3, vm


def von_mises_from_principal(p: np.ndarray) -> np.ndarray:
    """Independent von Mises from principal values (used as an internal consistency check)."""
    return np.sqrt(0.5 * ((p[..., 0] - p[..., 1]) ** 2 + (p[..., 1] - p[..., 2]) ** 2 + (p[..., 2] - p[..., 0]) ** 2))


def strain_from_stress(s6: np.ndarray, E: np.ndarray, nu: np.ndarray, model: str = "plane_stress") -> np.ndarray:
    """Hooke's law for an isotropic material:  eps_ij = (1+nu)/E sigma_ij - nu/E tr(sigma) delta_ij.
    Returns TENSORIAL strain (..., 6) in STRAIN_ORDER (shear = eps_ij, NOT engineering gamma).
    model='plane_stress': sigma_zz (shell through-thickness stress) is set to 0 before applying the law,
        which gives eps_zz = -nu/E (sxx+syy); transverse shears sxz, syz are kept.
    model='full_3d': all six components are used."""
    if model not in STRAIN_MODELS:
        raise ValueError(f"strain model must be one of {STRAIN_MODELS}, got '{model}'")
    s = np.array(s6, dtype=float, copy=True)
    if model == "plane_stress":
        s[..., _IDX["zz"]] = 0.0
    E = np.asarray(E, float)
    nu = np.asarray(nu, float)
    tr = s[..., _IDX["xx"]] + s[..., _IDX["yy"]] + s[..., _IDX["zz"]]
    eps = np.empty_like(s)
    for n in ("xx", "yy", "zz"):
        eps[..., _IDX[n]] = ((1 + nu) * s[..., _IDX[n]] - nu * tr) / E
    for n in ("xy", "xz", "yz"):
        eps[..., _IDX[n]] = (1 + nu) / E * s[..., _IDX[n]]      # = sigma / (2 G)
    return eps


def equivalent_strain_from_principal(pe: np.ndarray, nu: np.ndarray) -> np.ndarray:
    """Elastic von Mises equivalent strain with the material's nu (see module docstring)."""
    d = np.sqrt(0.5 * ((pe[..., 0] - pe[..., 1]) ** 2 + (pe[..., 1] - pe[..., 2]) ** 2 + (pe[..., 2] - pe[..., 0]) ** 2))
    return d / (1.0 + np.asarray(nu, float))


# ----------------------------------------------------------------------------
# Result containers
# ----------------------------------------------------------------------------
@dataclass
class SurfaceResult:
    """All per-element results for ONE surface ('outer' or 'inner'). Arrays have one row per element."""
    surface: str
    stress: np.ndarray               # (E,6) Pa   total tensor, STRESS_ORDER, element-local axes
    stress_gravity: np.ndarray       # (E,6) Pa   sigma_G
    stress_wind_scaled: np.ndarray   # (E,6) Pa   (v/v_ref)^2 sigma_W
    principal: np.ndarray            # (E,3) Pa   s1 >= s2 >= s3
    principal_dirs: np.ndarray       # (E,3,3)    column i = direction of principal[:, i] (local axes)
    von_mises: np.ndarray            # (E,)  Pa
    max_shear: np.ndarray            # (E,)  Pa   (s1 - s3)/2
    mean_stress: np.ndarray          # (E,)  Pa   I1/3
    I1: np.ndarray                   # (E,)  Pa
    J2: np.ndarray                   # (E,)  Pa^2
    J3: np.ndarray                   # (E,)  Pa^3
    strain: np.ndarray               # (E,6)      tensorial, STRAIN_ORDER
    engineering_shear: np.ndarray    # (E,3)      gamma_xy, gamma_xz, gamma_yz
    principal_strain: np.ndarray     # (E,3)      e1 >= e2 >= e3
    max_shear_strain: np.ndarray     # (E,)       engineering, e1 - e3
    equivalent_strain: np.ndarray    # (E,)
    sigma_zz_ratio: np.ndarray       # (E,)       |szz| / von Mises (plane-stress check)


@dataclass
class Extreme:
    """Maximum (or minimum) of one quantity over all elements and available surfaces."""
    quantity: str
    value: float
    units: str
    element_index: int               # 0-based row = mesh element index (use for arrays/mesh.elems)
    ccx_element_id: int              # element_index + 1 (id used inside the CalculiX files)
    surface: str
    group: Optional[str] = None


@dataclass
class StressStrainResult:
    outer: SurfaceResult
    inner: Optional[SurfaceResult]
    wind_speed: float
    v_ref: float
    wind_scale: float                # (v/v_ref)^2
    strain_model: str
    material_source: str
    wind_label: str                  # 'actual' or the label on a placeholder/synthetic dataset
    extremes: Dict[str, Extreme]
    critical: Extreme                # governing element/surface by von Mises
    notes: List[str] = field(default_factory=list)
    units: Dict[str, str] = field(default_factory=lambda: dict(UNITS))
    n_elems: int = 0

    def surface(self, name: str) -> Optional[SurfaceResult]:
        if name not in SURFACES:
            raise ValueError(f"surface must be one of {SURFACES}")
        return getattr(self, name)

    def report(self) -> str:
        """Human-readable summary with units."""
        L = ["=" * 78, "STRESS & STRAIN  (sigma = sigma_G + (v/v_ref)^2 sigma_W, tension positive)", "=" * 78,
             f"elements            : {self.n_elems}",
             f"wind speed v        : {self.wind_speed:g} m/s    v_ref: "
             + ("n/a (zero placeholder, value irrelevant)" if self.wind_label.startswith("ZERO-WIND")
                else f"{self.v_ref:g} m/s")
             + f"    (v/v_ref)^2 = {self.wind_scale:g}",
             f"wind dataset        : {self.wind_label}",
             f"strain model        : {self.strain_model}",
             f"material source     : {self.material_source}",
             "stress axes         : element-local shell axes (axis 3 = normal)", "",
             f"{'quantity':<22}{'value':>14}  {'units':<7}{'elem idx':>9}{'ccx id':>8}  {'surface':<7} group"]
        for q, e in self.extremes.items():
            disp, u = e.value, e.units
            if e.units == "Pa":
                disp, u = e.value / 1e6, "MPa"
            L.append(f"{q:<22}{disp:>14.6g}  {u:<7}{e.element_index:>9d}{e.ccx_element_id:>8d}  {e.surface:<7} {e.group or ''}")
        c = self.critical
        L += ["", f"CRITICAL (max von Mises): element index {c.element_index} (CalculiX id {c.ccx_element_id}), "
                  f"{c.surface} surface{', group ' + c.group if c.group else ''}, {c.value / 1e6:.6g} MPa"]
        if self.notes:
            L += ["", "Notes:"] + [f"  - {n}" for n in self.notes]
        return "\n".join(L)

    def as_dict(self, surface: str = "outer") -> Dict[str, np.ndarray]:
        """Flat dict of arrays for one surface (handy for np.savez / DataFrame)."""
        s = self.surface(surface)
        if s is None:
            raise ValueError(f"no '{surface}' surface results (stress_inner missing in the inputs)")
        return {k: v for k, v in vars(s).items() if isinstance(v, np.ndarray)}


# ----------------------------------------------------------------------------
# Input handling
# ----------------------------------------------------------------------------
def load_solve_result(path: str) -> SolveResult:
    """Load a pickled contracts.SolveResult (e.g. out/res_G.pkl). contracts.py must be importable."""
    with open(path, "rb") as fh:
        obj = pickle.load(fh)
    if not isinstance(obj, SolveResult):
        raise TypeError(f"{path} does not contain a contracts.SolveResult (got {type(obj).__name__})")
    return obj


def load_mesh(path: str) -> Mesh:
    """Load a Mesh from out/full_mesh.pkl (Member 2 stores the tuple (Mesh, thickness))."""
    with open(path, "rb") as fh:
        obj = pickle.load(fh)
    if isinstance(obj, tuple):
        obj = obj[0]
    if not isinstance(obj, Mesh):
        raise TypeError(f"{path} does not contain a contracts.Mesh")
    return obj


def make_zero_wind_result(gravity_result: SolveResult, v_ref: float = 1.0) -> SolveResult:
    """Zero-valued wind SolveResult matching the gravity result's mesh, element order, component order
    and surface convention. Used until Member 2's wind solver is available. v_ref is arbitrary here
    (0 * anything = 0) but must be positive; it is NOT a physical wind speed."""
    g = gravity_result
    w = SolveResult(
        case="W",
        stress_outer=np.zeros_like(g.stress_outer),
        stress_inner=None if g.stress_inner is None else np.zeros_like(g.stress_inner),
        displacements=np.zeros_like(g.displacements),
        base_reaction_force=np.zeros(3), base_reaction_moment=np.zeros(3), applied_force=np.zeros(3),
        v_ref=float(v_ref))
    w.data_label = "ZERO-WIND PLACEHOLDER (no wind solve available yet)"
    return w


def validate_gravity_wind_pair(gravity: SolveResult, wind: SolveResult, mesh: Optional[Mesh] = None) -> None:
    """Refuse to combine results that cannot be on the same mesh / convention. Checks what the data allow:
    case labels, array shapes, finiteness, inner-surface availability and node/element counts. (The frame
    and element ORDER cannot be proven from SolveResult alone; counts + the same-mesh requirement are the
    available evidence, see module docstring.)"""
    for name, r in (("gravity_result", gravity), ("wind_result", wind)):
        if not isinstance(r, SolveResult):
            raise TypeError(f"{name} must be a contracts.SolveResult, got {type(r).__name__}")
        if not np.isfinite(r.stress_outer).all():
            raise ValueError(f"{name}.stress_outer contains NaN/inf")
        if r.stress_inner is not None and not np.isfinite(r.stress_inner).all():
            raise ValueError(f"{name}.stress_inner contains NaN/inf")
    if gravity.case != "G":
        raise ValueError(f"gravity_result.case must be 'G', got '{gravity.case}'")
    if wind.case != "W":
        raise ValueError(f"wind_result.case must be 'W', got '{wind.case}'")
    if gravity.stress_outer.shape != wind.stress_outer.shape:
        raise ValueError(f"element count / stress layout differ: gravity {gravity.stress_outer.shape} vs "
                         f"wind {wind.stress_outer.shape}")
    if (gravity.stress_inner is None) != (wind.stress_inner is None):
        raise ValueError("stress_inner is available in only one of the two results; cannot combine inner surface")
    if gravity.stress_inner is not None and gravity.stress_inner.shape != wind.stress_inner.shape:
        raise ValueError("stress_inner shapes differ between gravity and wind results")
    if gravity.displacements.shape != wind.displacements.shape:
        raise ValueError(f"node count differs (displacements {gravity.displacements.shape} vs "
                         f"{wind.displacements.shape}): results are not on the same mesh")
    if mesh is not None:
        if mesh.n_elems != gravity.stress_outer.shape[0]:
            raise ValueError(f"mesh has {mesh.n_elems} elements but the results have {gravity.stress_outer.shape[0]}")
        if mesh.n_nodes != gravity.displacements.shape[0]:
            raise ValueError(f"mesh has {mesh.n_nodes} nodes but the results have {gravity.displacements.shape[0]}")


# ----------------------------------------------------------------------------
# Core per-surface computation
# ----------------------------------------------------------------------------
def compute_surface_result(surface: str, sigma_g: np.ndarray, sigma_w: np.ndarray, wind_speed: float,
                           v_ref: float, material: MaterialProps, strain_model: str = "plane_stress") -> SurfaceResult:
    """Stress and strain quantities for one surface. The tensors are ADDED FIRST; every derived quantity
    (principal, von Mises, invariants, strains) is computed from the total tensor."""
    scale = wind_scale_factor(wind_speed, v_ref)
    sig_w_scaled = scale * np.asarray(sigma_w, float)
    sig = np.asarray(sigma_g, float) + sig_w_scaled                 # component-wise tensor sum

    pr, dirs = principal_decomposition(sig)
    I1, mean, J2, J3, vm = stress_invariants(sig)
    tau_max = 0.5 * (pr[:, 0] - pr[:, 2])

    # internal consistency: two independent von Mises routes (J2 vs principal values)
    vm_p = von_mises_from_principal(pr)
    if not np.allclose(vm, vm_p, rtol=1e-8, atol=1e-9 * max(float(np.max(vm)), 1.0)):
        raise ArithmeticError("internal check failed: von Mises from J2 and from principal stresses disagree")

    eps = strain_from_stress(sig, material.E, material.nu, strain_model)
    pe, _ = principal_decomposition(eps)
    gam = 2.0 * eps[:, [_IDX["xy"], _IDX["xz"], _IDX["yz"]]]
    eq = equivalent_strain_from_principal(pe, material.nu)
    szz_ratio = np.divide(np.abs(sig[:, _IDX["zz"]]), vm, out=np.zeros_like(vm), where=vm > 0)

    return SurfaceResult(surface, sig, np.asarray(sigma_g, float), sig_w_scaled, pr, dirs, vm, tau_max, mean,
                         I1, J2, J3, eps, gam, pe, pe[:, 0] - pe[:, 2], eq, szz_ratio)


def _extremes(res_by_surface: Dict[str, SurfaceResult], mesh: Optional[Mesh]) -> Dict[str, Extreme]:
    """Max (or min for compressive quantities) over elements and surfaces."""
    spec = [  # name, getter, units, 'max'|'min'
        ("von_mises", lambda s: s.von_mises, UNITS["von_mises"], "max"),
        ("sigma1_max (tension)", lambda s: s.principal[:, 0], "Pa", "max"),
        ("sigma3_min (compression)", lambda s: s.principal[:, 2], "Pa", "min"),
        ("max_shear", lambda s: s.max_shear, "Pa", "max"),
        ("equivalent_strain", lambda s: s.equivalent_strain, "-", "max"),
        ("max_shear_strain", lambda s: s.max_shear_strain, "-", "max"),
        ("eps1_max (tension)", lambda s: s.principal_strain[:, 0], "-", "max"),
        ("eps3_min (compression)", lambda s: s.principal_strain[:, 2], "-", "min"),
    ]
    out: Dict[str, Extreme] = {}
    for name, get, units, how in spec:
        best = None
        for sname, s in res_by_surface.items():
            a = get(s)
            i = int(np.argmax(a) if how == "max" else np.argmin(a))
            if best is None or (a[i] > best[0] if how == "max" else a[i] < best[0]):
                best = (float(a[i]), i, sname)
        v, i, sname = best
        grp = mesh.group_names[int(mesh.elem_group[i])] if mesh is not None else None
        out[name] = Extreme(name, v, units, i, i + 1, sname, grp)
    return out


# ----------------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------------
def calculate_stress_and_strain(gravity_result: SolveResult,
                                wind_result: SolveResult,
                                wind_speed: float,
                                material: Union[MaterialProps, Settings, dict, None],
                                *,
                                wind_v_ref: Optional[float] = None,
                                strain_model: str = "plane_stress",
                                mesh: Optional[Mesh] = None) -> StressStrainResult:
    """Combined gravity + wind stress and strain for every element, outer and inner surface separately.

    gravity_result : SolveResult, case 'G' (e.g. out/res_G.pkl)
    wind_result    : SolveResult, case 'W' at v_ref - actual, zero placeholder (make_zero_wind_result) or
                     synthetic test data. Its .v_ref is the reference speed of that solve.
    wind_speed     : v [m/s] to evaluate (>= 0). 0 -> gravity only through the SAME code path.
    material       : MaterialProps (per element, recommended: MaterialProps.from_inp), Settings or {'E','nu'}.
    wind_v_ref     : only needed if wind_result.v_ref is None; must agree with it when both are given.
    strain_model   : 'plane_stress' (default, shell) or 'full_3d'.
    mesh           : optional Mesh; adds group names and mesh-size validation.
    """
    validate_gravity_wind_pair(gravity_result, wind_result, mesh)
    n_elems = gravity_result.stress_outer.shape[0]
    mat = resolve_material(material, n_elems)

    v_ref = wind_result.v_ref
    if v_ref is None:
        v_ref = wind_v_ref
    elif wind_v_ref is not None and not np.isclose(v_ref, wind_v_ref):
        raise ValueError(f"wind_v_ref={wind_v_ref} contradicts wind_result.v_ref={v_ref}")
    if v_ref is None:
        raise ValueError("The reference wind speed is unknown: wind_result.v_ref is None and wind_v_ref was not given")
    scale = wind_scale_factor(wind_speed, v_ref)          # validates v and v_ref

    per_surface: Dict[str, SurfaceResult] = {}
    per_surface["outer"] = compute_surface_result("outer", gravity_result.stress_outer, wind_result.stress_outer,
                                                  wind_speed, v_ref, mat, strain_model)
    if gravity_result.stress_inner is not None:
        per_surface["inner"] = compute_surface_result("inner", gravity_result.stress_inner, wind_result.stress_inner,
                                                      wind_speed, v_ref, mat, strain_model)

    ext = _extremes(per_surface, mesh)
    label = getattr(wind_result, "data_label", None) or "actual wind SolveResult"
    notes = [
        "Stress components are in element-local shell axes; G and W are added component-wise, which is valid "
        "because both come from the same mesh/node order (same local axes). SolveResult carries no frame flag, "
        "so this is an assumption, not a verified property of the wind result.",
        "'outer' = +normal side of the element (outward on every group of the current mesh); 'inner' = the other side.",
        "Surface stresses are extrapolated values (ccx_reader.surface_stresses), not raw integration-point values.",
        f"Strain model '{strain_model}': " + (
            "sigma_zz is excluded from Hooke's law (shell plane-stress); eps_zz = -nu/E (sxx+syy)."
            if strain_model == "plane_stress" else "all six stress components used in Hooke's law."),
    ]
    if gravity_result.stress_inner is None:
        notes.append("stress_inner is None in the inputs: no inner-surface results.")
    if np.ptp(mat.E) > 0.5 * np.min(mat.E):
        notes.append(f"Young's modulus varies per element ({np.min(mat.E):.3g} .. {np.max(mat.E):.3g} Pa): strains "
                     "follow the model's equivalent-stiffness material (e.g. blades), not a real laminate.")
    flagged = max(int((s.sigma_zz_ratio > SIGMA_ZZ_FLAG_RATIO).sum()) for s in per_surface.values())
    if flagged:
        notes.append(f"{flagged} element(s) have |sigma_zz| > {SIGMA_ZZ_FLAG_RATIO:.0%} of von Mises on at least one "
                     "surface (plane-stress assumption questionable there); compare strain_model='full_3d'.")
    if label != "actual wind SolveResult":
        notes.insert(0, f"WIND DATA: {label}")
    if wind_speed > 0 and label.startswith("ZERO-WIND"):
        notes.append("wind_speed > 0 but the wind stress is a zero placeholder: the result is gravity only.")
    return StressStrainResult(per_surface["outer"], per_surface.get("inner"), float(wind_speed), float(v_ref), scale,
                              strain_model, mat.source, label, ext, ext["von_mises"], notes, dict(UNITS), n_elems)


# ----------------------------------------------------------------------------
# Optional: element-local axes -> global axes (validated on the tower only)
# ----------------------------------------------------------------------------
def element_local_axes(mesh: Mesh):
    """Local shell axes of every element expressed in global coordinates.
    Rule (CalculiX default for shells): e3 = element normal (corner-node order, right-hand rule);
    e1 = global x projected onto the element surface; e2 = e3 x e1.
    VALIDATED on the tower groups only (rotating the actual gravity stress with this rule gives
    global szz = -11.77 MPa vs. -11.96 MPa hand calculation). Elements whose normal is nearly parallel to
    global x (|n.x| > 0.99) are returned in `ambiguous`; the rule is not verified there.
    Returns (axes (E,3,3) with ROWS e1,e2,e3 in global coordinates, ambiguous (E,) bool)."""
    from solver.ccx_reader import element_normals          # reuse Member 2's normal computation
    n = element_normals(mesh)
    ex = np.array([1.0, 0.0, 0.0])
    e1 = ex - (n @ ex)[:, None] * n
    nrm = np.linalg.norm(e1, axis=1, keepdims=True)
    ambiguous = (np.abs(n @ ex) > 0.99) | (nrm[:, 0] < 1e-8)
    e1 = e1 / np.maximum(nrm, 1e-300)
    e2 = np.cross(n, e1)
    return np.stack([e1, e2, n], axis=1), ambiguous


def stress_to_global(s6: np.ndarray, axes: np.ndarray) -> np.ndarray:
    """Rotate (E,6) local stress to global axes: T_g = Q^T T_l Q, Q rows = local axes. Returns (E,3,3)."""
    return np.einsum("eai,eab,ebj->eij", axes, stress_to_tensor(s6), axes)


def principal_directions_global(dirs_local: np.ndarray, axes: np.ndarray) -> np.ndarray:
    """(E,3,3) local principal directions (columns) -> global components (columns)."""
    return np.einsum("eak,eai->eki", axes, dirs_local)


# ----------------------------------------------------------------------------
# Command line
# ----------------------------------------------------------------------------
def _main():
    import argparse
    ap = argparse.ArgumentParser(description="Combined gravity + wind stress and strain report.")
    ap.add_argument("--gravity", default="out/res_G.pkl", help="pickled SolveResult, case G")
    ap.add_argument("--inp", default="out/G.inp", help="CalculiX input of the G run (per-element E, nu, thickness)")
    ap.add_argument("--mesh", default="out/full_mesh.pkl", help="optional mesh pickle (group names)")
    ap.add_argument("--wind", default="zero", help="'zero', 'synthetic', or a pickled SolveResult (case W)")
    ap.add_argument("--speed", type=float, default=0.0, help="wind speed v in m/s")
    ap.add_argument("--strain-model", default="plane_stress", choices=STRAIN_MODELS)
    ap.add_argument("--save-npz", default=None, help="write the outer/inner arrays to this .npz")
    a = ap.parse_args()

    g = load_solve_result(a.gravity)
    n = g.stress_outer.shape[0]
    mesh = load_mesh(a.mesh) if a.mesh and os.path.isfile(a.mesh) else None
    mat = MaterialProps.from_inp(a.inp, n)
    if a.wind == "zero":
        w = make_zero_wind_result(g)
    elif a.wind == "synthetic":
        from synthetic_wind_data import make_synthetic_wind_result
        w = make_synthetic_wind_result(g)
    else:
        w = load_solve_result(a.wind)
    res = calculate_stress_and_strain(g, w, a.speed, mat, strain_model=a.strain_model, mesh=mesh)
    print(res.report())
    if a.save_npz:
        arrays = {f"{s}_{k}": v for s in SURFACES if res.surface(s) is not None for k, v in res.as_dict(s).items()}
        np.savez_compressed(a.save_npz, **arrays)
        print(f"\nsaved {len(arrays)} arrays to {a.save_npz}")


if __name__ == "__main__":
    _main()