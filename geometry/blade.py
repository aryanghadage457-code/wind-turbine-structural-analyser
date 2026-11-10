"""Blade generator (Member 1). Simplified lofted blade, outer surface only.
Blade axis is built pointing +Z from the hub centre, then rotated about the
rotor axis (+Y) to make the copies. Units: metres, angles in degrees.

Optional leading-edge alignment (JSON keys in the "blade" block):
  leading_edge_align    0.0 = sections centred on the blade axis (old shape),
                        1.0 = straight leading edge, curved trailing edge.
  leading_edge_start_r  radius (m) from where the alignment starts; stations
                        inside it (root, cylinder) are not moved.
  leading_edge_sign     +1: leading edge on the +chord-direction side,
                        -1: on the other side (mirrors the shape sideways).
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


def _chord_shifts(blade):
    """Sideways shift (m, along each section's chord direction) per station.
    Keeps the leading edge on a straight line from the start station outward."""
    st = blade["stations"]
    shifts = [0.0] * len(st)
    align = float(blade.get("leading_edge_align", 0.0))
    if align < 0.0 or align > 1.0:
        raise ValueError("leading_edge_align must be between 0 and 1")
    if align == 0.0:
        return shifts
    sign = 1 if float(blade.get("leading_edge_sign", 1)) >= 0 else -1
    r0 = float(blade.get("leading_edge_start_r", 8.3333))
    i0 = next((i for i, s in enumerate(st) if s["r"] >= r0 - 1e-9), None)
    if i0 is None:
        return shifts
    ref = st[i0]["chord"]
    for i in range(i0, len(st)):
        shifts[i] = -sign * align * (st[i]["chord"] - ref) / 2.0
    return shifts


def build_blades(blade, hub_center):
    """Returns list of surface tags for all blades (blade k = list k)."""
    hx, hy, hz = hub_center
    st = blade["stations"]
    shifts = _chord_shifts(blade)

    def centre(i):
        a = math.radians(st[i]["twist"])
        return hx + shifts[i] * math.cos(a), hy + shifts[i] * math.sin(a), hz + st[i]["r"]

    wires = []
    for i, s in enumerate(st):
        cx, cy, cz = centre(i)
        w, _ = _section_wire(cx, cy, cz, s["chord"], s["thick"], s["twist"])
        wires.append(w)
    loft = occ.addThruSections(wires, makeSolid=False, makeRuled=True)
    # tip cap (closed tip)
    last = st[-1]
    cx, cy, cz = centre(len(st) - 1)
    tip_c = _section_wire(cx, cy, cz, last["chord"], last["thick"], last["twist"])
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