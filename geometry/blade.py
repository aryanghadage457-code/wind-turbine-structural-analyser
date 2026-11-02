
"""Blade generator (Member 1). Simplified lofted blade, outer surface only.
Blade axis points +Z from the hub centre, then rotates about +Y.
Units: metres, angles in degrees.
"""

import math
import gmsh

occ = gmsh.model.occ


def _section_wire(cx, cy, cz, chord, thick, twist_deg):
    """Create a closed elliptical blade section."""

    a = math.radians(twist_deg)

    if abs(chord - thick) < 1e-9:
        curve = occ.addCircle(
            cx, cy, cz, chord / 2,
            zAxis=[0, 0, 1]
        )
    else:
        curve = occ.addEllipse(
            cx, cy, cz,
            chord / 2,
            thick / 2,
            zAxis=[0, 0, 1],
            xAxis=[math.cos(a), math.sin(a), 0]
        )

    wire = occ.addWire([curve])
    return wire


def build_blades(blade, hub_center):
    """Return surface tags for each blade."""

    hx, hy, hz = hub_center
    stations = blade["stations"]

    # 1. Create one wire for each blade cross-section.
    wires = []

    for section in stations:
        wire = _section_wire(
            hx,
            hy,
            hz + section["r"],
            section["chord"],
            section["thick"],
            section["twist"]
        )
        wires.append(wire)

    # 2. Create the lofted outer blade surfaces.
    loft = occ.addThruSections(
        wires,
        makeSolid=False,
        makeRuled=True
    )

    # 3. Create the tip cap using the existing final station wire.
    # This avoids creating a second, coincident ellipse.
    tip_cap = occ.addPlaneSurface([wires[-1]])

    # Collect the loft surfaces and tip cap.
    base = [
        item for item in loft
        if item[0] == 2
    ]

    base.append((2, tip_cap))

    occ.synchronize()

    # 4. Create and rotate the blade copies.
    count = int(blade.get("count", 3))
    azimuth = blade.get("azimuth_deg", 0.0)

    blades = []

    for k in range(count):

        if k == 0:
            copied_surfaces = base
        else:
            copied_surfaces = occ.copy(base)

        angle = math.radians(
            azimuth + 360.0 * k / count
        )

        occ.rotate(
            copied_surfaces,
            hx, hy, hz,
            0, 1, 0,
            angle
        )

        blades.append([
            tag
            for dim, tag in copied_surfaces
            if dim == 2
        ])

    occ.synchronize()

    return blades