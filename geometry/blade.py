"""Blade generator (Member 1). Simplified lofted blade, outer surface only.
Blade axis is built pointing +Z from the hub centre, then rotated about the
rotor axis (+Y) to make the copies. Units: metres, angles in degrees.
"""
import math
import gmsh

occ = gmsh.model.occ


def _section_wire(cx, cy, cz, chord, thick, twist_deg):
    """Closed ellipse (circle if chord == thick) in a horizontal plane."""
    a = math.radians(twist_deg)
    if abs(chord - thick) < 1e-9:
        c = occ.addCircle(cx, cy, cz, chord / 2, zAxis=[0, 0, 1])
    else:
        c = occ.addEllipse(cx, cy, cz, chord / 2, thick / 2,
                           zAxis=[0, 0, 1], xAxis=[math.cos(a), math.sin(a), 0])
    return occ.addWire([c]), c


def build_blades(blade, hub_center):
    """Returns list of surface tags for all blades (blade k = list k)."""
    hx, hy, hz = hub_center
    st = blade["stations"]
    wires = []
    for s in st:
        w, _ = _section_wire(hx, hy, hz + s["r"], s["chord"], s["thick"], s["twist"])
        wires.append(w)
    loft = occ.addThruSections(wires, makeSolid=False, makeRuled=True)
    # tip cap (closed tip)
    last = st[-1]
    tip_c = _section_wire(hx, hy, hz + last["r"], last["chord"], last["thick"], last["twist"])
    cap = occ.addPlaneSurface([occ.addCurveLoop([tip_c[1]])])
    base = [d for d in loft if d[0] == 2] + [(2, cap)]
    occ.synchronize()

    n = int(blade.get("count", 3))
    az = blade.get("azimuth_deg", 0.0)
    blades = []
    for k in range(n):
        if k == 0:
            dts = base
        else:
            dts = occ.copy(base)
        occ.rotate(dts, hx, hy, hz, 0, 1, 0, math.radians(az + 360.0 * k / n))
        blades.append([t for _, t in dts])
    occ.synchronize()
    return blades