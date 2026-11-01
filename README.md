# wind-turbine-structural-analyser
A Python-based wind turbine structural analysis tool using shell FEA, CalculiX, and a graphical user interface.
## Known limitation: STEP upload grouping

Automatic component grouping for uploaded STEP files uses heuristic rules based on part height and distance from the tower axis. The current implementation has been tested on the supported demonstration assembly but has not been validated for arbitrary turbine geometries.

When the project's own turbine was exported and uploaded, the geometry was imported at the expected size, but the grouping process failed to identify the blades. The current rules are therefore not reliable for every turbine configuration.

The default turbine is unaffected because its component groups are assigned during construction. Supporting arbitrary uploaded turbine geometries would require improved grouping logic and additional validation.

Other limitations include unfused solids that do not share mesh nodes and uploaded rotor orientations that are reported but not automatically corrected.
