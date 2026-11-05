# Repository audit and implementation report

## Architecture and dependency map

```text
run_analysis.py
  ├─ run_gravity.py
  │    ├─ geometry/default_generator.py ── geometry/blade.py
  │    ├─ solver/mesh.py
  │    ├─ solver/loads.py (element orientation)
  │    ├─ solver/bcs.py + solver/links.py
  │    ├─ solver/ccx_writer.py
  │    ├─ solver/ccx_runner.py
  │    └─ solver/ccx_reader.py ── contracts.SolveResult
  ├─ run_winds.py (reuses exact gravity mesh when orchestrated)
  │    ├─ solver/loads.py (wind_dir_vector / wind_loadset)
  │    ├─ solver/bcs.py + solver/links.py
  │    ├─ solver/ccx_writer.py / ccx_runner.py / ccx_reader.py
  │    └─ contracts.LoadSet / SolveResult
  ├─ StressAndStrain.py
  │    ├─ contracts.py (Mesh / Settings / SolveResult)
  │    ├─ solver/ccx_reader.py (stress convention / local axes helpers)
  │    └─ out/*.pkl + G.inp + mesh pickles -> combined arrays + metadata NPZ
  └─ failure_analysis.py (von-Mises elastic-yield screening)

example_deformation.py
  ├─ contracts.py + analysis_metadata.py (provenance checks)
  ├─ visualization/mesh_builder.py
  ├─ visualization/deformation.py
  └─ visualization/contour_plots.py

Geometry configuration: data/default_turbine.json
Material/section data: data/nrel5mw_blade_ei.csv and the generated CalculiX G.inp
Persistent solver outputs: out/; tabular exports: results/
```

## Repository inventory reviewed

- Root Python execution and diagnostics: `run_gravity.py`, `run_winds.py`, `run_tower.py`, `StressAndStrain.py`, `stressandstrainbefore.py`, `synthetic_wind_data.py`, `example_deformation.py`, `example_stress_and_strain.py`, `example_visualization.py`, `inspect_results.py`, `check_degenerate.py`, `check_mesh.py`, `compare_meshes.py`, `testgeometry.py`, `test_element_selection.py`, `test_stress_and_strain.py`, `verify_com_loads.py`.
- Geometry: `geometry/__init__.py`, `geometry/blade.py`, `geometry/default_generator.py`, `geometry/hollow_tower.py`, `geometry/hollow_tower_backup.py`.
- Solver: `solver/__init__.py`, `solver/bcs.py`, `solver/ccx_reader.py`, `solver/ccx_runner.py`, `solver/ccx_writer.py`, `solver/geom.py`, `solver/links.py`, `solver/loads.py`, `solver/mesh.py`, and the added test-only `solver/testmesh.py`.
- Visualization: `visualization/contour_plots.py`, `visualization/deformation.py`, `visualization/element_details.py`, `visualization/mesh_builder.py`, `visualization/mohr_circle.py`.
- Tests/probes: `tests/coupling_probe.py`, `tests/plate_calibration.py`, `tests/rigid_link_probe.py`, `tests/run_cylinder_g.py`, `tests/test_bcs.py`, `tests/test_links.py`, and the added `tests/test_analysis_workflow.py` / `tests/conftest.py`; tower-only pretests were inventoried.
- Config/data/result assets: both JSON geometry configurations, NREL blade EI CSV, existing `.inp/.dat/.frd` solver files, pickle/NPZ result files, Excel exports, `.msh`/`.brep` geometry assets, comparison report and golden test data.

The original `out/`, `results/`, mesh, BREP and test-data files were retained. The existing `stressandstrainbefore.py` historical snapshot was retained unchanged.

## Changes made

1. **Contracts and provenance**
   - Added backward-compatible `SolveResult.metadata` with dictionary validation.
   - Added `analysis_metadata.py`: canonical geometry SHA-256, ordered mesh SHA-256 (coordinates, connectivity, group assignments/names and node sets), input-file SHA-256, metadata schema, UTC timestamp and atomic pickle writes.
   - Gravity and wind results receive metadata only after the CalculiX runner and result reader succeed.
   - Stress/strain NPZ and Excel Notes carry the operating speed, reference speed, direction, geometry/mesh fingerprints and solver/material/settings provenance.

2. **Stress/strain compatibility**
   - Retained the existing `(xx, yy, zz, xy, xz, yz)` stress/tensorial-strain order and engineering shear conversion.
   - Added rejection of conflicting gravity/wind geometry or mesh fingerprints and non-finite displacement data.
   - Added validation that the wind result's stored reference speed agrees with its metadata.
   - Fixed the CLI's access to a nonexistent `res.wind_direction`: direction is passed explicitly or read from saved wind metadata and stored on `StressStrainResult`.
   - Added `--wind-direction` and made `--save-npz` actually select the export path.

