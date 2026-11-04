"""User-editable turbine parameters (Member 1 -> Member 4).

Plain Python, no gmsh. The numbers in data/default_turbine.json stay the source
of truth: every default below is READ from that file, and apply_to_config()
returns the file's values unchanged when the user has not changed anything.

Typical use (Member 4):
    import parameters as P
    spec   = P.PARAMETERS                      # name -> label, unit, default, min, max, ...
    values = P.default_values()                # dict name -> number
    errors, warnings = P.validate(values)      # lists of text for the UI
    config = P.apply_to_config(values)         # dict in the format build_default() reads
"""
import copy
import json
import math
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).parent / "data" / "default_turbine.json"

# name: (label, unit, group, min, max, help)   -- defaults come from the JSON
_SPEC = {
    "tower_height":   ("Tower height", "m", "Tower", 30.0, 150.0,
                       "Height of the tower top above the ground."),
    "tower_base_d":   ("Tower base diameter", "m", "Tower", 2.0, 10.0,
                       "Outer diameter at the bottom."),
    "tower_top_d":    ("Tower top diameter", "m", "Tower", 1.5, 8.0,
                       "Outer diameter at the top. Must not exceed the base diameter."),
    "tower_base_t":   ("Tower wall thickness, bottom section", "m", "Tower", 0.010, 0.060,
                       "Shell thickness of the lowest tower section."),
    "tower_top_t":    ("Tower wall thickness, top section", "m", "Tower", 0.008, 0.060,
                       "Shell thickness of the highest tower section. Sections in between are interpolated."),
    "nacelle_length": ("Nacelle length", "m", "Nacelle", 6.0, 25.0,
                       "Length along the rotor axis."),
    "nacelle_width":  ("Nacelle width", "m", "Nacelle", 3.0, 10.0,
                       "Side-to-side size. Must be wider than the tower top."),
    "nacelle_height": ("Nacelle height", "m", "Nacelle", 3.0, 10.0,
                       "Vertical size. The hub centre sits at half this height."),
    "hub_diameter":   ("Hub diameter", "m", "Rotor", 2.8, 5.0,
                       "Diameter of the spherical hub."),
    "overhang":       ("Rotor overhang", "m", "Rotor", 2.5, 10.0,
                       "Distance from the tower axis to the hub centre along the rotor axis."),
    "blade_length":   ("Blade length", "m", "Rotor", 20.0, 100.0,
                       "Length from the hub surface to the blade tip."),
    "yaw_deg":        ("Yaw angle", "deg", "Rotor", -180.0, 180.0,
                       "Rotation of nacelle, hub and blades about the tower axis."),
}
FIXED = {"blade_count": 3}          # not editable in version 1


def load_config(path=None):
    with open(path or DEFAULT_CONFIG_PATH) as f:
        return json.load(f)


def _internal(cfg):
    """Fixed relations that keep the junctions valid (not editable)."""
    nac, hub = cfg["nacelle"], cfg["hub"]
    st = cfg["blade"]["stations"]
    return {
        "front_offset": hub["overhang"] - nac["y_front"],      # hub centre to nacelle front face
        "root_radius": st[0]["chord"] / 2,                     # simplified round root
        "root_half_thick": st[0]["thick"] / 2,
    }


def values_from_config(cfg):
    """Read the editable values out of a config dict."""
    s = cfg["tower"]["sections"]
    nac, hub, bl = cfg["nacelle"], cfg["hub"], cfg["blade"]
    return {
        "tower_height": s[-1]["z1"],
        "tower_base_d": s[0]["d0"],
        "tower_top_d": s[-1]["d1"],
        "tower_base_t": s[0]["t"],
        "tower_top_t": s[-1]["t"],
        "nacelle_length": nac["y_front"] - nac["y_rear"],
        "nacelle_width": nac["width"],
        "nacelle_height": nac["height"],
        "hub_diameter": hub["diameter"],
        "overhang": hub["overhang"],
        "blade_length": bl["stations"][-1]["r"] - hub["diameter"] / 2,
        "yaw_deg": cfg.get("yaw_deg", 0.0),
    }


def build_parameters(cfg=None):
    cfg = cfg or load_config()
    vals = values_from_config(cfg)
    out = {}
    for name, (label, unit, group, lo, hi, hlp) in _SPEC.items():
        out[name] = {"label": label, "unit": unit, "group": group,
                     "default": round(vals[name], 6), "min": lo, "max": hi, "help": hlp}
    return out


PARAMETERS = build_parameters()


def default_values(cfg=None):
    return {k: v["default"] for k, v in build_parameters(cfg).items()}


