"""patch_blade_mass.py - adds NREL blade MASS-distribution matching to solver/ccx_writer.py.

    python patch_blade_mass.py solver/ccx_writer.py          (makes solver/ccx_writer.py.bak first)

What it adds (all optional; defaults keep today's behaviour):
  write_inp(..., blade_ei_file="data/NRELOffshrBsline5MW_Blade.dat", blade_mass_match=True)
  * load_blade_table(): reads 3-col CSV (BlFract,Flp,Edg), 4-col CSV (+BMassDen as 4th column),
    ElastoDyn v1.00 5-col rows (BlFract,StrcTwst,BMassDen,FlpStff,EdgStff) and FAST v7 >=6-col rows
  * per blade region: wall thickness t = BMassDen*AdjBlMs / (rho_blade * perimeter) so the mass per metre
    follows NREL (blade density 2050 kg/m3 untouched); E_eq is then recomputed with that thickness, so the
    flapwise EI match is kept
  * element_thickness(): per-element wall thickness (use it for the expected weight in run_gravity.py)
  * <job>_blade_ei.csv gets 4 extra columns at the END (t_wall_m, mass_per_len_target/model, perimeter)
"""
import re, shutil, sys

path = sys.argv[1] if len(sys.argv) > 1 else "solver/ccx_writer.py"
src = open(path, newline="").read()
nl = "\r\n" if "\r\n" in src else "\n"
fix = lambda s: s.replace("\n", nl)


def sub(old, new, count=1):
    global src
    old, new = fix(old), fix(new)
    assert src.count(old) == count, f"anchor found {src.count(old)}x (want {count}): {old[:70]!r}"
    src = src.replace(old, new)


# 1) write_inp signature: two new optional keywords at the end
i = src.index("def write_inp(")
depth, j = 0, src.index("(", i)
for k in range(j, len(src)):
    depth += src[k] == "("; depth -= src[k] == ")"
    if depth == 0:
        close = k; break
head = src[:close].rstrip()
src = head + "," + fix("\n    blade_mass_match=False,\n    blade_mass_factor=1.04536\n") + src[close:]

# 2) the call
sub("blade_plan = _plan_blade_regions(mesh, thickness, settings, blade_ei_file, blade_match, blade_regions)",
    "blade_plan = _plan_blade_regions(mesh, thickness, settings, blade_ei_file, blade_match, blade_regions,\n"
    "                                     blade_mass_match, blade_mass_factor)")

# 3) loader
a = src.index("def load_blade_ei(path):"); b = src.index("def _plan_blade_regions(")
src = src[:a] + fix('''BLADE_RHO = 2050.0     # equivalent blade density (kg/m3), the same value write_inp uses; do not change


def load_blade_table(path):
    """Read the NREL blade table -> dict(x, flp, edg, mass); mass is None if the file has no BMassDen.
    Row formats (numbers only; text lines are skipped):
      3 cols  BlFract, FlpStff, EdgStff                         (your CSV)
      4 cols  BlFract, FlpStff, EdgStff, BMassDen               (CSV with mass)
      5 cols  BlFract, StrcTwst, BMassDen, FlpStff, EdgStff     (ElastoDyn v1.00 blade file)
      >=6     BlFract, AeroCent, StrcTwst, BMassDen, FlpStff, EdgStff, ...   (FAST v7)
    Units: N*m^2 and kg/m. The ElastoDyn file's AdjBlMs factor is NOT read: pass blade_mass_factor."""
    rows = []
    with open(path) as fh:
        for line in fh:
            try:
                v = [float(t) for t in line.replace(",", " ").split()]
            except ValueError:
                continue
            n = len(v)
            if n == 3:
                rows.append((v[0], v[1], v[2], None))
            elif n == 4:
                rows.append((v[0], v[1], v[2], v[3]))
            elif n == 5:
                rows.append((v[0], v[3], v[4], v[2]))
            elif n >= 6:
                rows.append((v[0], v[4], v[5], v[3]))
    if len(rows) < 3:
        raise ValueError(f"{path}: found fewer than 3 table rows (BlFract, FlpStff, EdgStff)")
    rows.sort(key=lambda r: r[0])
    x = np.array([r[0] for r in rows]); flp = np.array([r[1] for r in rows]); edg = np.array([r[2] for r in rows])
    mass = np.array([r[3] for r in rows]) if all(r[3] is not None for r in rows) else None
    if x[0] < 0 or x[-1] > 1.0001 or np.any(np.diff(x) <= 0):
        raise ValueError(f"{path}: BlFract must increase strictly within 0..1")
    if np.any(flp <= 0) or np.any(edg <= 0) or max(flp.max(), edg.max()) < 1e7:
        raise ValueError(f"{path}: stiffness must be positive and in N*m^2 (root value is of order 1e10)")
    if mass is not None and np.any(mass <= 0):
        raise ValueError(f"{path}: BMassDen must be positive (kg/m)")
    return dict(x=x, flp=flp, edg=edg, mass=mass)


def load_blade_ei(path):
    """Read the NREL blade EI table -> (blfract, flp, edg), N*m^2 (kept for older callers)."""
    t = load_blade_table(path)
    return t["x"], t["flp"], t["edg"]


''') + src[b:]

