"""Small modal dialog shown while the turbine geometry builds in the
background, before the Engineering Workspace appears.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout


class LoadingOverlay(QDialog):

    def __init__(self, parent=None, message="Preparing project..."):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setWindowModality(Qt.ApplicationModal)
        self.setFixedSize(400, 130)
        self.setObjectName("LoadingOverlay")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(10)

        self.title_label = QLabel("Generating Turbine Model")
        self.title_label.setObjectName("DialogTitle")
        layout.addWidget(self.title_label)

        self.message_label = QLabel(message)
        self.message_label.setObjectName("HintText")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        bar = QProgressBar()
        bar.setRange(0, 0)          # indeterminate
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        layout.addWidget(bar)

        self.setStyleSheet(
            "QDialog#LoadingOverlay { background-color: #221F1D; "
            "border: 1px solid #4A453E; border-radius: 10px; } "
            "QLabel { background: transparent; }"
        )

    def set_message(self, text):
        self.message_label.setText(text)

    def center_on(self, widget):
        if widget is None:
            return
        geo = widget.frameGeometry()
        self.move(
            geo.center().x() - self.width() // 2,
            geo.center().y() - self.height() // 2,
        )