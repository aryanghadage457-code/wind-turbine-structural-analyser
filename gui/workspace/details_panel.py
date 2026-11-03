"""Right-hand Details panel: read-only property/value table.

    panel.show_for("Tower", "component")
    panel.set_rows([("Name", "Value"), ...])
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from gui.theme.styles import COLORS
from gui.workspace.panel import Panel
from gui.workspace.sample_data import DETAILS, OUTLINE

_STATUS_TEXT = {
    "done": "Defined",
    "pending": "Not defined",
    "locked": "Waiting for earlier steps",
}


class DetailsPanel(Panel):

    def __init__(self, parent=None):
        super().__init__("Details", parent=parent)

        self.table = QTableWidget(0, 2)
        self.table.setObjectName("DetailsTable")
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 120)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(True)
        self.body.addWidget(self.table)

        self.show_for("", "")

    def set_rows(self, rows):
        self.table.setRowCount(len(rows))
        for r, (key, value) in enumerate(rows):
            k = QTableWidgetItem(key)
            k.setForeground(QColor(COLORS["text2"]))
            self.table.setItem(r, 0, k)
            self.table.setItem(r, 1, QTableWidgetItem(str(value)))
        self.table.resizeRowsToContents()

    def show_for(self, name, kind=""):
        if kind == "component" and name in DETAILS:
            rows = DETAILS[name]
        elif kind == "section":
            status = next((s for label, s, _ in OUTLINE if label == name), "pending")
            rows = [("Section", name), ("Status", _STATUS_TEXT.get(status, status))]
        elif kind == "project":
            rows = [("Project", name), ("Analysis", "Not started")]
        else:
            rows = DETAILS["default"]
        self.set_rows(rows)
        self.set_subtitle(name)