# ------------------------------------------------------------------ validation
def validate(values, base_cfg=None):
    """Return (errors, warnings). Errors must block the build; warnings are advice."""
    base = base_cfg or load_config()
    spec = build_parameters(base)
    fixed = _internal(base)
    v, errs, warns = dict(values), [], []

    for name, sp in spec.items():                       # 1. every value present and in range
        if name not in v or not isinstance(v[name], (int, float)) or math.isnan(v[name]):
            errs.append(f"{sp['label']}: a number is required.")
            continue
        if not sp["min"] <= v[name] <= sp["max"]:
            errs.append(f"{sp['label']}: {v[name]} {sp['unit']} is outside "
                        f"{sp['min']} to {sp['max']} {sp['unit']}.")
    if errs:
        return errs, warns                              # relations below need valid numbers

    if v["tower_top_d"] > v["tower_base_d"]:
        errs.append("Tower top diameter must not be larger than the base diameter.")
    for key, d in (("tower_base_t", v["tower_base_d"]), ("tower_top_t", v["tower_top_d"])):
        if v[key] >= d / 2:
            errs.append(f"{spec[key]['label']} must be smaller than the tower radius.")
        elif v[key] > d / 20:
            warns.append(f"{spec[key]['label']}: thickness above 1/20 of the diameter "
                         f"weakens the thin-shell assumption.")
    if v["tower_top_t"] > v["tower_base_t"]:
        warns.append("Top wall is thicker than the bottom wall, which is unusual.")

    y_front = v["overhang"] - fixed["front_offset"]
    y_rear = y_front - v["nacelle_length"]
    r_top = v["tower_top_d"] / 2
    rnd = base["nacelle"].get("round", 0.0)               # rounded edges along the rotor axis
    if r_top > v["nacelle_width"] / 2 - 0.2:
        errs.append("Nacelle is too narrow: the tower top must fit inside its floor (0.2 m margin).")
    elif rnd > 0 and r_top + rnd + 0.1 > v["nacelle_width"] / 2:
        errs.append("Nacelle is too narrow for its rounded edges: the tower top must fit on the "
                    "flat part of the floor.")
    if rnd > 0 and rnd > min(v["nacelle_width"], v["nacelle_height"]) / 2 - 0.1:
        errs.append("Nacelle is too small for its rounded edges.")
    if r_top > -y_rear - 0.2 or r_top > y_front - 0.2:
        errs.append("Nacelle floor does not cover the tower top: lengthen the nacelle or "
                    "increase the overhang.")

    R = v["hub_diameter"] / 2
    off = fixed["front_offset"]
    if off >= 0.95 * R:
        errs.append("Hub is too small for this overhang: the hub must cross the nacelle front face.")
    elif math.sqrt(R * R - off * off) > min(v["nacelle_width"], v["nacelle_height"]) / 2 - 0.2:
        errs.append("Hub meets the nacelle front face too close to its edge: enlarge the "
                    "nacelle or reduce the hub.")
    min_R = 1.53 * fixed["root_radius"]     # round roots 120 degrees apart must not overlap
    if R < min_R:
        errs.append(f"Hub is too small: blade roots would overlap. Minimum hub diameter "
                    f"{2 * min_R:.2f} m.")
    if fixed["root_half_thick"] > off - 0.05:
        errs.append("Blade root would cut into the nacelle front face.")

    hub_z = v["tower_height"] + v["nacelle_height"] / 2
    tip_r = R + v["blade_length"]
    if hub_z - 0.5 * tip_r <= 0:
        errs.append("Blade tip would be below the ground (lowest blade at 120 degrees).")
    elif hub_z - tip_r <= 0:
        warns.append("A blade pointing straight down would reach the ground.")
    return errs, warns


# --------------------------------------------------------- values -> config dict
def _remap(old, old_a, old_b, new_a, new_b):
    """Affine map: old_a->new_a, old_b->new_b. Keeps the shape of the original taper."""
    if abs(old_b - old_a) < 1e-12:
        return new_a
    return new_a + (old - old_a) * (new_b - new_a) / (old_b - old_a)


