"""Left-hand Outline: project > workflow sections > turbine components.

Signal
    item_selected(name: str, kind: str)   kind = "project" | "section" | "component"

Public
    set_project_name(name)
    set_status(section, "done" | "pending" | "locked")
    select(name)
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from gui.theme.styles import COLORS
from gui.workspace.panel import Panel
from gui.workspace.sample_data import OUTLINE

_STATUS_COLOR = {
    "done": COLORS["success"],
    "pending": COLORS["warning"],
    "locked": COLORS["text3"],
    "part": COLORS["accent"],
    "project": COLORS["accent"],
}

KIND_ROLE = Qt.UserRole + 1


def _dot(color, size=12):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(2, 2, size - 4, size - 4)
    p.end()
    return QIcon(pix)


class OutlineTree(QTreeWidget):

    item_selected = Signal(str, str)

    def __init__(self, project_name="Project", parent=None):
        super().__init__(parent)
        self.setObjectName("OutlineTree")
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.setUniformRowHeights(True)
        self.setEditTriggers(QTreeWidget.NoEditTriggers)

        self._sections = {}
        self._build(project_name)
        self.currentItemChanged.connect(self._on_current_changed)

    def _build(self, project_name):
        self.clear()
        self._root = QTreeWidgetItem(self, [project_name])
        self._root.setIcon(0, _dot(_STATUS_COLOR["project"]))
        self._root.setData(0, KIND_ROLE, "project")

        for label, status, parts in OUTLINE:
            section = QTreeWidgetItem(self._root, [label])
            section.setIcon(0, _dot(_STATUS_COLOR[status]))
            section.setData(0, KIND_ROLE, "section")
            self._sections[label] = section
            for part in parts:
                child = QTreeWidgetItem(section, [part])
                child.setIcon(0, _dot(_STATUS_COLOR["part"]))
                child.setData(0, KIND_ROLE, "component")
            section.setExpanded(True)
        self._root.setExpanded(True)

    def _on_current_changed(self, current, _previous):
        if current is not None:
            self.item_selected.emit(
                current.text(0), current.data(0, KIND_ROLE) or ""
            )

    # ---------------- public ----------------
    def set_project_name(self, name):
        self._root.setText(0, name)

    def set_status(self, section, status):
        item = self._sections.get(section)
        if item is not None and status in _STATUS_COLOR:
            item.setIcon(0, _dot(_STATUS_COLOR[status]))

    def select(self, name):
        for item in self.findItems(name, Qt.MatchRecursive | Qt.MatchExactly):
            self.setCurrentItem(item)
            return


class OutlinePanel(Panel):
    """OutlineTree inside a titled panel."""

    def __init__(self, project_name="Project", parent=None):
        super().__init__("Outline", parent=parent)
        self.tree = OutlineTree(project_name)
        self.body.addWidget(self.tree)