"""Blade generator (Member 1).

Simplified lofted blade, outer surface only.
Blade axis is built pointing +Z from the hub centre,
then rotated about the rotor axis (+Y) to make copies.

Units: metres.
Angles: degrees.
"""

import math
import gmsh


def _section_wire(cx, cy, cz, chord, thick, twist_deg):
    """Create a closed elliptical blade section."""

    occ = gmsh.model.occ

    angle = math.radians(twist_deg)

    if abs(chord - thick) < 1e-9:

        curve = occ.addCircle(
            cx, cy, cz,
            chord / 2,
            zAxis=[0, 0, 1]
        )

    else:

        curve = occ.addEllipse(
            cx, cy, cz,
            chord / 2,
            thick / 2,
            zAxis=[0, 0, 1],
            xAxis=[
                math.cos(angle),
                math.sin(angle),
                0
            ]
        )

    wire = occ.addWire([curve])

    return wire, curve


def build_blades(blade, hub_center):
    """Generate all blade surfaces.

    Returns:
        List of lists containing surface tags.
        blades[0] = Blade 1 surface tags
        blades[1] = Blade 2 surface tags
        blades[2] = Blade 3 surface tags
    """

    occ = gmsh.model.occ

    hx, hy, hz = hub_center

    stations = blade["stations"]

    if len(stations) < 2:
        raise ValueError(
            "At least two blade stations are required."
        )

    blade_count = int(blade.get("count", 3))
    azimuth = float(blade.get("azimuth_deg", 0.0))

    if blade_count < 1:
        raise ValueError(
            "Blade count must be at least one."
        )

    wires = []
    curves = []

    # Create blade cross-sections.
    for station in stations:

        radius = float(station["r"])
        chord = float(station["chord"])
        thickness = float(station["thick"])
        twist = float(station["twist"])

        if chord <= 0 or thickness <= 0:
            raise ValueError(
                "Blade chord and thickness must be positive."
            )

        wire, curve = _section_wire(
            hx,
            hy,
            hz + radius,
            chord,
            thickness,
            twist
        )

        wires.append(wire)
        curves.append(curve)

    # Generate the blade loft.
    loft = occ.addThruSections(
        wires,
        makeSolid=False,
        makeRuled=True
    )

    # Create the tip cap using the existing final section curve.
    tip_curve = curves[-1]

    tip_loop = occ.addCurveLoop(
        [tip_curve]
    )

    tip_surface = occ.addPlaneSurface(
        [tip_loop]
    )

    # Keep lofted surfaces and the tip cap.
    base_surfaces = [
        (dim, tag)
        for dim, tag in loft
        if dim == 2
    ]

    base_surfaces.append(
        (2, tip_surface)
    )

    occ.synchronize()

    blades = []

    # Create and position the blade copies.
    for k in range(blade_count):

        if k == 0:

            current_surfaces = base_surfaces

        else:

            current_surfaces = occ.copy(
                base_surfaces
            )

        angle = math.radians(
            azimuth + 360.0 * k / blade_count
        )

        occ.rotate(
            current_surfaces,
            hx, hy, hz,
            0, 1, 0,
            angle
        )

        blades.append([
            tag
            for dim, tag in current_surfaces
            if dim == 2
        ])

    occ.synchronize()

    return blades