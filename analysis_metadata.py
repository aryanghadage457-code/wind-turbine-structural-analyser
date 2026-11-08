"""Stable provenance and compatibility fingerprints for turbine FEA results.

Fingerprints describe the exact input geometry and ordered mesh. They are deliberately
separate from solver result arrays so older SolveResult pickles remain readable.
"""
from __future__ import annotations
import hashlib, json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

SCHEMA_VERSION = 1

def geometry_fingerprint(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(canonical).hexdigest()

def mesh_fingerprint(mesh):
    h = hashlib.sha256()
    for arr in (np.asarray(mesh.nodes, dtype="<f8"), np.asarray(mesh.elems, dtype="<i8"),
                np.asarray(mesh.elem_group, dtype="<i8")):
        a = np.ascontiguousarray(arr)
        h.update(str(a.shape).encode("ascii")); h.update(a.tobytes())
    h.update(json.dumps(list(mesh.group_names), separators=(",", ":")).encode())
    for name in sorted(getattr(mesh, "node_sets", {})):
        h.update(name.encode("utf-8"))
        a = np.ascontiguousarray(np.asarray(mesh.node_sets[name], dtype="<i8"))
        h.update(str(a.shape).encode("ascii")); h.update(a.tobytes())
    return h.hexdigest()

def file_fingerprint(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def make_metadata(*, case, geometry_hash, mesh_hash, wind_speed=None, v_ref=None,
                  wind_direction_deg=None, solver=None, material=None, settings=None):
    return {
        "schema_version": SCHEMA_VERSION, "case": str(case),
        "operating_wind_speed_m_s": None if wind_speed is None else float(wind_speed),
        "reference_wind_speed_m_s": None if v_ref is None else float(v_ref),
        "wind_direction_deg": None if wind_direction_deg is None else float(wind_direction_deg) % 360.0,
        "geometry_fingerprint": str(geometry_hash), "mesh_fingerprint": str(mesh_hash),
        "analysis_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "solver": solver or {}, "material": material or {}, "settings": settings or {},
    }

def atomic_pickle(path, obj):
    import pickle
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f: pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise

def metadata_matches(meta, *, case, geometry_hash, mesh_hash, wind_direction_deg=None, v_ref=None):
    if not isinstance(meta, dict): return False
    if meta.get("schema_version") != SCHEMA_VERSION or meta.get("case") != case: return False
    if meta.get("geometry_fingerprint") != geometry_hash or meta.get("mesh_fingerprint") != mesh_hash: return False
    if wind_direction_deg is not None:
        got = meta.get("wind_direction_deg")
        if got is None or not np.isclose(float(got) % 360.0, float(wind_direction_deg) % 360.0): return False
    if v_ref is not None:
        got = meta.get("reference_wind_speed_m_s")
        if got is None or not np.isclose(float(got), float(v_ref)): return False
    return True
