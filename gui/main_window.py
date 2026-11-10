"""Engineering Workspace (ANSYS-style).

    ribbon
    ┌─────────┬──────────────────────┬─────────┐
    │ Outline │ Graphics             │ Details │
    │         ├──────────────────────┤         │
    │         │ Messages/Graphs/Log  │         │
    └─────────┴──────────────────────┴─────────┘
    status bar

MainWindow(project_data, viewport=None)
    If `viewport` is given, it must be a TurbineViewport already created for
    this project (possibly already loaded). This window reuses it rather
    than building the geometry a second time.
`close_requested` is emitted by File > Close Project.
`project_action` is emitted for File > New / Open; the caller handles it.
"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QMainWindow, QSplitter, QVBoxLayout, QWidget

from gui.components.viewport_3d import TurbineViewport
from gui.workspace.bottom_dock import BottomDock
from gui.workspace.details_panel import DetailsPanel
from gui.workspace.graphics_view import GraphicsView
from gui.workspace.outline_tree import OutlinePanel
from gui.workspace.ribbon import Ribbon
from gui.workspace.status_bar import StatusBar
from gui.components.wind_dialog import WindSettingsDialog
from gui.components.solve_job import SolveRunner
from gui.components.mesh_dialog import MeshSettingsDialog
from gui.components.results_loader import load_result, build_result_rows
from gui.turbine_config_dialog import TurbineConfigDialog
from failure_analysis import format_report


class MainWindow(QMainWindow):

    close_requested = Signal()
    project_action = Signal(str)   # project.new / project.open

    def __init__(self, project_data=None, parent=None, viewport=None):
        super().__init__(parent)

        self.project_data = project_data or {}
        self.project_name = self.project_data.get(
            "project_name", "Wind Turbine Project"
        )

        self.setWindowTitle(
            f"{self.project_name} - Wind Turbine Structural Analyser"
        )
        self.setMinimumSize(1100, 700)
        self._solver = None
        self._results_viewer = None

        # ---------- widgets ----------
        self.ribbon = Ribbon(self.project_name)
        self.outline = OutlinePanel(self.project_name)
        self.graphics = GraphicsView()
        self.dock = BottomDock()
        self.details = DetailsPanel()
        self.status = StatusBar()
        

        built_elsewhere = viewport is not None
        self.viewport = viewport if built_elsewhere else TurbineViewport(self.project_data)
        self.graphics.set_viewport(self.viewport)

        # ---------- layout ----------
        centre = QSplitter(Qt.Vertical)
        centre.addWidget(self.graphics)
        centre.addWidget(self.dock)
        centre.setStretchFactor(0, 5)
        centre.setStretchFactor(1, 1)
        centre.setCollapsible(0, False)
        centre.setCollapsible(1, False)
        self.dock.setMinimumHeight(100)
        self.graphics.setMinimumHeight(300)
        self._centre_split = centre

        main = QSplitter(Qt.Horizontal)
        main.addWidget(self.outline)
        main.addWidget(centre)
        main.addWidget(self.details)
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 1)
        main.setStretchFactor(2, 0)
        main.setChildrenCollapsible(False)
        self.outline.setMinimumWidth(200)
        self.details.setMinimumWidth(260)
        self._main_split = main
        self._sized = False

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.ribbon)
        layout.addWidget(main, 1)
        layout.addWidget(self.status)
        self.setCentralWidget(container)

        # ---------- connections ----------
        self.outline.tree.item_selected.connect(self.details.show_for)
        self.outline.tree.item_selected.connect(self._on_outline_selected)
        self.ribbon.action_triggered.connect(self._on_action)
        self.ribbon.close_project_requested.connect(self._on_close_project)

        # geometry <-> rest of the workspace
        self.viewport.status_message.connect(self.dock.add_message)
        self.viewport.component_selected.connect(self._on_viewport_selected)
        self.viewport.geometry_ready.connect(self._on_geometry_ready)

        self.outline.tree.select(self.project_name)
        self.dock.add_message(f"Opened project '{self.project_name}'.")

        if built_elsewhere:
            # Geometry was already generated before this window existed.
            if self.viewport.last_details:
                self._on_geometry_ready(self.viewport.last_details)
        else:
            # Stand-alone use (e.g. running this file directly): build now.
            QTimer.singleShot(150, self.viewport.ensure_geometry_loaded)

    # ------------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if not self._sized:
            self._sized = True
            QTimer.singleShot(0, self._apply_sizes)

    def _apply_sizes(self):
        total_w = max(self._main_split.width(), 1000)
        self._main_split.setSizes([210, total_w - 210 - 270, 270])
        total_h = max(self._centre_split.height(), 600)
        self._centre_split.setSizes([total_h - 110, 110])

    def _on_outline_selected(self, name, kind):
        if kind == "component":
            self.graphics.set_caption(name)
            self.status.set_status(f"Selected {name}")
            self.viewport.select_component(name)
        else:
            self.graphics.set_caption("3D Viewport")
            self.status.set_status("Ready")
            self.viewport.select_component(None)

    def _on_viewport_selected(self, name):
        """A part was clicked directly in the 3D view: sync the tree."""
        self.outline.tree.select(name)

    def _on_geometry_ready(self, details_by_component):
        for name, rows in details_by_component.items():
            self.details.update_component(name, rows)
        self.outline.tree.set_status("Geometry", "done")
        self.dock.add_message("Geometry details updated from the generated model.")
        self.ribbon.set_action_enabled("solve.run", True)
        self.details.update_section("Geometry", self._geometry_overview_rows(details_by_component))

    def _geometry_overview_rows(self, details_by_component):
        rows = [
            ("Components", f"{len(details_by_component)} ({', '.join(sorted(details_by_component))})"),
            ("Model source", self.project_data.get("model_source", "builtin")),
        ]
        values = getattr(self.viewport, "last_values", None) or {}
        if values:
            import parameters as P
            for key, spec in P.PARAMETERS.items():
                if key not in values:
                    continue
                val = values[key]
                text = f"{val:g}" if isinstance(val, float) else str(val)
                unit = spec.get("unit")
                if unit:
                    text += f" {unit}"
                rows.append((spec.get("label", key), text))
        return rows
        self.details.update_section("Geometry", self._geometry_overview_rows(details_by_component))

    def _geometry_overview_rows(self, details_by_component):
        rows = [("Components", f"{len(details_by_component)} ({', '.join(sorted(details_by_component))})")]
        dims = self.project_data.get("dimensions") or {}
        tower, nacelle, rotor = dims.get("tower", {}), dims.get("nacelle", {}), dims.get("rotor", {})
        if tower:
            rows.append(("Tower height",
                         f"{tower.get('height', '—')} m" if tower.get("height") is not None else "—"))
            rows.append(("Tower base / top diameter",
                         f"{tower.get('base_diameter', '—')} / {tower.get('top_diameter', '—')} m"))
        if rotor:
            rows.append(("Blade length",
                         f"{rotor.get('blade_length', '—')} m" if rotor.get("blade_length") is not None else "—"))
            rows.append(("Hub diameter",
                         f"{rotor.get('hub_diameter', '—')} m" if rotor.get("hub_diameter") is not None else "—"))
        if nacelle:
            rows.append(("Nacelle L x W x H",
                         f"{nacelle.get('length', '—')} x {nacelle.get('width', '—')} x "
                         f"{nacelle.get('height', '—')} m"))
        rows.append(("Model source", self.project_data.get("model_source", "builtin")))
        return rows

        
    def _apply_view(self, key):
        result = self.viewport.set_view(key)
        if key == "wireframe":
            self.dock.log(f"Wireframe {'on' if result else 'off'}")
        else:
            self.dock.log(f"View: {key}")   

    def _on_action(self, action_id):
        if action_id in ("project.new", "project.open"):
            self.project_action.emit(action_id)
            return
        if action_id == "project.save":
            self._save_progress()
            return
        if action_id in ("geometry.generate", "geometry.reload"):
            self.viewport.reload()
            return

        if action_id == "geometry.dimensions":
            self._open_dimensions_dialog()
            return

        
        if action_id.startswith("view."):
            key = action_id.split(".", 1)[1]
            if key == "axes":
                visible = self.viewport.toggle_axes()
                self.dock.log(f"Axes {'shown' if visible else 'hidden'}")

            else:
                self._apply_view(key)
            return

        if action_id == "setup.wind":
            self._open_wind_dialog()
            return

        if action_id == "setup.mesh":
            self._open_mesh_dialog()
            return  

        if action_id == "solve.run":
            self._start_solve()
            return
        if action_id == "solve.cancel":
            self._cancel_solve()
            return
        if action_id == "results.failure":
            self.outline.tree.select("Results")
            return
        if action_id == "results.stress":
            self._show_results_view("Von Mises")
            return
        if action_id == "results.displacement":
            self._show_results_view("Displacement")
            return
        if action_id in ("results.outer", "results.inner"):
            self._set_results_surface("outer" if action_id == "results.outer" else "inner")
            return

        
        self.dock.add_message(f"'{action_id}' is not connected yet.", "warning")

    def _save_progress(self):
        from datetime import datetime
        import json
        from pathlib import Path

        project_path = self.project_data.get("project_path")
        if not project_path:
            self.dock.add_message(
                "Cannot save: this project has no folder on disk.", "warning"
            )
            return

        metadata_file = Path(project_path) / "project.json"
        try:
            data = {}
            if metadata_file.exists():
                data = json.loads(metadata_file.read_text(encoding="utf-8"))
            data.update(self.project_data)
            data["last_saved"] = datetime.now().isoformat(timespec="seconds")
            metadata_file.write_text(
                json.dumps(data, indent=4), encoding="utf-8"
            )
            self.project_data = data
            self.status.set_status("Saved")
            self.dock.add_message(
                f"Project saved at {datetime.now().strftime('%H:%M:%S')}."
            )
        except OSError as exc:
            self.dock.add_message(f"Save failed: {exc}", "error")



    def _on_close_project(self):
        self._stop_solver()
        self.close_requested.emit()

    def shutdown(self):
        """Called by the owner before this window is discarded."""
        self._stop_solver()
        self.viewport.shutdown()

    def _stop_solver(self):
        """Cancel any running solve and detach its signals before this
        window's widgets (including the dock) are destroyed. Without this,
        a solve that outlives the window keeps emitting `progress` into a
        dock that no longer exists, which crashes with 'Internal C++
        object already deleted.'"""
        if self._solver is not None:
            try:
                self._solver.progress.disconnect()
            except (RuntimeError, TypeError):
                pass
            try:
                self._solver.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._solver.cancel()
            self._solver = None

    @staticmethod
    def _compass_label(bearing_deg):
        dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        return dirs[int((bearing_deg % 360.0) / 22.5 + 0.5) % 16]

    def _open_wind_dialog(self):
        current = self.project_data.get("wind", {})
        dialog = WindSettingsDialog(
            v_ref=current.get("v_ref", 8.0),
            bearing_deg=current.get("bearing_deg", 0.0),
            parent=self,
        )
        dialog.values_changed.connect(self._preview_wind)
        if dialog.exec():
            self.project_data["wind"] = {
                "v_ref": dialog.v_ref,
                "bearing_deg": dialog.bearing_deg,
            }
            self.dock.add_message(
                f"Wind set: {dialog.v_ref:g} m/s from {dialog.bearing_deg:g}°."
            )
            self.outline.tree.set_status("Environment", "done")
            self.details.update_section("Environment", [
                ("Wind speed", f"{dialog.v_ref:g} m/s"),
                ("Direction (from)",
                 f"{dialog.bearing_deg:g}\u00b0 ({self._compass_label(dialog.bearing_deg)})"),
                ("Status", "Defined"),
            ])
        else:
            # Restore whatever was showing before the live preview
            wind = self.project_data.get("wind")
            if wind:
                self.viewport.add_wind_indicator(wind["v_ref"], wind["bearing_deg"])
            else:
                self.viewport.clear_wind_indicator()

    def _preview_wind(self, v_ref, bearing_deg):
        self.viewport.add_wind_indicator(v_ref, bearing_deg)

    def _open_mesh_dialog(self):
        current = self.project_data.get("mesh", {})
        dialog = MeshSettingsDialog(
            element_size=current.get("element_size", 3.0),
            parent=self,
        )
        if dialog.exec():
            self.project_data["mesh"] = {"element_size": dialog.element_size}
            self.dock.add_message(f"Mesh element size set: {dialog.element_size:g} m.")
            self.outline.tree.set_status("Mesh", "done")
            self.viewport.apply_mesh(dialog.element_size)
            self.details.update_section("Mesh", [
                ("Scoping", "Whole turbine (1 body)"),
                ("Element size", f"{dialog.element_size:g} m"),
                ("Status", "Defined"),
            ])


    def _open_dimensions_dialog(self):
        if self.viewport.loading:
            self.dock.add_message("Geometry is already being generated; please wait.", "warning")
            return
        current = self._load_saved_dimensions()
        dialog = TurbineConfigDialog(self, initial_values=current)
        if not dialog.exec():
            return
        self.project_data["dimensions"] = dialog.dimensions
        self._save_model_config(dialog.dimensions)
        self.dock.add_message("Turbine dimensions updated. Rebuilding geometry...")
        self.outline.tree.set_status("Geometry", "pending")
        self.viewport.reload()

    def _load_saved_dimensions(self):
        import json
        from pathlib import Path

        project_path = self.project_data.get("project_path")
        if not project_path:
            return None
        path = Path(project_path) / "config" / "model_config.json"
        if not path.exists():
            return None
        try:
            model_config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        dims = model_config.get("dimensions")
        return dims if isinstance(dims, dict) and dims else None

    def _save_model_config(self, dimensions):
        import json
        from pathlib import Path

        project_path = self.project_data.get("project_path")
        if not project_path:
            return
        config_dir = Path(project_path) / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        path = config_dir / "model_config.json"
        model_config = {}
        if path.exists():
            try:
                model_config = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                model_config = {}
        model_config["model_source"] = model_config.get(
            "model_source", self.project_data.get("model_source", "builtin")
        )
        model_config["dimensions"] = dimensions
        path.write_text(json.dumps(model_config, indent=4), encoding="utf-8")

    def _start_solve(self):
        wind = self.project_data.get("wind")
        mesh = self.project_data.get("mesh")
        if not mesh:
            self.dock.add_message("Set mesh settings before solving.", "warning")
            self._open_mesh_dialog()
            return
        if not wind:
            self.dock.add_message("Set wind conditions before solving.", "warning")
            self._open_wind_dialog()
            return
        if not self.viewport.last_config:
            self.dock.add_message("Geometry must be generated before solving.", "warning")
            return
        
        project_path = self.project_data.get("project_path")
        if not project_path:
            self.dock.add_message("This project has no folder on disk; cannot solve.", "error")
            return

        self.ribbon.set_action_enabled("solve.run", False)
        self.ribbon.set_action_enabled("solve.cancel", True)
        self.status.set_status("Solving...")
        self.dock.add_message(
            f"Starting solve at {wind['v_ref']:g} m/s from {wind['bearing_deg']:g}°..."
        )
        self.details.update_section("Solution", [
            ("Status", "Running..."),
            ("Wind speed", f"{wind['v_ref']:g} m/s"),
            ("Direction (from)", f"{wind['bearing_deg']:g}\u00b0"),
            ("Mesh element size", f"{mesh['element_size']:g} m"),
        ])

        self._solver = SolveRunner(
            project_path, self.viewport.last_config,
            wind["v_ref"], wind["bearing_deg"],
            mesh_size=mesh["element_size"],
            ccx_path=self.project_data.get("ccx_path"),
        )
        self._solver.progress.connect(lambda line: self.dock.log(line))
        self._solver.finished.connect(self._on_solve_finished)
        self._solver.start()

    def _cancel_solve(self):
        if self._solver is not None:
            self._solver.cancel()
            self.dock.add_message("Solve cancelled.", "warning")

    def _on_solve_finished(self, success, out_dir):
        self.ribbon.set_action_enabled("solve.run", True)
        self.ribbon.set_action_enabled("solve.cancel", False)
        self._solver = None
        if success:
            self.status.set_status("Solved")
            self.outline.tree.set_status("Solution", "done")
            self.dock.add_message(f"Solve complete. Results in {out_dir}.")
            self.details.update_section("Solution", [
                ("Status", "Complete"),
                ("Output folder", str(out_dir)),
            ])

            result = load_result(out_dir)
            if result is not None:
                rows = build_result_rows(result)
                self.details.update_section("Results", rows)
                self.outline.tree.set_status("Results", "done")
                self.dock.add_message(format_report(result))
                op_speed = self.project_data.get("wind", {}).get("v_ref")
                self.dock.show_utilisation_curve(result["curve"], operating_speed=op_speed)
            else:
                self.dock.add_message(
                    "Solve finished but no failure_assessment.json was found.", "warning"
                )

            self.ribbon.set_action_enabled("results.stress", True)
            self.ribbon.set_action_enabled("results.displacement", True)
            self.ribbon.set_action_enabled("results.failure", True)
            self.ribbon.set_action_enabled("results.outer", True)
            self.ribbon.set_action_enabled("results.inner", True)
        else:
            self.status.set_status("Solve failed")
            self.dock.add_message("Solve failed. Check the Log tab for details.", "error")
            self.details.update_section("Solution", [
                ("Status", "Failed — see Log tab"),
            ])

    def _show_results_view(self, default_quantity=None):
        from pathlib import Path
        from gui.components.results_data import load_results_data
        from gui.components.results_viewer import ResultsViewer

        project_path = self.project_data.get("project_path")
        if not project_path:
            self.dock.add_message("No project folder to load results from.", "warning")
            return

        data = load_results_data(Path(project_path) / "out")
        if data is None:
            self.dock.add_message("No solve results found. Run Solve first.", "warning")
            return

        viewer = ResultsViewer(data)
        viewer.status_message.connect(self.dock.add_message)
        viewer.element_selected.connect(self.dock.show_element_details)
        viewer.show_details_requested.connect(
            lambda: self.dock.setCurrentWidget(self.dock.details_page)
        )
        self.dock.set_element_results_data(data)
        if default_quantity:
            idx = viewer.quantity_box.findText(default_quantity)
            if idx >= 0:
                viewer.quantity_box.setCurrentIndex(idx)

        self._results_viewer = viewer
        self._set_results_surface("outer")

        self.graphics.set_viewport(viewer)
        self.graphics.set_caption("Results")

    def _set_results_surface(self, surface):
        self.ribbon.set_action_checked("results.outer", surface == "outer")
        self.ribbon.set_action_checked("results.inner", surface == "inner")
        if self._results_viewer is not None:
            self._results_viewer.set_surface(surface)

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    from gui.theme.styles import install_theme

    app = QApplication(sys.argv)
    install_theme(app)
    win = MainWindow({"project_name": "Demo project"})
    win.showMaximized()
    sys.exit(app.exec())