"""Turns a failure_assessment.json (written by failure_analysis.assess_npz)
into Details-panel rows. No GUI dependency here either — just formatting.
"""
from pathlib import Path

from failure_analysis import load_assessment


def _mpa(pa):
    return f"{pa / 1e6:.1f} MPa" if pa is not None else "N/A"


def _speed(v):
    return f"{v:.1f} m/s" if v is not None else "Not reached"


def load_result(out_dir):
    path = Path(out_dir) / "failure_assessment.json"
    if not path.is_file():
        return None
    return load_assessment(path)


def build_result_rows(result):
    fs = result.get("failure_speed") or {}
    buck = result.get("buckling") or {}

    rows = [
        ("Overall status", result.get("overall_status", result["status"])),
        ("Operating wind speed", f"{result['operating_wind_speed_m_s']:g} m/s"),
        ("Max von Mises", _mpa(result["maximum_von_mises_pa"])),
        ("Utilisation", f"{result['utilization']:.3f}"),
        ("Allowable stress", _mpa(result["allowable_stress_pa"])),
        ("Governing element", f"#{result['governing_calculix_element_id_1_based']}"),
        ("Governing group", result.get("governing_group") or "N/A"),
        ("Governing surface", result.get("governing_surface", "N/A")),
        ("First-yield speed", _speed(fs.get("v_fail_m_s"))),
        ("Allowable speed (SF applied)", _speed(fs.get("v_allow_m_s"))),
    ]

    if buck.get("performed"):
        rows.append(("Tower buckling", f"{buck['status']} (util. {buck['utilization']:.3f})"))
    else:
        rows.append(("Tower buckling", f"Not checked ({buck.get('reason', 'n/a')})"))

    rows.append((
        "Note",
        "Elastic first-yield screening only — not a final design check."
    ))
    return rows