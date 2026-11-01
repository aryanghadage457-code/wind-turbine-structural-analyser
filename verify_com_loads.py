
import numpy as np
from pathlib import Path

from geometry.default_generator import load_params
from solver.ccx_writer import default_ref_nodes, _centroid_weights

INP_FILE = Path("out/G.inp")
G = 9.81
TOL = 1e-5


# ==================================================
# 1. READ NODES AND ELEMENT GROUPS
# ==================================================

nodes = {}
elements_by_group = {}

reading_nodes = False
current_elset = None

with INP_FILE.open() as f:
    for raw in f:
        line = raw.strip()

        if not line or line.startswith("**"):
            continue

        upper = line.upper()

        # IMPORTANT:
        # Match only *NODE, not *NODE PRINT.
        if upper == "*NODE" or upper.startswith("*NODE,"):
            reading_nodes = True
            current_elset = None
            continue

        if upper.startswith("*ELEMENT"):
            reading_nodes = False
            current_elset = None

            for item in upper.split(","):
                item = item.strip()
                if item.startswith("ELSET="):
                    current_elset = item.split("=", 1)[1]

            if current_elset:
                elements_by_group.setdefault(current_elset, [])

            continue

        if line.startswith("*"):
            reading_nodes = False
            current_elset = None
            continue

        values = [v.strip() for v in line.split(",")]

        if reading_nodes:
            node_id = int(values[0])
            nodes[node_id] = np.array(
                [float(v) for v in values[1:4]]
            )

        elif current_elset:
            element_nodes = [
                int(v) for v in values[1:] if v
            ]
            elements_by_group[current_elset].append(element_nodes)


print("Nodes read:", len(nodes))
print("Element groups:", list(elements_by_group.keys()))


# ==================================================
# 2. READ ACTUAL CLOAD FROM G.INP
# ==================================================

actual_cload = {}
inside_cload = False

with INP_FILE.open() as f:
    for raw in f:
        line = raw.strip()

        if not line or line.startswith("**"):
            continue

        upper = line.upper()

        if upper.startswith("*CLOAD"):
            inside_cload = True
            continue

        # Stop at the next keyword.
        if inside_cload and line.startswith("*"):
            break

        if not inside_cload:
            continue

        values = [v.strip() for v in line.split(",")]

        if len(values) < 3:
            raise ValueError(f"Invalid CLOAD entry: {line}")

        node_id = int(values[0])
        direction = int(values[1])
        force = float(values[2])

        if node_id not in nodes:
            raise ValueError(
                f"CLOAD refers to missing node {node_id}"
            )

        if direction not in (1, 2, 3):
            raise ValueError(
                f"Invalid force direction: {line}"
            )

        actual_cload.setdefault(
            node_id, np.zeros(3)
        )[direction - 1] += force


# ==================================================
# 3. RECONSTRUCT EXPECTED NACELLE AND HUB LOADS
# ==================================================

params = load_params("data/default_turbine.json")
ref_nodes = default_ref_nodes(params)

expected_cload = {}

for ref in ref_nodes:

    name = ref["name"]
    group = ref["group"].upper()
    mass = float(ref["mass_kg"])
    point = np.array(ref["point"], dtype=float)

    if group not in elements_by_group:
        raise ValueError(
            f"Element group not found: {group}"
        )

    group_node_ids = sorted({
        node_id
        for element in elements_by_group[group]
        for node_id in element
    })

    X = np.array([
        nodes[n] for n in group_node_ids
    ])

    # Reconstruct the distribution using the same
    # centroid-weighting function as ccx_writer.py.
    weights = _centroid_weights(X, point)

    total_force = np.array([
        0.0, 0.0, -mass * G
    ])

    nodal_forces = weights[:, None] * total_force

    for node_id, force in zip(
        group_node_ids, nodal_forces
    ):
        expected_cload.setdefault(
            node_id, np.zeros(3)
        )

        expected_cload[node_id] += force

    # Resultant force and moment.
    resultant = np.sum(nodal_forces, axis=0)

    moment = np.sum(
        np.cross(X, nodal_forces),
        axis=0
    )

    target_moment = np.cross(
        point, total_force
    )

    print(f"\n========== {name} ==========")
    print("Target COM:", point)
    print("Expected force:", total_force)
    print("Calculated resultant:", resultant)
    print("Distributed-load moment:", moment)
    print("Target COM moment:", target_moment)
    print("Moment error:", moment - target_moment)


# ==================================================
# 4. COMPARE EXPECTED AND ACTUAL NODAL FORCES
# ==================================================

all_ids = set(expected_cload) | set(actual_cload)

max_error = max(
    (
        np.linalg.norm(
            expected_cload.get(n, np.zeros(3))
            - actual_cload.get(n, np.zeros(3))
        )
        for n in all_ids
    ),
    default=0.0
)

actual_total = sum(
    actual_cload.values(),
    np.zeros(3)
)

expected_total = sum(
    expected_cload.values(),
    np.zeros(3)
)

print("\n========== ACTUAL INP VERIFICATION ==========")

print("Actual total CLOAD:", actual_total)
print("Expected total CLOAD:", expected_total)

print("Maximum nodal force difference:", max_error, "N")


# ==================================================
# 5. FINAL RESULT
# ==================================================

if max_error < TOL:
    print("\nPASS: Actual CLOAD matches reconstructed distribution.")
    print("Nacelle and hub nodal forces verified.")
else:
    print("\nCHECK: Actual and reconstructed nodal forces differ.")
    print("Investigate the difference before accepting the result.")
