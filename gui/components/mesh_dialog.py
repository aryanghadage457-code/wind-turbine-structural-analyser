"""Mesh settings dialog - ANSYS 'Body Sizing' style. One Element Size input
that controls the surface mesh density shown in the viewport and used as
--mesh-size for the real solve.
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QDoubleSpinBox, QGroupBox, QWidget
)


class MeshSettingsDialog(QDialog):

    def __init__(self, element_size=3.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mesh Settings")
        self.setMinimumSize(420, 300)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("DialogHeader")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(25, 20, 25, 20)
        title = QLabel("Mesh Settings")
        title.setObjectName("SectionTitle")
        subtitle = QLabel("Set the surface element size for the whole turbine.")
        subtitle.setObjectName("SecondaryText")
        subtitle.setWordWrap(True)
        h_layout.addWidget(title)
        h_layout.addWidget(subtitle)
        root.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(25, 20, 25, 10)
        body_layout.setSpacing(15)

        group = QGroupBox("Body Sizing")
        form = QFormLayout(group)

        scoping = QLabel("Whole turbine (1 body)")
        scoping.setObjectName("SecondaryText")
        form.addRow("Scoping:", scoping)

        self.size_input = QDoubleSpinBox()
        self.size_input.setRange(0.05, 20.0)
        self.size_input.setDecimals(2)
        self.size_input.setSingleStep(0.25)
        self.size_input.setValue(element_size)
        self.size_input.setSuffix(" m")
        form.addRow("Element Size:", self.size_input)

        body_layout.addWidget(group)

        hint = QLabel(
            "A smaller element size gives a finer mesh and a more accurate "
            "solve, at the cost of a longer solve time."
        )
        hint.setObjectName("SecondaryText")
        hint.setWordWrap(True)
        body_layout.addWidget(hint)
        body_layout.addStretch()

        root.addWidget(body)

        footer = QWidget()
        footer.setObjectName("DialogFooter")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(25, 15, 25, 15)
        f_layout.addStretch()

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        confirm = QPushButton("Generate Mesh")
        confirm.setObjectName("PrimaryButton")
        confirm.clicked.connect(self.accept)

        f_layout.addWidget(cancel)
        f_layout.addWidget(confirm)
        root.addWidget(footer)

    @property
    def element_size(self):
        return self.size_input.value()