# Wind Turbine Structural Analyser

Python shell-FEA workflow for a parked wind turbine using Gmsh and CalculiX.
The backend is driven by the existing geometry generator, mesh generator,
CalculiX writer/runner/reader and stress/strain post-processor.

## Prerequisites (Windows)

1. Python 3.10+ (use the Python version supported by your Gmsh wheel).
2. CalculiX `ccx.exe` installed and accessible. The executable path can be passed
   with `--ccx` or configured through the `CCX_PATH` environment variable.
3. Install Python packages from the repository root:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

   For tests: `pip install -r requirements-dev.txt`.

## Run the complete backend analysis

The reference wind speed is fixed at **50 m/s**. The operating wind speed is
selected independently and is applied in post-processing using
`(V / 50)^2`. Wind direction is a compass bearing **FROM**: 0° North, 90° East,
180° South, 270° West.

```powershell
$env:CCX_PATH = "C:\Path\To\CalculiX\ccx.exe"
python run_analysis.py --wind-speed 25 --wind-direction 90
```

Example with a modified geometry JSON and mesh controls:

```powershell
python run_analysis.py `
  --config data/default_turbine.json `
  --mesh-size 0.8 `
  --mesh-base-size 0.5 `
  --mesh-refine-distance 6 `
  --mesh-order 2 `
  --wind-speed 35 `
  --wind-direction 180
```

Geometry controls are the parameters already supported by
`data/default_turbine.json`: tower section elevations/diameters/thicknesses,
nacelle dimensions and position, hub diameter/overhang/thickness, and blade
count, azimuth, thickness and radial chord/thickness/twist stations. Keep the
configuration physically valid and ensure the component intersections remain
valid when editing it.

## Incremental reuse rules

- Geometry or mesh setting changes invalidate and rerun gravity and wind.
- Wind direction changes rerun the reference-wind CalculiX analysis; gravity is
  reused if its geometry/mesh provenance still matches.
- Operating wind speed changes only rerun combined post-processing; the 50 m/s
  reference wind solution is reused.
- Result metadata records geometry and ordered-mesh SHA-256 fingerprints,
  conditions, solver identity, material/settings information and UTC timestamp.
- Results are reused only when their provenance matches the requested case.
  Missing or stale metadata causes a rerun rather than silent reuse.

## Outputs

The output directory (default `out/`) contains the existing CalculiX input,
`.dat`/`.frd` solver files, mesh/result pickles, combined
`stress_strain_results.npz`, and `failure_assessment.json`. The two Excel
exports can still be generated with `StressAndStrain.py`.

Interactive PyVista deformation view:

```powershell
python example_deformation.py
```

It validates gravity, wind and combined-result metadata and exact mesh
connectivity/order before displaying. The maximum principal stress contour uses
`sigma_1` (the first principal-value column, sorted descending).

## Tests

```powershell
pytest -q tests/test_analysis_workflow.py
pytest -q test_stress_and_strain.py
```

The complete CalculiX end-to-end workflow requires a working Gmsh installation
and `ccx.exe`. A solver run is not considered passed unless CalculiX actually
executes and produces valid `.dat` results.

## Engineering scope and limitations

- The solver model remains the existing parked-rotor shell model; it does not
  include rotor thrust or operating aerodynamic control loads.
- Wind speed scaling assumes the wind pressure/load is proportional to `V^2`
  and the structure remains in linear response. It is not valid for nonlinear
  contact, geometric/material nonlinearity, or speed-dependent aerodynamic
  coefficients.
- Stress components are the project's element-local shell components in
  `(xx, yy, zz, xy, xz, yz)` order. Component-wise superposition requires
  identical meshes and local axes; the workflow checks mesh identity/order.
- Strain exports distinguish tensorial shear strain from engineering shear
  strain. The default shell plane-stress strain model remains unchanged.
- The included failure assessment is a von-Mises elastic-yield screening check
  with a uniform user-selected yield strength. It is not a shell-buckling,
  fatigue, fracture, composite, or design-code assessment. The default 345 MPa
  is a project placeholder and must be replaced with the actual material data
  before engineering decisions are made.
