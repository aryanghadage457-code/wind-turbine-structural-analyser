"""ANSYS-style ribbon: File menu, tab row and grouped tool buttons.

Signals
    action_triggered(str)   id of the clicked button, e.g. "geometry.dimensions"
    close_project_requested()  File > Close Project (go back to the Start page)

Styling comes from the Ribbon* rules in gui/theme/styles.py.
"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QStackedWidget,
    QTabBar, QToolButton, QVBoxLayout, QWidget,
)

from gui.workspace.ribbon_icons import ribbon_icon


def _safe_icon(name, size=26):
    try:
        return ribbon_icon(name, size)
    except Exception:
        return QIcon()


# tab -> [(group title, [(action id, label, icon name, enabled)])]
TABS = {
    "Home": [
        ("Project", [("project.save", "Save", "save", True),
                     ("project.close", "Close\nProject", "close_project", True)]),
        ("View", [("view.fit", "Fit", "fit", True),
                  ("view.iso", "Isometric", "cube", True),
                  ("view.front", "Front", "cube", True),
                  ("view.top", "Top", "mesh", True),
                  ("view.bottom", "Bottom", "mesh", True),
                  ("view.left", "Left", "cube", True),
                  ("view.right", "Right", "cube", True),
                  ("view.wireframe", "Wireframe", "mesh", True, True, False)]),
        ("Display", [("view.axes", "Axes", "mesh", True, True, True)]),
    ],
    "Geometry": [
        ("Edit", [("geometry.dimensions", "Dimensions", "dimensions", True)]),
    ],
    "Setup": [
        ("Environment", [("setup.wind", "Wind", "wind", True)]),
        ("Mesh", [("setup.mesh", "Mesh\nSettings", "mesh", True)]),
    ],
    "Solution": [
        ("Solve", [("solve.run", "Solve", "play", False),
                   ("solve.cancel", "Cancel", "stop", False)]),
    ],
    "Results": [
        ("Contours", [("results.stress", "Stress", "contour", False),
                      ("results.displacement", "Displacement", "displacement", False)]),
        ("Surface", [("results.outer", "Outer", "outer", False),
                     ("results.inner", "Inner", "inner", False)]),
        ("Failure", [("results.failure", "Failure\nSpeed", "warning", False)]),
    ],
}


class Ribbon(QWidget):

    action_triggered = Signal(str)
    close_project_requested = Signal()

    def __init__(self, project_name="", parent=None):
        super().__init__(parent)

        self.buttons = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- tab row ----------
        tab_row = QFrame()
        tab_row.setObjectName("RibbonTabRow")
        row = QHBoxLayout(tab_row)
        row.setContentsMargins(0, 0, 12, 0)
        row.setSpacing(0)

        self.file_button = QPushButton("File")
        self.file_button.setObjectName("FileTab")
        self.file_button.setCursor(Qt.PointingHandCursor)
        self.file_button.setMenu(self._build_file_menu())
        row.addWidget(self.file_button)

        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("RibbonTabBar")
        self.tab_bar.setDrawBase(False)
        for name in TABS:
            self.tab_bar.addTab(name)
        row.addWidget(self.tab_bar)

        row.addStretch()

        self.project_label = QLabel(project_name)
        self.project_label.setObjectName("RibbonProject")
        row.addWidget(self.project_label)

        root.addWidget(tab_row)

        # ---------- ribbon body ----------
        body = QFrame()
        body.setObjectName("RibbonBody")
        body.setFixedHeight(116)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        for groups in TABS.values():
            self.stack.addWidget(self._build_page(groups))
        body_layout.addWidget(self.stack)

        root.addWidget(body)

        self.tab_bar.currentChanged.connect(self.stack.setCurrentIndex)

    # ------------------------------------------------------------------
    def _build_file_menu(self):
        menu = QMenu(self)
        for action_id, text in (
            ("project.new", "New Project"),
            ("project.open", "Open Project..."),
            ("project.save", "Save"),
        ):
            act = menu.addAction(text)
            act.triggered.connect(
                lambda _=False, a=action_id: self.action_triggered.emit(a)
            )
        menu.addSeparator()
        close = menu.addAction("Close Project")
        close.triggered.connect(self.close_project_requested.emit)
        return menu

    def _build_page(self, groups):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(6, 4, 6, 2)
        layout.setSpacing(0)

        for title, items in groups:
            group = QFrame()
            group.setObjectName("RibbonGroup")
            g_layout = QVBoxLayout(group)
            g_layout.setContentsMargins(8, 2, 8, 2)
            g_layout.setSpacing(2)

            buttons_row = QHBoxLayout()
            buttons_row.setSpacing(2)

            for item in items:
                action_id, label, icon_name, enabled = item[:4]
                checkable, checked = (item[4], item[5]) if len(item) == 6 else (False, False)

                btn = QToolButton()
                btn.setObjectName("RibbonButton")
                btn.setText(label)
                btn.setIcon(_safe_icon(icon_name))
                btn.setIconSize(QSize(26, 26))
                btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setEnabled(enabled)
                btn.setCheckable(checkable)
                if checkable:
                    btn.setChecked(checked)
                btn.clicked.connect(
                    lambda _=False, a=action_id: self._on_click(a)
                )
                self.buttons[action_id] = btn
                buttons_row.addWidget(btn)
                
            caption = QLabel(title)
            caption.setObjectName("RibbonGroupLabel")
            caption.setAlignment(Qt.AlignCenter)

            g_layout.addLayout(buttons_row, 1)
            g_layout.addWidget(caption)
            layout.addWidget(group)

        layout.addStretch()
        return page

    def _on_click(self, action_id):
        if action_id == "project.close":
            self.close_project_requested.emit()
        else:
            self.action_triggered.emit(action_id)

    # ------------------------------------------------------------------
    # public helpers
    def set_project_name(self, name):
        self.project_label.setText(name)

    def set_action_enabled(self, action_id, enabled):
        if action_id in self.buttons:
            self.buttons[action_id].setEnabled(enabled)


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    from gui.theme.styles import install_theme

    app = QApplication(sys.argv)
    install_theme(app)
    w = Ribbon("Demo project")
    w.action_triggered.connect(print)
    w.resize(1100, 140)
    w.show()
    sys.exit(app.exec())