"""Turbine configuration dialog for the built-in model.

Result (unchanged): dialog.dimensions = {"tower": {...}, "nacelle": {...},
"rotor": {...}}, filled when the user presses Generate Geometry.

Note: these fields do not yet match Member 1's 12 parameters. That is
handled in the integration phase; this file is restyled only.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.components.dialog_parts import make_footer, make_header


class TurbineConfigDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle("Turbine Configuration")
        self.setMinimumSize(580, 700)

        self.dimensions = {}

        self.create_interface()

    # ==========================================
    # INTERFACE
    # ==========================================

    def create_interface(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(
            make_header(
                "sliders",
                "Turbine Dimensions",
                "Customise the dimensions of your wind turbine. "
                "All dimensions are in metres."
            )
        )

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        content = QWidget()
        content.setObjectName("ConfigContent")
        content.setStyleSheet(
            "QWidget#ConfigContent { background: transparent; }"
        )

        layout = QVBoxLayout(content)
        layout.setContentsMargins(26, 18, 18, 18)
        layout.setSpacing(6)

        # ---------------- Tower ----------------
        self.tower_height = self.create_input(80, 200, 100)
        self.tower_base = self.create_input(2, 10, 5)
        self.tower_top = self.create_input(1, 8, 3)
        self.tower_thickness = self.create_input(0.02, 0.5, 0.05)

        layout.addWidget(self.create_group("Tower", [
            ("Height", self.tower_height),
            ("Base diameter", self.tower_base),
            ("Top diameter", self.tower_top),
            ("Wall thickness", self.tower_thickness),
        ]))

        # ---------------- Nacelle ----------------
        self.nacelle_length = self.create_input(2, 20, 12)
        self.nacelle_width = self.create_input(1, 8, 4)
        self.nacelle_height = self.create_input(1, 8, 4)

        layout.addWidget(self.create_group("Nacelle", [
            ("Length", self.nacelle_length),
            ("Width", self.nacelle_width),
            ("Height", self.nacelle_height),
        ]))

        # ---------------- Hub and blades ----------------
        self.hub_diameter = self.create_input(1, 8, 3)
        self.blade_length = self.create_input(10, 100, 50)
        self.blade_root_width = self.create_input(0.5, 5, 3)
        self.blade_tip_width = self.create_input(0.1, 3, 0.5)
        self.blade_thickness = self.create_input(0.05, 1, 0.3)

        layout.addWidget(self.create_group("Hub and Blades", [
            ("Hub diameter", self.hub_diameter),
            ("Blade length", self.blade_length),
            ("Blade root width", self.blade_root_width),
            ("Blade tip width", self.blade_tip_width),
            ("Blade thickness", self.blade_thickness),
        ]))

        layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # ---------------- Footer ----------------
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        generate_button = QPushButton("Generate Geometry")
        generate_button.setObjectName("PrimaryButton")
        generate_button.setDefault(True)
        generate_button.clicked.connect(self.save_dimensions)

        root.addWidget(make_footer(cancel_button, generate_button))

    # ==========================================
    # BUILDING BLOCKS
    # ==========================================

    def create_group(self, title, rows):

        group = QGroupBox(title)

        form = QFormLayout(group)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        for text, widget in rows:

            label = QLabel(text.upper())
            label.setObjectName("FieldLabel")

            form.addRow(label, widget)

        return group

    def create_input(
        self,
        minimum,
        maximum,
        default
    ):

        spin = QDoubleSpinBox()

        spin.setRange(
            minimum,
            maximum
        )

        spin.setValue(default)

        spin.setDecimals(3)

        spin.setSingleStep(0.1)

        spin.setSuffix(" m")

        spin.setMinimumWidth(150)

        return spin

    # ==========================================
    # VALIDATE AND SAVE DIMENSIONS
    # ==========================================

    def save_dimensions(self):

        # Tower validation
        if self.tower_base.value() <= self.tower_top.value():

            QMessageBox.warning(

                self,

                "Invalid Tower Dimensions",

                "Tower base diameter must be greater "
                "than tower top diameter."

            )

            return

        # Blade validation
        if self.blade_root_width.value() <= self.blade_tip_width.value():

            QMessageBox.warning(

                self,

                "Invalid Blade Dimensions",

                "Blade root width must be greater "
                "than blade tip width."

            )

            return

        # Store dimensions
        self.dimensions = {

            "tower": {

                "height": self.tower_height.value(),

                "base_diameter": self.tower_base.value(),

                "top_diameter": self.tower_top.value(),

                "thickness": self.tower_thickness.value()

            },

            "nacelle": {

                "length": self.nacelle_length.value(),

                "width": self.nacelle_width.value(),

                "height": self.nacelle_height.value()

            },

            "rotor": {

                "hub_diameter": self.hub_diameter.value(),

                "blade_length": self.blade_length.value(),

                "blade_root_width": self.blade_root_width.value(),

                "blade_tip_width": self.blade_tip_width.value(),

                "blade_thickness": self.blade_thickness.value()

            }

        }

        self.accept()