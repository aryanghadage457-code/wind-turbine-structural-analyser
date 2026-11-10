"""Bottom dock: Messages, Graphs and Log tabs.

    dock.add_message("Geometry generated", "info")   # info | warning | error
    dock.log("raw text line")
"""
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from gui.theme.styles import COLORS
from gui.workspace.sample_data import LOG_MESSAGES
from gui.workspace.utilisation_plot import UtilisationPlot

_LEVEL_COLOR = {
    "info": COLORS["text2"],
    "warning": COLORS["warning"],
    "error": COLORS["danger"],
}


class BottomDock(QTabWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BottomDock")

        # ---- Messages ----
        self.messages = QTableWidget(0, 3)
        self.messages.setHorizontalHeaderLabels(["TYPE", "MESSAGE", "TIME"])
        header = self.messages.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.messages.setColumnWidth(0, 90)
        self.messages.setColumnWidth(2, 90)
        self.messages.verticalHeader().setVisible(False)
        self.messages.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.messages.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.messages.setAlternatingRowColors(True)
        self.addTab(self.messages, "Messages")

        # ---- Graphs ----
        graphs = QWidget()
        g_layout = QVBoxLayout(graphs)
        self.utilisation_plot = UtilisationPlot()
        g_layout.addWidget(self.utilisation_plot)
        self.graphs_page = graphs
        self.addTab(graphs, "Graphs")

        # ---- Log ----
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("LogView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.addTab(self.log_view, "Log")

        for text in LOG_MESSAGES:
            self.add_message(text)

    def add_message(self, text, level="info"):
        row = self.messages.rowCount()
        self.messages.insertRow(row)

        kind = QTableWidgetItem(level.capitalize())
        kind.setForeground(QColor(_LEVEL_COLOR.get(level, COLORS["text2"])))
        self.messages.setItem(row, 0, kind)
        self.messages.setItem(row, 1, QTableWidgetItem(text))
        self.messages.setItem(
            row, 2, QTableWidgetItem(datetime.now().strftime("%H:%M:%S"))
        )
        self.messages.scrollToBottom()
        self.log(f"[{level.upper()}] {text}")

    def log(self, text):
        stamp = datetime.now().strftime("%H:%M:%S")
        try:
            self.log_view.appendPlainText(f"{stamp}  {text}")
        except RuntimeError:
            pass  # the dock's widgets were already destroyed (window closed mid-solve)

    def show_utilisation_curve(self, curve, operating_speed=None):
        """curve is failure_analysis.assess_npz()'s result["curve"] dict."""
        self.utilisation_plot.set_curve(
            curve.get("wind_speed_m_s"), curve.get("utilization"), operating_speed
        )
        self.setCurrentWidget(self.graphs_page)