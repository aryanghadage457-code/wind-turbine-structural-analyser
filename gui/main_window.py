"""Engineering Workspace (ANSYS-style).

    ribbon
    ┌─────────┬──────────────────────┬─────────┐
    │ Outline │ Graphics             │ Details │
    │         ├──────────────────────┤         │
    │         │ Messages/Graphs/Log  │         │
    └─────────┴──────────────────────┴─────────┘
    status bar

Same constructor as before: MainWindow(project_data).
`close_requested` is emitted by File > Close Project. When this window is
embedded in the single-window shell, main.py connects it to go back to the
Start page; while it is a stand-alone window it simply closes.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMainWindow, QSplitter, QVBoxLayout, QWidget

from gui.workspace.bottom_dock import BottomDock
from gui.workspace.details_panel import DetailsPanel
from gui.workspace.graphics_view import GraphicsView
from gui.workspace.outline_tree import OutlinePanel
from gui.workspace.ribbon import Ribbon
from gui.workspace.status_bar import StatusBar


class MainWindow(QMainWindow):

    close_requested = Signal()

    def __init__(self, project_data=None, parent=None):
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

        # ---------- layout ----------
        centre = QSplitter(Qt.Vertical)
        centre.addWidget(self.graphics)
        centre.addWidget(self.dock)
        centre.setStretchFactor(0, 4)
        centre.setStretchFactor(1, 1)
        centre.setSizes([620, 200])

        main = QSplitter(Qt.Horizontal)
        main.addWidget(self.outline)
        main.addWidget(centre)
        main.addWidget(self.details)
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 1)
        main.setStretchFactor(2, 0)
        main.setSizes([250, 900, 300])
        main.setChildrenCollapsible(False)

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
        self.graphics.view_requested.connect(self._on_view_requested)

        self.outline.tree.select(self.project_name)
        self.dock.add_message(f"Opened project '{self.project_name}'.")

    # ------------------------------------------------------------------
    def _on_outline_selected(self, name, kind):
        if kind == "component":
            self.graphics.set_caption(name)
            self.status.set_status(f"Selected {name}")
        else:
            self.graphics.set_caption("Graphics")
            self.status.set_status("Ready")

    def _on_view_requested(self, key):
        self.dock.log(f"View: {key}")

    def _on_action(self, action_id):
        # Placeholder: real handlers are connected during integration.
        self.dock.add_message(f"'{action_id}' is not connected yet.", "warning")

    def _on_close_project(self):
        self.close_requested.emit()
        if self.isWindow():
            self.close()


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    from gui.theme.styles import install_theme

    app = QApplication(sys.argv)
    install_theme(app)
    win = MainWindow({"project_name": "Demo project"})
    win.showMaximized()
    sys.exit(app.exec())