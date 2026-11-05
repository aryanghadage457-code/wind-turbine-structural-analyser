
import pickle
import numpy as np

# Load gravity mesh and results
with open("out/full_mesh.pkl", "rb") as f:
    gmesh, gthickness = pickle.load(f)

with open("out/res_G.pkl", "rb") as f:
    res_G = pickle.load(f)

# Load wind mesh and results
with open("out/wind_mesh.pkl", "rb") as f:
    wmesh = pickle.load(f)

with open("out/res_W.pkl", "rb") as f:
    res_W = pickle.load(f)

# Compare meshes
with open("comparison_report.txt", "w") as f:
    def report(*args):
        print(*args, file=f)

    report("=== MESH COMPARISON ===")
    report("Gravity nodes:", gmesh.nodes.shape)
    report("Wind nodes:", wmesh.nodes.shape)
    report("Gravity elements:", gmesh.elems.shape)
    report("Wind elements:", wmesh.elems.shape)

    report("Node coordinates identical:",
           np.array_equal(gmesh.nodes, wmesh.nodes))
    report("Element connectivity identical:",
           np.array_equal(gmesh.elems, wmesh.elems))
    report("Element groups identical:",
           np.array_equal(gmesh.elem_group, wmesh.elem_group))
    report("Group names identical:",
           gmesh.group_names == wmesh.group_names)

    report("\n=== RESULT SHAPES ===")
    for name, result in [("Gravity", res_G), ("Wind", res_W)]:
        report(name)
        report("Outer stress:", result.stress_outer.shape)
        report("Inner stress:",
               None if result.stress_inner is None
               else result.stress_inner.shape)
        report("Displacements:", result.displacements.shape)
        report("Case:", result.case)
        report("Reference wind speed:", result.v_ref)

print("Comparison saved to comparison_report.txt")
