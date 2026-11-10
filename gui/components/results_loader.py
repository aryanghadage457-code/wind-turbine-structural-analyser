"""Turns a failure_assessment.json (written by failure_analysis.assess_npz)
into Details-panel rows. No GUI dependency here either — just formatting.
"""
from pathlib import Path

from failure_analysis import load_assessment


def _mpa(pa):
    return f"{pa / 1e6:.1f} MPa" if pa is not None else "N/A"


def _speed(v):
    if v is None:
        return "Not reached"
    if v <= 0.0:
        return "0.0 m/s — exceeded under gravity alone"
    return f"{v:.1f} m/s"

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
        ("Failure note", fs.get("message", "")),
    ]



    if buck.get("performed"):
        rows.append(("Tower buckling", f"{buck['status']} (util. {buck['utilization']:.3f})"))
        rows.append(("Buckling first-yield speed", _speed(buck.get("v_fail_m_s"))))
        rows.append(("Buckling allowable speed (SF applied)", _speed(buck.get("v_allow_m_s"))))
        rows.append(("Buckling governing group", buck.get("governing_group") or "N/A"))

        stress_allow = fs.get("v_allow_m_s")
        buck_allow = buck.get("v_allow_m_s")
        if stress_allow is not None and buck_allow is not None:
            if buck_allow < stress_allow:
                rows.append((
                    "Governing failure mode",
                    f"Buckling ({buck_allow:.1f} m/s) governs before stress ({stress_allow:.1f} m/s)."
                ))
            else:
                rows.append((
                    "Governing failure mode",
                    f"Stress ({stress_allow:.1f} m/s) governs before buckling ({buck_allow:.1f} m/s)."
                ))
    else:
        rows.append(("Tower buckling", f"Not checked ({buck.get('reason', 'n/a')})"))

    rows.append((
        "Note",
        "Elastic first-yield screening only — not a final design check."
    ))
    return rows