3. **Geometry and meshing inputs**
   - Both solver runners now accept `TURBINE_CONFIG`, `TURBINE_OUT`, `TURBINE_MESH_SIZE`, `TURBINE_MESH_BASE_SIZE`, `TURBINE_MESH_REFINE_DISTANCE`, and `TURBINE_MESH_ORDER` environment settings.
   - Tower-top group selection is based on the number of configured tower sections, not `Tower_4`.
   - Hub/nacelle rigid-link patches, tower base radius checks, hub reference-node position and hub-height wind reference are derived from the geometry JSON rather than fixed default-turbine coordinates.
   - The wind runner can consume the exact saved gravity mesh, preventing a second Gmsh pass from changing element/node order.
   - The CalculiX writer requires quadratic S6 shell elements, so mesh order remains fixed at 2; the orchestrator does not offer an unsupported linear order.

4. **Incremental orchestration**
   - Added `run_analysis.py`. Geometry/mesh/material/solver/input fingerprints gate reuse.
   - Geometry or mesh changes invalidate gravity and wind. Direction changes invalidate only wind. Operating speed changes only rerun combination/failure post-processing.
   - Wind reference speed is fixed at 50 m/s in the workflow.
   - A failed subprocess stops downstream processing. Old files are not treated as successful new results because metadata and input hashes must match.

5. **Visualization consistency**
   - Reworked `example_deformation.py` into a validation-first loader plus the existing PyVista display.
   - It verifies exact mesh identity/order, result metadata, direction/reference-speed agreement, stress element count and displacement dimensions before plotting.
   - Combined displacement is `u_G + (V/50)^2 u_W`.
   - Corrected the displayed maximum principal stress statistic to use the first stored principal value (`sigma_1`, descending order); the contour helper sorts its own values before selection and remains unchanged.
   - The original wireframe checkbox, axes, grid, camera and principal-stress contour are retained.

6. **Failure screening and documentation**
   - Added `failure_analysis.py`, a transparent von-Mises elastic-yield utilization screen using an explicit uniform yield-strength input and safety factor.
   - Added `requirements.txt`, `requirements-dev.txt`, and updated Windows run instructions in `README.md`.

## Validation performed in this environment

- `python -m compileall -q .`: passed.
- `pytest -q tests/test_analysis_workflow.py tests/test_links.py test_stress_and_strain.py -k 'not ElementExportRealData and not ElementExportEdgeCases'`: **52 passed, 18 deselected**.
- `python run_analysis.py --help`: passed.
- `python StressAndStrain.py --help`: passed.
- Core imports for `contracts`, `StressAndStrain`, `analysis_metadata`, `failure_analysis`, and `run_analysis`: passed.

## Not validated here / known pre-existing issues

- Gmsh is not installed in this execution environment; geometry generation and remeshing could not be executed.
- CalculiX (`ccx`/`ccx.exe`) is not installed or discoverable; no new CalculiX solve was executed. Therefore no end-to-end structural solver run is claimed as passed.
- PyVista is not installed; the interactive window could not be launched.
- A pre-existing Excel export regression test `TestElementExportRealData.test05_07_stress_values_match_calculation_and_are_MPa` expects the golden maximum von-Mises value 1884.33 MPa, but the repository's supplied `out/res_G.pkl` and current stress calculation produce about 850.799 MPa at that location. This fixture/golden mismatch is present in the supplied repository data and was not altered by this work. The stress formula and export checks preceding that hard-coded benchmark passed.
- `tests/test_links.py` originally imported a missing `solver.testmesh` module; a deterministic test-only quadratic-cylinder fixture was added, after which all four link tests passed.
- Some legacy diagnostic scripts are interactive or require Gmsh/PyVista/Windows Excel and were not executed.

## Physical-model limitations that remain explicit

- The existing model is the parked-rotor shell model and does not add rotor thrust.
- The `V^2` scaling assumes aerodynamic drag pressure scales with speed squared and linear structural response; it is not a substitute for nonlinear or speed-dependent aeroelastic analysis.
- Stress components are in the project's element-local shell axes. Component-wise superposition is only defensible on the exact same mesh/local frames; this workflow checks mesh identity and reuses the gravity mesh for wind.
- The current failure check is not a buckling, fatigue, fracture, composite or design-code assessment. The default 345 MPa yield strength is explicitly a placeholder and must be replaced with actual material data.
