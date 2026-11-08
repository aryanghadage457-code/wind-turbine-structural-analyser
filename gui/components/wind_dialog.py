"""Wind settings dialog - collects v_ref (hub-height wind speed) and
wind_bearing_deg (compass bearing the wind comes FROM) for the W load case.

Matches contracts.Settings exactly: v_ref in m/s, wind_bearing_deg in degrees,
0 = wind from North, 90 = wind from East (clockwise compass bearing).
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QDoubleSpinBox, QGroupBox, QWidget
)


class WindSettingsDialog(QDialog):
    """Modal dialog for the reference wind speed and direction."""

    values_changed = Signal(float, float)  # v_ref, bearing_deg — live preview

    def __init__(self, v_ref=8.0, bearing_deg=0.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wind Conditions")
        self.setMinimumSize(420, 320)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("DialogHeader")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(25, 20, 25, 20)
        title = QLabel("Wind Conditions")
        title.setObjectName("SectionTitle")
        subtitle = QLabel(
            "Set the reference wind speed and the compass direction "
            "the wind is coming from."
        )
        subtitle.setObjectName("SecondaryText")
        subtitle.setWordWrap(True)
        h_layout.addWidget(title)
        h_layout.addWidget(subtitle)
        root.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(25, 20, 25, 10)
        body_layout.setSpacing(15)

        group = QGroupBox("Parked-rotor wind load")
        form = QFormLayout(group)

        self.speed_input = QDoubleSpinBox()
        self.speed_input.setRange(0.1, 100.0)
        self.speed_input.setDecimals(2)
        self.speed_input.setSingleStep(0.5)
        self.speed_input.setValue(v_ref)
        self.speed_input.setSuffix(" m/s")
        self.speed_input.valueChanged.connect(self._emit_preview)

        self.bearing_input = QDoubleSpinBox()
        self.bearing_input.setRange(0.0, 359.9)
        self.bearing_input.setDecimals(1)
        self.bearing_input.setSingleStep(5.0)
        self.bearing_input.setValue(bearing_deg % 360.0)
        self.bearing_input.setSuffix(" °")
        self.bearing_input.valueChanged.connect(self._emit_preview)

        form.addRow("Hub-height wind speed:", self.speed_input)
        form.addRow(
            "Direction wind blows FROM\n(0° = North, 90° = East):",
            self.bearing_input
        )

        body_layout.addWidget(group)

        hint = QLabel(
            "This is the single reference speed used for the wind load "
            "case. The failure check scales this result to every other "
            "speed, since the wind load is proportional to v²."
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

        confirm = QPushButton("Use these conditions")
        confirm.setObjectName("PrimaryButton")
        confirm.clicked.connect(self.accept)

        f_layout.addWidget(cancel)
        f_layout.addWidget(confirm)
        root.addWidget(footer)

    def _emit_preview(self):
        self.values_changed.emit(self.speed_input.value(), self.bearing_input.value())

    @property
    def v_ref(self):
        return self.speed_input.value()

    @property
    def bearing_deg(self):
        return self.bearing_input.value() % 360.0