def apply_to_config(values, base_cfg=None):
    """Return a NEW config dict for build_default(). Unchanged inputs give the base
    file's numbers back exactly. Raises ValueError if validate() finds errors."""
    base = base_cfg or load_config()
    errs, _ = validate(values, base)
    if errs:
        raise ValueError("; ".join(errs))
    cfg, v, v0 = copy.deepcopy(base), values, values_from_config(base)
    fixed = _internal(base)

    secs = cfg["tower"]["sections"]                       # tower: same shape, new size
    if any(v[k] != v0[k] for k in ("tower_height", "tower_base_d", "tower_top_d",
                                   "tower_base_t", "tower_top_t")):
        H0 = secs[-1]["z1"]
        n = len(secs)
        d_a0, d_b0 = secs[0]["d0"], secs[-1]["d1"]
        for i, s in enumerate(secs):
            s["z0"] = round(secs[i]["z0"] * v["tower_height"] / H0, 6)
            s["z1"] = round(secs[i]["z1"] * v["tower_height"] / H0, 6)
            s["d0"] = round(_remap(base["tower"]["sections"][i]["d0"], d_a0, d_b0,
                                   v["tower_base_d"], v["tower_top_d"]), 6)
            s["d1"] = round(_remap(base["tower"]["sections"][i]["d1"], d_a0, d_b0,
                                   v["tower_base_d"], v["tower_top_d"]), 6)
            s["t"] = round(v["tower_base_t"] + (v["tower_top_t"] - v["tower_base_t"])
                           * (i / (n - 1) if n > 1 else 0), 6)

    nac, hub = cfg["nacelle"], cfg["hub"]
    hub["diameter"], hub["overhang"] = v["hub_diameter"], v["overhang"]
    nac["width"], nac["height"] = v["nacelle_width"], v["nacelle_height"]
    nac["y_front"] = round(v["overhang"] - fixed["front_offset"], 6)
    nac["y_rear"] = round(nac["y_front"] - v["nacelle_length"], 6)

    st = cfg["blade"]["stations"]                          # blade: root stations 0,1 fixed
    new_tip = v["hub_diameter"] / 2 + v["blade_length"]
    old_tip = base["blade"]["stations"][-1]["r"]
    if abs(new_tip - old_tip) > 1e-9 and len(st) > 2:
        r_ref = base["blade"]["stations"][1]["r"]
        for i in range(2, len(st)):
            st[i]["r"] = round(_remap(base["blade"]["stations"][i]["r"], r_ref, old_tip,
                                      r_ref, new_tip), 4)
    cfg["blade"]["count"] = FIXED["blade_count"]
    cfg["yaw_deg"] = v["yaw_deg"]
    return cfg


# ----------------------------------------------------------------------- self test
if __name__ == "__main__":
    base = load_config()
    d = default_values()
    ok = True

    def check(name, cond):
        global ok
        ok &= bool(cond)
        print(("PASS  " if cond else "FAIL  ") + name)

    e, w = validate(d)
    check("defaults are valid, no errors", not e)
    check("defaults give no warnings", not w)
    cfg = apply_to_config(d)
    same = {k: cfg[k] for k in base} == base
    check("unchanged inputs reproduce the JSON exactly (yaw key aside)",
          same and cfg.get("yaw_deg") == 0.0)
    cases = {
        "negative thickness": {"tower_base_t": -0.01},
        "top diameter > base": {"tower_top_d": 7.0},
        "nacelle too narrow for tower top": {"nacelle_width": 3.0, "tower_top_d": 3.87 + 0.0},
        "hub too small": {"hub_diameter": 2.0},
        "tower height out of range": {"tower_height": 500},
        "tip below ground": {"tower_height": 30.0, "blade_length": 100.0},
    }
    for label, change in cases.items():
        e, _ = validate({**d, **change})
        check(f"rejects: {label}", len(e) > 0)
    if base["nacelle"].get("round", 0) > 0:
        e, _ = validate({**d, "nacelle_width": 4.4})
        check("rejects: nacelle too narrow for its rounded floor", len(e) > 0)
        check("rounding value is kept by apply_to_config",
              apply_to_config(d)["nacelle"]["round"] == base["nacelle"]["round"])
    big = apply_to_config({**d, "tower_height": 100.0, "blade_length": 70.0, "yaw_deg": 20.0})
    s = big["tower"]["sections"]
    check("height 100: top of last section is 100", abs(s[-1]["z1"] - 100.0) < 1e-6)
    check("height 100: sections touch each other",
          all(abs(s[i]["z1"] - s[i + 1]["z0"]) < 1e-6 and abs(s[i]["d1"] - s[i + 1]["d0"]) < 1e-6
              for i in range(len(s) - 1)))
    check("blade 70: tip station at hub radius + 70",
          abs(big["blade"]["stations"][-1]["r"] - 71.5) < 1e-3)
    check("blade 70: root stations unchanged",
          big["blade"]["stations"][:2] == base["blade"]["stations"][:2])
    check("yaw stored", big["yaw_deg"] == 20.0)
    print("\nALL PASS" if ok else "\nSOME FAILED")