"""Interactive PyVista viewport for the built-in wind turbine.

Gmsh runs in a separate process (geometry_job.py). A QThread only watches that
process, so the GUI never blocks and Gmsh's global state stays out of the app.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import queue as queue_mod
import traceback
import numpy as np
from pathlib import Path

import pyvista as pv
from pyvistaqt import QtInteractor

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

import parameters as P
from gui.components.geometry_job import run_job

GEOMETRY_COLOR = "#A6A6A6"

BACKGROUND = "#171614"


def _format_thickness(values):
    if not values:
        return "Not available"
    if len(values) == 1:
        return f"{values[0]:.3f} m"
    return f"{min(values):.3f} - {max(values):.3f} m"


class JobWatcher(QObject):
    """Starts the geometry process and relays its messages as Qt signals."""

    progress = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, config, stage="geometry", mesh_size=1.0,
                 mesh_base_size=0.5, mesh_refine_distance=6.0):
        super().__init__()
        self.config = config
        self.stage = stage
        self.mesh_size = mesh_size
        self.mesh_base_size = mesh_base_size
        self.mesh_refine_distance = mesh_refine_distance
        self._cancel = False
        self._process = None

    def cancel(self):
        self._cancel = True
        proc = self._process
        if proc is not None and proc.is_alive():
            proc.terminate()

    @Slot()
    def run(self):
        try:
            ctx = mp.get_context("spawn")
            q = ctx.Queue()
            proc = ctx.Process(
                target=run_job,
                args=(self.config, q, self.stage, self.mesh_size,
                      self.mesh_base_size, self.mesh_refine_distance),
                daemon=True,
            )
            self._process = proc
            proc.start()

            while not self._cancel:
                try:
                    kind, data = q.get(timeout=0.2)
                except queue_mod.Empty:
                    if proc.is_alive():
                        continue
                    try:
                        kind, data = q.get(timeout=0.5)
                    except queue_mod.Empty:
                        self.failed.emit(
                            "The geometry process stopped unexpectedly "
                            f"(exit code {proc.exitcode})."
                        )
                        break

                if kind == "progress":
                    self.progress.emit(data)
                elif kind == "done":
                    self.succeeded.emit(data)
                    break
                elif kind == "error":
                    self.failed.emit(data)
                    break

            proc.join(timeout=5)
            if proc.is_alive():
                proc.terminate()
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            self.finished.emit()


class TurbineViewport(QWidget):

    status_message = Signal(str)
    component_selected = Signal(str)
    geometry_ready = Signal(dict)       # {component_name: [(label, value), ...]}
    build_finished = Signal(bool)       # True on success, False on failure

    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self.project_data = project_data or {}

        self.plotter = None
        self.actors = {}
        self.component_meshes = {}
        self.geometry_loaded = False
        self.loading = False
        self.last_details = None
        self.mesh_stage = "geometry"
        self.mesh_size = 1.0
        self.mesh_base_size = 0.5
        self.mesh_refine_distance = 6.0
        self.show_mesh_edges = False    
        self._thread = None
        self._worker = None
        self._axes_visible = True
        self.last_config = None     

        self.setMinimumSize(400, 350)
        self.setStyleSheet(f"background-color: {BACKGROUND};")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.message_label = QLabel("Open Geometry to generate the turbine model.")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet(
            f"color: #B0A593; background-color: {BACKGROUND}; padding: 12px;"
        )
        self.layout.addWidget(self.message_label)

    # ------------------------------------------------------------------
    def reload(self):
        """Rebuild after the parameters changed."""
        if self.loading:
            return
        self.geometry_loaded = False
        self.ensure_geometry_loaded()

    def apply_mesh(self, element_size):
        """Build the REAL analysis mesh (solver/mesh.py) at this element
        size and display it, replacing the quick preview."""
        self.mesh_stage = "mesh"
        self.mesh_size = element_size
        self.show_mesh_edges = True
        self.geometry_loaded = False
        self.ensure_geometry_loaded()

    def ensure_geometry_loaded(self):
        if self.geometry_loaded or self.loading:
            return

        try:
            config = self._load_config()
            self.last_config = config            
        except Exception as exc:
            self.message_label.show()
            self.message_label.setText(
                f"Could not prepare the turbine parameters.\n\n{exc}"
            )
            self.status_message.emit(f"Parameter problem: {exc}")
            self.build_finished.emit(False)
            return

        self.loading = True
        self.message_label.show()
        self.message_label.setText("Generating turbine geometry...\n\nPlease wait.")
        self.status_message.emit("Starting turbine geometry generation...")

        self._thread = QThread(self)
        self._worker = JobWatcher(
            config,
            stage=self.mesh_stage,
            mesh_size=self.mesh_size,
            mesh_base_size=self.mesh_base_size,
            mesh_refine_distance=self.mesh_refine_distance,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_geometry_ready)
        self._worker.failed.connect(self._on_geometry_failed)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    # ------------------------------------------------------------------
    def _load_config(self):
        project_path = self.project_data.get("project_path")
        model_config = {}
        if project_path:
            path = Path(project_path) / "config" / "model_config.json"
            if path.exists():
                model_config = json.loads(path.read_text(encoding="utf-8"))

        source = model_config.get(
            "model_source", self.project_data.get("model_source", "builtin")
        )
        if source == "step":
            raise NotImplementedError("STEP viewport loading is not integrated yet.")

        values = P.default_values()
        dims = model_config.get("dimensions") or self.project_data.get("dimensions")
        if isinstance(dims, dict) and "tower_height" in dims:
            values.update({k: float(v) for k, v in dims.items() if k in values})
        elif dims:
            self.status_message.emit(
                "This project uses the old dimension format. Default turbine shown."
            )

        errors, warnings = P.validate(values)
        if errors:
            raise ValueError("; ".join(errors))
        for w in warnings:
            self.status_message.emit(f"Warning: {w}")
        return P.apply_to_config(values)

    # ------------------------------------------------------------------
    @Slot(str)
    def _on_progress(self, message):
        self.message_label.setText("Generating turbine geometry...\n\n" + message)
        self.status_message.emit(message)

    @Slot(object)
    def _on_geometry_ready(self, payload):
        try:
            if self.plotter is None:
                self.plotter = QtInteractor(self)
                self.layout.addWidget(self.plotter.interactor)
                self.plotter.set_background(BACKGROUND)

            self.plotter.clear()
            self.actors.clear()
            self.component_meshes.clear()

            points = payload["points"]
            for component, faces in payload["components"].items():
                mesh = pv.PolyData(points, faces)
                self.component_meshes[component] = mesh
                self.actors[component] = self.plotter.add_mesh(
                    mesh,
                    color=GEOMETRY_COLOR,
                    smooth_shading=not self.show_mesh_edges,
                    show_edges=self.show_mesh_edges,
                    edge_color="#5C5C5C",
                    name=component,
                )

            self.plotter.show_axes()
            self.plotter.show_grid(
                color="#59616B", xlabel="X (m)", ylabel="Y (m)", zlabel="Z (m)"
            )

            self.plotter.view_isometric()
            self.plotter.reset_camera()
            self.plotter.render()

            self.message_label.hide()
            self.geometry_loaded = True
            self.status_message.emit(
                "3D turbine model displayed. "
                f"Components: {len(self.actors)} | "
                f"Surface cells: {payload['total_cells']:,} | "
                f"Time: {payload['generation_time']:.1f} s."
            )

            # ---- build Details-panel rows from the real geometry ----
            details = {}
            for component in payload["components"]:
                cells = payload["component_cell_counts"].get(component, 0)
                surfaces = payload["component_surface_counts"].get(component, 0)
                thick = _format_thickness(
                    payload["component_thickness"].get(component, [])
                )
                details[component] = [
                    ("Component", component),
                    ("Surfaces", str(surfaces)),
                    ("Wall thickness", thick),
                    ("Mesh elements", f"{cells:,}"),
                    ("Status", "Geometry generated"),
                ]
            self.last_details = details
            self.geometry_ready.emit(details)
            self.build_finished.emit(True)

        except Exception:
            self._on_geometry_failed(traceback.format_exc())

    @Slot(str)
    def _on_geometry_failed(self, error_text):
        self.geometry_loaded = False
        lines = error_text.strip().splitlines()
        short = lines[-1] if lines else "Unknown error"
        self.message_label.show()
        self.message_label.setText(
            f"Could not generate the 3D turbine model.\n\n{short}"
        )
        self.status_message.emit(f"Geometry generation failed: {short}")
        print("\n--- Geometry generation traceback ---\n")
        print(error_text)
        self.build_finished.emit(False)

    @Slot()
    def _on_thread_finished(self):
        self.loading = False
        self._thread = None
        self._worker = None

    # ------------------------------------------------------------------
    def select_component(self, component_name):
        if not self.actors or self.plotter is None:
            return
        selected = component_name if component_name in self.actors else None
        for name, actor in self.actors.items():
            actor.GetProperty().SetOpacity(
                1.0 if selected in (None, name) else 0.22
            )
        self.plotter.render()
        if selected:
            self.component_selected.emit(selected)

        # ------------------------------------------------------------------
    def set_view(self, key):
        """Handle the Fit / Isometric / Front / Top / Wireframe toolbar."""
        if self.plotter is None:
            return

        if key == "fit":
            self.plotter.reset_camera()
        elif key == "iso":
            self.plotter.view_isometric()
            self.plotter.reset_camera()
        elif key == "front":
            self.plotter.view_xz()
            self.plotter.reset_camera()
        elif key == "top":
            self.plotter.view_xy()
            self.plotter.reset_camera()
        elif key == "bottom":
            self.plotter.view_xy(negative=True)
            self.plotter.reset_camera()
        elif key == "left":
            self.plotter.view_yz(negative=True)
            self.plotter.reset_camera()
        elif key == "right":
            self.plotter.view_yz()
            self.plotter.reset_camera()
        elif key == "wireframe":
            self._wireframe = not getattr(self, "_wireframe", False)
            for actor in self.actors.values():
                prop = actor.GetProperty()
                if self._wireframe:
                    prop.SetRepresentationToWireframe()
                else:
                    prop.SetRepresentationToSurface()

        self.plotter.render()
        return getattr(self, "_wireframe", False) if key == "wireframe" else None


    def toggle_axes(self):
        """Show/hide both the corner orientation triad and the bounding grid."""
        if self.plotter is None:
            return self._axes_visible

        self._axes_visible = not self._axes_visible
        if self._axes_visible:
            self.plotter.show_axes()
            self.plotter.show_grid(
                color="#59616B", xlabel="X (m)", ylabel="Y (m)", zlabel="Z (m)"
            )
        else:
            self.plotter.hide_axes()
            self.plotter.remove_bounds_axes()
        self.plotter.render()
        return self._axes_visible

    def shutdown(self):
        """Stop the background process. Call this before discarding the viewport."""
        if self._worker is not None:
            self._worker.cancel()
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        if self.plotter is not None:
            self.plotter.close()
            self.plotter = None

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def add_wind_indicator(self, v_ref, bearing_deg, z_hub=None):
        """Draw an arrow showing wind direction/rough speed. Safe to call
        repeatedly — it replaces the previous arrow rather than stacking."""
        if self.plotter is None:
            return
        from solver.loads import wind_dir_vector
        d = wind_dir_vector(bearing_deg)
        z = z_hub if z_hub is not None else self._estimate_hub_height()
        bounds = self.plotter.bounds
        span = max(bounds[1] - bounds[0], bounds[3] - bounds[2], 40.0)
        offset = span * 0.9
        length = span * 0.35 * min(max(v_ref / 10.0, 0.4), 1.6)
        start = np.array([0.0, 0.0, z]) - d * offset
        arrow = pv.Arrow(start=start, direction=d, scale=length)
        if "WindArrow" in self.actors:
            self.plotter.remove_actor(self.actors.pop("WindArrow"))
        self.actors["WindArrow"] = self.plotter.add_mesh(
            arrow, color="#00B8D9", name="WindArrow"
        )
        self.plotter.render()

    def clear_wind_indicator(self):
        if "WindArrow" in self.actors and self.plotter is not None:
            self.plotter.remove_actor(self.actors.pop("WindArrow"))
            self.plotter.render()

    def _estimate_hub_height(self):
        if self.plotter is None:
            return 90.0
        _, _, _, _, _, zmax = self.plotter.bounds
        return zmax * 0.7