# 4) planner
sub("def _plan_blade_regions(mesh, thickness, settings, ei_file, match, n_reg):",
    "def _plan_blade_regions(mesh, thickness, settings, ei_file, match, n_reg,\n"
    "                        mass_match=False, blade_mass_factor=1.04536, verbose=True):")
sub("    xb, flp, edg = load_blade_ei(ei_file)\n",
    "    tab = load_blade_table(ei_file)\n    xb, flp, edg, mass = tab[\"x\"], tab[\"flp\"], tab[\"edg\"], tab[\"mass\"]\n"
    "    if mass_match and mass is None:\n"
    "        raise ValueError(f\"{ei_file} has no BMassDen column, so blade_mass_match cannot be used\")\n")
sub("            sel = wall & (ov > 0)\n            i_min = i_max = E = np.nan\n            if sel.sum() >= 6:\n"
    "                w = t * area[sel] * ov[sel] / (d_xi * span)\n",
    "            sel = wall & (ov > 0)\n            i_min = i_max = E = np.nan\n"
    "            perim = float((area[sel] * ov[sel]).sum() / (d_xi * span)) if sel.any() else np.nan\n"
    "            t_r, m_t = t, np.nan\n"
    "            if mass_match and sel.sum() >= 6:      # wall thickness that gives NREL's mass per metre\n"
    "                m_t = blade_mass_factor * float(np.mean(np.interp(xs, xb, mass)))\n"
    "                t_r = m_t / (BLADE_RHO * perim)\n"
    "                if not (0.002 <= t_r <= 0.1):\n"
    "                    warnings.warn(f\"{name}_R{r + 1:02d}: required wall thickness {1000 * t_r:.1f} mm is outside 2..100 mm\")\n"
    "            elif mass_match:\n"
    "                warnings.warn(f\"{name}_R{r + 1:02d}: too few elements, uniform thickness kept\")\n"
    "            if sel.sum() >= 6:\n"
    "                w = t_r * area[sel] * ov[sel] / (d_xi * span)\n")
sub("                             i_min=i_min, i_max=i_max, E=E))",
    "                             i_min=i_min, i_max=i_max, E=E, t=t_r, m_t=m_t, perim=perim))")
sub("        plan[\"groups\"].add(name)\n",
    "        if mass_match and verbose:\n            _print_blade_mass(name, rows, xb, mass, blade_mass_factor, span)\n"
    "        plan[\"groups\"].add(name)\n")

# 5) sections use the region thickness
sub("L += [f\"*SHELL SECTION, ELSET={q['set']}, MATERIAL={q['set']}\", f\"{thickness[gname]:.10g}\"]",
    "L += [f\"*SHELL SECTION, ELSET={q['set']}, MATERIAL={q['set']}\", f\"{q.get('t', thickness[gname]):.10g}\"]")

