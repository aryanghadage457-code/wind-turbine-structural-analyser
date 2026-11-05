"""Transparent elastic-yield screening for combined shell stress results.

This is a first-yield / von-Mises check only. It is not a buckling, fatigue,
composite failure, or code-compliance assessment.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np


def assess_npz(npz_path, *, yield_strength_pa=345e6, safety_factor=1.5, output_path=None):
    if not np.isfinite(yield_strength_pa) or yield_strength_pa <= 0:
        raise ValueError("yield_strength_pa must be finite and positive")
    if not np.isfinite(safety_factor) or safety_factor < 1:
        raise ValueError("safety_factor must be finite and >= 1")
    with np.load(npz_path, allow_pickle=False) as data:
        candidates = []
        for surface in ("outer", "inner"):
            key = f"{surface}_von_mises"
            if key in data.files:
                arr = np.asarray(data[key], dtype=float)
                if arr.ndim != 1 or not np.isfinite(arr).all():
                    raise ValueError(f"{key} must be a finite 1-D element array")
                if arr.size:
                    i = int(np.argmax(arr))
                    candidates.append((float(arr[i]), i, surface))
        if not candidates:
            raise ValueError("No von Mises stress arrays found in stress/strain NPZ")
        stress, element_index, surface = max(candidates)
        metadata = json.loads(str(data["metadata_json"].item())) if "metadata_json" in data.files else {}
    utilization = stress / (yield_strength_pa / safety_factor)
    result = {
        "method": "elastic von-Mises yield screening",
        "yield_strength_pa": float(yield_strength_pa),
        "safety_factor": float(safety_factor),
        "allowable_stress_pa": float(yield_strength_pa / safety_factor),
        "maximum_von_mises_pa": stress,
        "utilization": float(utilization),
        "governing_element_index_0_based": element_index,
        "governing_calculix_element_id_1_based": element_index + 1,
        "governing_surface": surface,
        "status": "EXCEEDS_ALLOWABLE" if utilization > 1 else "WITHIN_ALLOWABLE",
        "metadata": metadata,
        "limitations": [
            "Uniform yield strength is an explicit screening input, not recovered per element from the current .inp.",
            "No shell buckling, fatigue, fracture, composite failure, or design-code checks are included.",
        ],
    }
    if output_path:
        path = Path(output_path); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
