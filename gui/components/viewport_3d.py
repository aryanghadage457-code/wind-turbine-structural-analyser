"""Interactive Gmsh/PyVista viewport for the built-in wind turbine model."""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

import gmsh
import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
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


class GeometryWorker(QObject):

    progress = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params

    @Slot()
    def run(self):

        start_time = time.time()

        try:
            self.progress.emit("Initializing Gmsh...")

            if not gmsh.isInitialized():
                raise RuntimeError(
                    "Gmsh was not initialized in the main thread."
                )

            gmsh.clear()

            gmsh.option.setNumber("General.Terminal", 1)

            # -----------------------------------------
            # BUILD GEOMETRY
            # -----------------------------------------

            self.progress.emit("Building turbine surfaces...")

            geometry_start = time.time()

            groups, _thickness = build_default(self.params)

            geometry_time = time.time() - geometry_start

            self.progress.emit(
                f"Geometry created in {geometry_time:.1f} seconds."
            )

            # -----------------------------------------
            # VISUALIZATION MESH SETTINGS
            # -----------------------------------------

            self.progress.emit(
                "Preparing visualization mesh..."
            )

            gmsh.option.setNumber(
                "Mesh.ElementOrder", 1
            )

            gmsh.option.setNumber(
                "Mesh.MeshSizeMin", 4.0
            )

            gmsh.option.setNumber(
                "Mesh.MeshSizeMax", 8.0
            )

            gmsh.option.setNumber(
                "Mesh.MeshSizeFromCurvature", 0
            )

            gmsh.option.setNumber(
                "Mesh.MeshSizeExtendFromBoundary", 0
            )

            gmsh.option.setNumber(
                "Mesh.Algorithm", 6
            )

            points_entities = gmsh.model.getEntities(0)

            if points_entities:
                gmsh.model.mesh.setSize(
                    points_entities,
                    8.0
                )

            # -----------------------------------------
            # GENERATE SURFACE MESH
            # -----------------------------------------

            self.progress.emit(
                "Generating coarse visualization surface mesh..."
            )

            mesh_start = time.time()

            gmsh.model.mesh.generate(2)

            mesh_time = time.time() - mesh_start

            self.progress.emit(
                f"Surface mesh generated in {mesh_time:.1f} seconds."
            )

            # -----------------------------------------
            # EXTRACT NODES
            # -----------------------------------------

            self.progress.emit(
                "Extracting mesh nodes..."
            )

            node_tags, coordinates, _ = (
                gmsh.model.mesh.getNodes()
            )

            if len(node_tags) == 0:
                raise RuntimeError(
                    "Gmsh generated no mesh nodes."
                )

            points = np.asarray(
                coordinates,
                dtype=np.float64
            ).reshape((-1, 3))

            node_index = {
                int(tag): index
                for index, tag in enumerate(node_tags)
            }

            # -----------------------------------------
            # COMPONENT GROUPS
            # -----------------------------------------

            group_map = {
                "Tower": [
                    name for name in groups
                    if name.startswith("Tower_")
                ],
                "Nacelle": ["Nacelle"],
                "Hub": ["Hub"],
                "Blade 1": ["Blade_1"],
                "Blade 2": ["Blade_2"],
                "Blade 3": ["Blade_3"],
            }

            result = {}
            total_cells = 0

            # -----------------------------------------
            # EXTRACT COMPONENT ELEMENTS
            # -----------------------------------------

            self.progress.emit(
                "Extracting component surface elements..."
            )

            for component, group_names in group_map.items():

                component_cells = []
                component_types = []

                for group_name in group_names:

                    surface_tags = groups.get(
                        group_name,
                        []
                    )

                    for surface_tag in surface_tags:

                        element_types, _, element_node_tags = (
                            gmsh.model.mesh.getElements(
                                2,
                                int(surface_tag)
                            )
                        )

                        for element_type, connectivity in zip(
                            element_types,
                            element_node_tags
                        ):

                            properties = (
                                gmsh.model.mesh.getElementProperties(
                                    int(element_type)
                                )
                            )

                            element_dim = properties[1]
                            num_nodes = properties[3]

                            if element_dim != 2:
                                continue

                            if num_nodes not in (3, 4):
                                continue

                            conn = np.asarray(
                                connectivity,
                                dtype=np.int64
                            ).reshape((-1, num_nodes))

                            for row in conn:

                                try:
                                    indices = [
                                        node_index[int(tag)]
                                        for tag in row
                                    ]

                                except KeyError:
                                    continue

                                component_cells.append(
                                    [num_nodes, *indices]
                                )

                                component_types.append(
                                    int(
                                        pv.CellType.TRIANGLE
                                        if num_nodes == 3
                                        else pv.CellType.QUAD
                                    )
                                )

                if component_cells:

                    flat_cells = np.asarray(
                        [
                            value
                            for cell in component_cells
                            for value in cell
                        ],
                        dtype=np.int64
                    )

                    cell_types = np.asarray(
                        component_types,
                        dtype=np.uint8
                    )

                    result[component] = (
                        points,
                        flat_cells,
                        cell_types
                    )

                    total_cells += len(component_types)

            if not result:

                raise RuntimeError(
                    "No displayable surface elements were found. "
                    "The geometry groups may contain invalid surface tags."
                )

            total_time = time.time() - start_time

            self.succeeded.emit({
                "components": result,
                "total_cells": total_cells,
                "generation_time": total_time,
            })

        except Exception:

            self.failed.emit(
                traceback.format_exc()
            )

        finally:

            try:
                if gmsh.isInitialized():
                    gmsh.clear()

            except Exception:
                pass


