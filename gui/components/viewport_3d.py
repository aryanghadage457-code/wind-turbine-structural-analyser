"""Interactive PyVista viewport for the built-in wind turbine.

Gmsh runs in a separate process (geometry_job.py). A QThread only watches that
process, so the GUI never blocks and Gmsh's global state stays out of the app.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import queue as queue_mod
import traceback
from pathlib import Path

import pyvista as pv
from pyvistaqt import QtInteractor

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

import parameters as P
from gui.components.geometry_job import run_job

COMPONENT_COLORS = {
    "Tower": "#9A8873",
    "Nacelle": "#D6CFC4",
    "Hub": "#B5A28B",
    "Blade 1": "#E6A23C",
    "Blade 2": "#7FA38A",
    "Blade 3": "#A78BFA",
}
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

    def __init__(self, config):
        super().__init__()
        self.config = config
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
            proc = ctx.Process(target=run_job, args=(self.config, q), daemon=True)
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
        self._thread = None
        self._worker = None

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

    def ensure_geometry_loaded(self):
        if self.geometry_loaded or self.loading:
            return

        try:
            config = self._load_config()
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
        self._worker = JobWatcher(config)
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
                    color=COMPONENT_COLORS.get(component, "#A0A0A0"),
                    smooth_shading=True,
                    show_edges=False,
                    name=component,
                )

            self.plotter.add_axes(line_width=2)
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