"""Bottom status bar: state dot, message, progress bar, units.

    bar.set_status("Solving...", "busy")      # ready | busy | error
    bar.set_progress(40)                        # 0-100, or None to hide
    bar.set_info("Units: SI")
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar

from gui.theme.styles import COLORS

_STATE_COLOR = {
    "ready": COLORS["success"],
    "busy": COLORS["warning"],
    "error": COLORS["danger"],
}


class StatusBar(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(28)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(8)

        self.dot = QLabel("●")
        self.text = QLabel("Ready")

        self.progress = QProgressBar()
        self.progress.setFixedWidth(160)
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.hide()

        self.info = QLabel("Units: SI (m, kg, N, Pa, s)")
        self.info.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        row.addWidget(self.dot)
        row.addWidget(self.text)
        row.addStretch()
        row.addWidget(self.progress)
        row.addWidget(self.info)

        self.set_status("Ready", "ready")

    def set_status(self, text, state="ready"):
        self.text.setText(text)
        self.dot.setStyleSheet(
            f"color: {_STATE_COLOR.get(state, COLORS['text3'])};"
        )

    def set_progress(self, value):
        if value is None:
            self.progress.hide()
        else:
            self.progress.setValue(int(value))
            self.progress.show()

    def set_info(self, text):
        self.info.setText(text)