class TurbineViewport(QWidget):

    status_message = Signal(str)
    component_selected = Signal(str)

    def __init__(self, project_data=None, parent=None):

        super().__init__(parent)

        self.project_data = project_data or {}

        self.plotter = None
        self.actors = {}
        self.component_meshes = {}

        self.geometry_loaded = False
        self.loading = False

        self._thread = None
        self._worker = None

        self.setMinimumSize(400, 350)

        self.setStyleSheet(
            "background-color: #17191D;"
        )

        self.layout = QVBoxLayout(self)

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.message_label = QLabel(
            "Open Geometry to generate the turbine model."
        )

        self.message_label.setAlignment(
            Qt.AlignCenter
        )

        self.message_label.setWordWrap(True)

        self.message_label.setStyleSheet(
            "color: #A5ABB4;"
            "background-color: #17191D;"
            "padding: 12px;"
        )

        self.layout.addWidget(
            self.message_label
        )

    # ==================================================
    # START GEOMETRY GENERATION
    # ==================================================

    def ensure_geometry_loaded(self):

        if self.geometry_loaded or self.loading:
            return

        try:
            params = self._load_parameters()

        except Exception as exc:

            self.message_label.setText(
                "Could not load turbine parameters.\n\n"
                f"{type(exc).__name__}: {exc}"
            )

            self.status_message.emit(
                f"Parameter loading failed: {exc}"
            )

            return

        self.loading = True

        # Gmsh must be initialized in the main Python thread.
        try:
                if not gmsh.isInitialized():
                    gmsh.initialize()

        except Exception as exc:
            self.loading = False

            self.message_label.setText(
                "Could not initialize Gmsh.\n\n"
                f"{type(exc).__name__}: {exc}"
            )

            self.status_message.emit(
                f"Gmsh initialization failed: {exc}"
            )

            return

        self.message_label.show()

        self.message_label.setText(
            "Generating turbine geometry and surface mesh...\n\n"
            "Please wait."
        )

        self.status_message.emit(
            "Starting turbine geometry generation..."
        )

        self._thread = QThread(self)

        self._worker = GeometryWorker(params)

        self._worker.moveToThread(
            self._thread
        )

        self._thread.started.connect(
            self._worker.run
        )

        self._worker.progress.connect(
            self._on_worker_progress
        )

        self._worker.succeeded.connect(
            self._on_geometry_ready
        )

        self._worker.failed.connect(
            self._on_geometry_failed
        )

        self._worker.succeeded.connect(
            self._thread.quit
        )

        self._worker.failed.connect(
            self._thread.quit
        )

        self._thread.finished.connect(
            self._worker.deleteLater
        )

        self._thread.finished.connect(
            self._on_thread_finished
        )

        self._thread.start()

    # ==================================================
    # LOAD PARAMETERS
    # ==================================================

    def _load_parameters(self):

        project_path = self.project_data.get(
            "project_path"
        )

        model_config_path = None

        if project_path:

            model_config_path = (
                Path(project_path)
                / "config"
                / "model_config.json"
            )

        model_config = {}

        if (
            model_config_path
            and model_config_path.exists()
        ):

            with model_config_path.open(
                "r",
                encoding="utf-8"
            ) as file:

                model_config = json.load(file)

        model_source = model_config.get(
            "model_source",
            self.project_data.get(
                "model_source",
                "builtin"
            )
        )

        if model_source == "step":

            raise NotImplementedError(
                "STEP viewport loading has not been integrated yet."
            )

        root = Path(__file__).resolve().parents[2]

        json_path = (
            root
            / "data"
            / "default_turbine.json"
        )

        raw = json_path.read_text(
            encoding="utf-8"
        ).replace("\u00a0", " ")

        params = json.loads(raw)

        dimensions = (
            model_config.get("dimensions")
            or self.project_data.get("dimensions")
        )

        if dimensions:

            self._apply_dialog_dimensions(
                params,
                dimensions
            )

        return params

    # ==================================================
    # APPLY USER DIMENSIONS
    # ==================================================

    @staticmethod
    def _apply_dialog_dimensions(params, dimensions):

        tower = dimensions.get("tower", {})

        sections = params["tower"]["sections"]

        if sections and tower:

            old_height = sections[-1]["z1"]

            new_height = float(
                tower.get("height", old_height)
            )

            base_d = float(
                tower.get(
                    "base_diameter",
                    sections[0]["d0"]
                )
            )

            top_d = float(
                tower.get(
                    "top_diameter",
                    sections[-1]["d1"]
                )
            )

            wall_t = float(
                tower.get(
                    "thickness",
                    sections[0]["t"]
                )
            )

            for section in sections:

                f0 = (
                    section["z0"] / old_height
                    if old_height else 0.0
                )

                f1 = (
                    section["z1"] / old_height
                    if old_height else 1.0
                )

                section["z0"] = f0 * new_height
                section["z1"] = f1 * new_height

                section["d0"] = (
                    base_d + (top_d - base_d) * f0
                )

                section["d1"] = (
                    base_d + (top_d - base_d) * f1
                )

                section["t"] = wall_t

        # NACELLE

        nacelle = dimensions.get("nacelle", {})

        if nacelle:

            nac = params["nacelle"]

            old_center = (
                nac["y_rear"] + nac["y_front"]
            ) / 2

            length = float(
                nacelle.get(
                    "length",
                    nac["y_front"] - nac["y_rear"]
                )
            )

            nac["y_rear"] = old_center - length / 2
            nac["y_front"] = old_center + length / 2

            nac["width"] = float(
                nacelle.get("width", nac["width"])
            )

            nac["height"] = float(
                nacelle.get("height", nac["height"])
            )

        # ROTOR AND BLADES

        rotor = dimensions.get("rotor", {})

        if rotor:

            params["hub"]["diameter"] = float(
                rotor.get(
                    "hub_diameter",
                    params["hub"]["diameter"]
                )
            )

            stations = params["blade"]["stations"]

            old_length = (
                stations[-1]["r"] - stations[0]["r"]
            )

            new_length = float(
                rotor.get(
                    "blade_length",
                    old_length
                )
            )

            root_width = float(
                rotor.get(
                    "blade_root_width",
                    stations[0]["chord"]
                )
            )

            tip_width = float(
                rotor.get(
                    "blade_tip_width",
                    stations[-1]["chord"]
                )
            )

            root_thickness = float(
                rotor.get(
                    "blade_thickness",
                    stations[0]["thick"]
                )
            )

            start_radius = stations[0]["r"]

            for station in stations:

                fraction = (
                    (station["r"] - start_radius) / old_length
                    if old_length else 0.0
                )

                station["r"] = (
                    start_radius + fraction * new_length
                )

                station["chord"] = (
                    root_width
                    + fraction * (tip_width - root_width)
                )

                station["thick"] = (
                    root_thickness
                    + fraction * (
                        min(tip_width * 0.18, root_thickness)
                        - root_thickness
                    )
                )

    # ==================================================
    # PROGRESS
    # ==================================================

    @Slot(str)
    def _on_worker_progress(self, message):

        self.message_label.setText(
            "Generating turbine geometry...\n\n"
            + message
        )

        self.status_message.emit(
            message
        )

    # ==================================================
    # DISPLAY GEOMETRY
    # ==================================================

    @Slot(object)
    def _on_geometry_ready(self, payload):

        try:

            if self.plotter is None:

                self.plotter = QtInteractor(self)

                self.layout.addWidget(
                    self.plotter.interactor
                )

                self.plotter.set_background(
                    "#17191D"
                )

            self.plotter.clear()

            self.actors.clear()
            self.component_meshes.clear()

            for component, (
                points,
                flat_cells,
                cell_types
            ) in payload["components"].items():

                mesh = pv.UnstructuredGrid(
                    flat_cells,
                    cell_types,
                    points
                )

                self.component_meshes[component] = mesh

                actor = self.plotter.add_mesh(
                    mesh,
                    color=COMPONENT_COLORS.get(
                        component,
                        "#A0A0A0"
                    ),
                    smooth_shading=True,
                    show_edges=False,
                    opacity=1.0,
                    name=component
                )

                self.actors[component] = actor

            self.plotter.add_axes(
                line_width=2
            )

            self.plotter.show_grid(
                color="#59616B",
                xlabel="X (m)",
                ylabel="Y (m)",
                zlabel="Z (m)"
            )

            self.plotter.view_isometric()

            self.plotter.reset_camera()

            self.plotter.render()

            self.message_label.hide()

            self.geometry_loaded = True

            self.status_message.emit(
                "3D turbine model displayed successfully. "
                f"Components: {len(self.actors)} | "
                f"Surface cells: {payload['total_cells']:,} | "
                f"Time: {payload['generation_time']:.1f} seconds."
            )

        except Exception:

            self._on_geometry_failed(
                traceback.format_exc()
            )

    # ==================================================
    # ERROR HANDLING
    # ==================================================

    @Slot(str)
    def _on_geometry_failed(self, error_text):

        self.loading = False
        self.geometry_loaded = False

        lines = error_text.strip().splitlines()

        short_error = (
            lines[-1]
            if lines
            else "Unknown error"
        )

        self.message_label.show()

        self.message_label.setText(
            "Could not generate the 3D turbine model.\n\n"
            f"{short_error}\n\n"
            "Check the VS Code terminal for details."
        )

        self.status_message.emit(
            f"Geometry generation failed: {short_error}"
        )

        print(
            "\n--- Geometry generation traceback ---\n"
        )

        print(error_text)

    @Slot()
    def _on_thread_finished(self):

        self.loading = False
        self._thread = None
        self._worker = None

    # ==================================================
    # COMPONENT SELECTION
    # ==================================================

    def select_component(self, component_name):

        if not self.actors or self.plotter is None:
            return

        selected = (
            component_name
            if component_name in self.actors
            else None
        )

        for name, actor in self.actors.items():

            actor.GetProperty().SetOpacity(
                1.0 if selected in (None, name) else 0.22
            )

        self.plotter.render()

        if selected:

            self.component_selected.emit(
                selected
            )

    # ==================================================
    # CLEANUP
    # ==================================================

    def closeEvent(self, event):

        if (
            self._thread is not None
            and self._thread.isRunning()
        ):

            # Do not destroy a running QThread.
# Wait until the geometry worker finishes.
            self._thread.wait()
                
        if self.plotter is not None:

            self.plotter.close()
            self.plotter = None

        super().closeEvent(event)