# 6) report + helpers (replace the whole report function)
a = src.index("def _write_blade_report(path, plan):"); b = src.index("# ====", a)
src = src[:a] + fix('''def _print_blade_mass(name, rows, xb, mass, f, span):
    """One line per blade: model wall mass and centre of mass against the NREL table (x factor)."""
    if any(not np.isfinite(q["perim"]) for q in rows):
        return
    dx = rows[0]["xi_hi"] - rows[0]["xi_lo"]
    m = np.array([BLADE_RHO * q["t"] * q["perim"] for q in rows]); xm = np.array([(q["xi_lo"] + q["xi_hi"]) / 2 for q in rows])
    xs = np.linspace(0.0, 1.0, 2001); mt = f * np.interp(xs, xb, mass)
    trap = getattr(np, "trapezoid", None) or np.trapz          # NumPy 2.x / 1.x
    print(f"{name}: wall mass {(m * dx * span).sum():.0f} kg (NREL table x {f}: {trap(mt, xs) * span:.0f} kg), "
          f"centre of mass {(m * xm).sum() / m.sum() * span:.2f} m from the root "
          f"(NREL {trap(mt * xs, xs) / trap(mt, xs) * span:.2f} m)")


def element_thickness(mesh, thickness, settings, **plan_kwargs):
    """(E,) wall thickness of every element, including the blade-region thicknesses. Use it for the expected
    weight:  t_el = element_thickness(mesh, thickness, S, blade_ei_file=..., blade_mass_match=True)
    plan_kwargs: blade_ei_file, blade_match, blade_regions, blade_mass_match, blade_mass_factor."""
    t_el = np.array([thickness[mesh.group_names[g]] for g in mesh.elem_group], dtype=float)
    plan = _plan_blade_regions(mesh, thickness, settings,
                               plan_kwargs.get("blade_ei_file", DEFAULT_BLADE_EI_FILE),
                               plan_kwargs.get("blade_match", "flap"), plan_kwargs.get("blade_regions", 12),
                               plan_kwargs.get("blade_mass_match", False),
                               plan_kwargs.get("blade_mass_factor", 1.04536), verbose=False)
    if plan:
        for q in plan["regions"]:
            t_el[np.asarray(q["ids"]) - 1] = q["t"]
    return t_el


def _write_blade_report(path, plan):
    """<job>_blade_ei.csv: target vs model EI per region, for the validation table."""
    out = os.path.splitext(path)[0] + "_blade_ei.csv"
    with open(out, "w") as fh:
        fh.write("blade,region,xi_lo,xi_hi,n_elems,E_eq_Pa,I_min_m4,I_max_m4,"
                 "FlpStff_target,FlpStff_model,EdgStff_target,EdgStff_model,flp_ratio,edg_ratio,"
                 "t_wall_m,mass_per_len_target,mass_per_len_model,perimeter_m\\n")
        for q in plan["regions"]:
            t_r = q.get("t", float("nan")); pe = q.get("perim", float("nan"))
            fh.write(f"{q['blade']},{q['region']},{q['xi_lo']:.4f},{q['xi_hi']:.4f},{len(q['ids'])},"
                     f"{q['E']:.6g},{q['i_min']:.6g},{q['i_max']:.6g},{q['flp_t']:.6g},{q['flp_m']:.6g},"
                     f"{q['edg_t']:.6g},{q['edg_m']:.6g},{q['flp_m'] / q['flp_t']:.4f},"
                     f"{q['edg_m'] / q['edg_t']:.4f},{t_r:.6g},{q.get('m_t', float('nan')):.6g},"
                     f"{BLADE_RHO * t_r * pe:.6g},{pe:.6g}\\n")
    return out


''') + src[b:]

shutil.copy(path, path + ".bak")
open(path, "w", newline="").write(src)
print("patched", path, "(backup:", path + ".bak)")