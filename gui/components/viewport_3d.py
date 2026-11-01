"""Interactive Gmsh/PyVista viewport for the built-in wind turbine model.

The mesh generated here is for visualization only. It is not the final
quadratic shell mesh used by the CalculiX analysis workflow.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import gmsh
import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from geometry.default_generator import build_default


COMPONENT_COLORS = {
    "Tower": "#718096",
    "Nacelle": "#D6DEE8",
    "Hub": "#00B8D9",
    "Blade 1": "#E6A23C",
    "Blade 2": "#69B578",
    "Blade 3": "#A78BFA",
}

COMPONENT_TO_GROUPS = {
    "Tower": ["Tower_1", "Tower_2", "Tower_3", "Tower_4", "Tower_5", "Tower_6", "Tower_7", "Tower_8"],
    "Nacelle": ["Nacelle"],
    "Hub": ["Hub"],
    "Blade 1": ["Blade_1"],
    "Blade 2": ["Blade_2"],
    "Blade 3": ["Blade_3"],
}


class TurbineViewport(QWidget):
    """Qt widget that builds and displays the built-in turbine geometry."""

    status_message = Signal(str)
    component_selected = Signal(str)

    def __init__(self, project_data: dict | None = None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.plotter = None
        self.actors: dict[str, object] = {}
        self.component_meshes: dict[str, pv.DataSet] = {}
        self.geometry_loaded = False
        self.loading = False

        self.setMinimumSize(400, 350)
        self.setStyleSheet("background-color: #17191D;")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.message_label = QLabel("Open Geometry to generate the turbine model.")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet(
            "color: #A5ABB4; background-color: #17191D; padding: 12px;"
        )
        self.layout.addWidget(self.message_label)

    def ensure_geometry_loaded(self):
        """Generate geometry once, when the Geometry page is first opened."""
        if self.geometry_loaded or self.loading:
            return
        self.loading = True
        self.message_label.setText("Generating turbine geometry... please wait.")
        self.status_message.emit("Starting built-in turbine geometry generation...")

        try:
            params = self._load_parameters()
            self._build_view(params)
            self.geometry_loaded = True
            self.status_message.emit("3D turbine visualization generated successfully.")
        except Exception as exc:
            self.message_label.setText(
                "Could not generate the 3D model.\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                "Check the console for details, then reopen the Geometry page to retry."
            )
            self.status_message.emit(f"Geometry generation failed: {type(exc).__name__}: {exc}")
            raise
        finally:
            self.loading = False

    def _load_parameters(self) -> dict:
        project_path = self.project_data.get("project_path")
        model_config_path = None
        if project_path:
            model_config_path = Path(project_path) / "config" / "model_config.json"

        model_config = {}
        if model_config_path and model_config_path.exists():
            with model_config_path.open("r", encoding="utf-8") as file:
                model_config = json.load(file)

        model_source = model_config.get(
            "model_source", self.project_data.get("model_source", "builtin")
        )
        if model_source == "step":
            raise NotImplementedError(
                "STEP viewport loading has not been integrated yet. "
                "The built-in turbine generator is ready; STEP support will be added separately."
            )

        root = Path(__file__).resolve().parents[2]
        json_path = root / "data" / "default_turbine.json"
        # The supplied JSON may contain non-breaking spaces. Normalize those
        # whitespace characters before parsing; no model values are changed.
        raw = json_path.read_text(encoding="utf-8").replace("\u00a0", " ")
        params = json.loads(raw)

        dimensions = model_config.get("dimensions") or self.project_data.get("dimensions")
        if dimensions:
            self._apply_dialog_dimensions(params, dimensions)
        return params

    @staticmethod
    def _apply_dialog_dimensions(params: dict, dimensions: dict):
        """Map the configuration-dialog dimensions onto the default model.

        blade_thickness is interpreted as the blade cross-section thickness
        at the root, while blade['t'] remains the shell wall thickness from
        the reference JSON. These are different physical quantities.
        """
        tower = dimensions.get("tower", {})
        sections = params["tower"]["sections"]
        if sections and tower:
            old_height = sections[-1]["z1"]
            new_height = float(tower.get("height", old_height))
            base_d = float(tower.get("base_diameter", sections[0]["d0"]))
            top_d = float(tower.get("top_diameter", sections[-1]["d1"]))
            wall_t = float(tower.get("thickness", sections[0]["t"]))
            for section in sections:
                f0 = section["z0"] / old_height if old_height else 0.0
                f1 = section["z1"] / old_height if old_height else 1.0
                section["z0"] = f0 * new_height
                section["z1"] = f1 * new_height
                section["d0"] = base_d + (top_d - base_d) * f0
                section["d1"] = base_d + (top_d - base_d) * f1
                section["t"] = wall_t

        nacelle = dimensions.get("nacelle", {})
        if nacelle:
            nac = params["nacelle"]
            old_center = (nac["y_rear"] + nac["y_front"]) / 2
            length = float(nacelle.get("length", nac["y_front"] - nac["y_rear"]))
            nac["y_rear"] = old_center - length / 2
            nac["y_front"] = old_center + length / 2
            nac["width"] = float(nacelle.get("width", nac["width"]))
            nac["height"] = float(nacelle.get("height", nac["height"]))

        rotor = dimensions.get("rotor", {})
        if rotor:
            params["hub"]["diameter"] = float(
                rotor.get("hub_diameter", params["hub"]["diameter"])
            )
            stations = params["blade"]["stations"]
            old_length = stations[-1]["r"] - stations[0]["r"]
            new_length = float(rotor.get("blade_length", old_length))
            root_width = float(rotor.get("blade_root_width", stations[0]["chord"]))
            tip_width = float(rotor.get("blade_tip_width", stations[-1]["chord"]))
            root_thickness = float(rotor.get("blade_thickness", stations[0]["thick"]))
            for station in stations:
                fraction = (station["r"] - stations[0]["r"]) / old_length if old_length else 0.0
                station["r"] = stations[0]["r"] + fraction * new_length
                station["chord"] = root_width + fraction * (tip_width - root_width)
                station["thick"] = root_thickness + fraction * (
                    min(tip_width * 0.18, root_thickness) - root_thickness
                )

    def _build_view(self, params: dict):
        if not gmsh.isInitialized():
            gmsh.initialize()
        gmsh.clear()

        groups, _thickness = build_default(params)
        gmsh.model.mesh.setSize(gmsh.model.getEntities(0), 2.5)
        gmsh.option.setNumber("Mesh.MeshSizeMin", 0.8)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 3.0)
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.model.mesh.generate(2)

        node_tags, coordinates, _ = gmsh.model.mesh.getNodes()
        if len(node_tags) == 0:
            raise RuntimeError("Gmsh generated no mesh nodes.")
        points = np.asarray(coordinates, dtype=float).reshape((-1, 3))
        node_index = {int(tag): i for i, tag in enumerate(node_tags)}

        if self.plotter is None:
            self.message_label.hide()
            self.plotter = QtInteractor(self)
            self.layout.addWidget(self.plotter.interactor)
            self.plotter.set_background("#17191D")

        self.plotter.clear()
        self.actors.clear()
        self.component_meshes.clear()

        gmsh_group_names = {
            "Tower": [name for name in groups if name.startswith("Tower_")],
            "Nacelle": ["Nacelle"],
            "Hub": ["Hub"],
            "Blade 1": ["Blade_1"],
            "Blade 2": ["Blade_2"],
            "Blade 3": ["Blade_3"],
        }

        total_cells = 0
        for component, group_names in gmsh_group_names.items():
            component_cells = []
            component_types = []
            for group_name in group_names:
                for surface_tag in groups.get(group_name, []):
                    element_types, _element_tags, element_node_tags = gmsh.model.mesh.getElements(
                        2, int(surface_tag)
                    )
                    for element_type, connectivity in zip(element_types, element_node_tags):
                        properties = gmsh.model.mesh.getElementProperties(int(element_type))
                        element_name, element_dim, _order, num_nodes = properties[:4]
                        if element_dim != 2:
                            continue
                        if num_nodes not in (3, 4):
                            continue
                        conn = np.asarray(connectivity, dtype=np.int64).reshape((-1, num_nodes))
                        for row in conn:
                            try:
                                indices = [node_index[int(tag)] for tag in row]
                            except KeyError:
                                continue
                            component_cells.append([num_nodes, *indices])
                            component_types.append(
                                pv.CellType.TRIANGLE if num_nodes == 3 else pv.CellType.QUAD
                            )

            if not component_cells:
                continue

            flat_cells = np.asarray([v for cell in component_cells for v in cell], dtype=np.int64)
            cell_types = np.asarray(component_types, dtype=np.uint8)
            mesh = pv.UnstructuredGrid(flat_cells, cell_types, points)
            self.component_meshes[component] = mesh
            color = COMPONENT_COLORS[component]
            actor = self.plotter.add_mesh(
                mesh,
                color=color,
                smooth_shading=True,
                show_edges=False,
                opacity=1.0,
                name=component,
            )
            self.actors[component] = actor
            total_cells += mesh.n_cells

        if not self.actors:
            raise RuntimeError(
                "The generator returned no displayable triangular or quadrilateral surface elements."
            )

        self.plotter.add_axes(line_width=2)
        self.plotter.show_grid(color="#59616B", xlabel="X (m)", ylabel="Y (m)", zlabel="Z (m)")
        self.plotter.view_isometric()
        self.plotter.reset_camera()
        self.plotter.render()

        self.status_message.emit(
            f"Visualization mesh ready: {len(self.actors)} components, {total_cells:,} surface cells."
        )

    def select_component(self, component_name: str | None):
        """Visually emphasize the selected model-tree component."""
        if not self.actors:
            return
        selected = component_name if component_name in self.actors else None
        for name, actor in self.actors.items():
            actor.GetProperty().SetOpacity(1.0 if selected in (None, name) else 0.22)
        self.plotter.render()
        if selected:
            self.component_selected.emit(selected)

    def closeEvent(self, event):
        if self.plotter is not None:
            self.plotter.close()
            self.plotter = None
        super().closeEvent(event)
