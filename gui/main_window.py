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
            self.graphics.set_caption("Graphics")
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
        if action_id.startswith("view."):
            key = action_id.split(".", 1)[1]
            if key == "axes":
                visible = self.viewport.toggle_axes()
                self.dock.log(f"Axes {'shown' if visible else 'hidden'}")
            else:
                self._apply_view(key)
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
        self.close_requested.emit()

    def shutdown(self):
        """Called by the owner before this window is discarded."""
        self.viewport.shutdown()


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    from gui.theme.styles import install_theme

    app = QApplication(sys.argv)
    install_theme(app)
    win = MainWindow({"project_name": "Demo project"})
    win.showMaximized()
    sys.exit(app.exec())