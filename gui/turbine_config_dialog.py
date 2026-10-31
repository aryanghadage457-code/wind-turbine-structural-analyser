from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFormLayout,
    QDoubleSpinBox,
    QGroupBox,
    QScrollArea,
    QWidget,
    QMessageBox
)

from PySide6.QtCore import Qt


class TurbineConfigDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle("Turbine Configuration")

        self.setMinimumSize(550, 650)

        self.dimensions = {}

        self.setStyleSheet("""

            QDialog {
                background-color: #202329;
                color: #F2F3F5;
            }

            QLabel {
                color: #F2F3F5;
            }

            QGroupBox {
                background-color: #292D34;
                border: 1px solid #414751;
                border-radius: 7px;
                margin-top: 12px;
                padding: 12px;
                font-weight: bold;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 5px;
            }

            QDoubleSpinBox {
                background-color: #343941;
                color: white;
                border: 1px solid #414751;
                border-radius: 5px;
                padding: 6px;
                min-height: 25px;
            }

            QPushButton {
                background-color: #343941;
                color: white;
                border: 1px solid #414751;
                border-radius: 5px;
                padding: 9px 15px;
            }

            QPushButton:hover {
                background-color: #0078D4;
            }

            QPushButton#PrimaryButton {
                background-color: #0078D4;
                border: none;
            }

            QPushButton#PrimaryButton:hover {
                background-color: #0063B1;
            }

        """)

        self.create_interface()


    # ==========================================
    # CREATE INTERFACE
    # ==========================================

    def create_interface(self):

        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            25, 25, 25, 25
        )

        main_layout.setSpacing(15)

        # Heading
        title = QLabel("Turbine Dimensions")

        title.setStyleSheet("""
            font-size: 22px;
            font-weight: bold;
        """)

        subtitle = QLabel(
            "Customize the dimensions of your wind turbine. "
            "All dimensions are in metres."
        )

        subtitle.setWordWrap(True)

        subtitle.setStyleSheet(
            "color: #A5ABB4;"
        )

        main_layout.addWidget(title)
        main_layout.addWidget(subtitle)

        # ======================================
        # SCROLL AREA
        # ======================================

        scroll = QScrollArea()

        scroll.setWidgetResizable(True)

        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()

        layout = QVBoxLayout(content)

        layout.setSpacing(15)

        # ======================================
        # TOWER DIMENSIONS
        # ======================================

        tower_group = QGroupBox("Tower")

        tower_form = QFormLayout(tower_group)

        self.tower_height = self.create_input(
            80, 200, 100
        )

        self.tower_base = self.create_input(
            2, 10, 5
        )

        self.tower_top = self.create_input(
            1, 8, 3
        )

        self.tower_thickness = self.create_input(
            0.02, 0.5, 0.05
        )

        tower_form.addRow(
            "Height (m):",
            self.tower_height
        )

        tower_form.addRow(
            "Base diameter (m):",
            self.tower_base
        )

        tower_form.addRow(
            "Top diameter (m):",
            self.tower_top
        )

        tower_form.addRow(
            "Thickness (m):",
            self.tower_thickness
        )

        layout.addWidget(tower_group)

        # ======================================
        # NACELLE DIMENSIONS
        # ======================================

        nacelle_group = QGroupBox("Nacelle")

        nacelle_form = QFormLayout(nacelle_group)

        self.nacelle_length = self.create_input(
            2, 20, 12
        )

        self.nacelle_width = self.create_input(
            1, 8, 4
        )

        self.nacelle_height = self.create_input(
            1, 8, 4
        )

        nacelle_form.addRow(
            "Length (m):",
            self.nacelle_length
        )

        nacelle_form.addRow(
            "Width (m):",
            self.nacelle_width
        )

        nacelle_form.addRow(
            "Height (m):",
            self.nacelle_height
        )

        layout.addWidget(nacelle_group)

        # ======================================
        # HUB AND BLADES
        # ======================================

        rotor_group = QGroupBox("Hub and Blades")

        rotor_form = QFormLayout(rotor_group)

        self.hub_diameter = self.create_input(
            1, 8, 3
        )

        self.blade_length = self.create_input(
            10, 100, 50
        )

        self.blade_root_width = self.create_input(
            0.5, 5, 3
        )

        self.blade_tip_width = self.create_input(
            0.1, 3, 0.5
        )

        self.blade_thickness = self.create_input(
            0.05, 1, 0.3
        )

        rotor_form.addRow(
            "Hub diameter (m):",
            self.hub_diameter
        )

        rotor_form.addRow(
            "Blade length (m):",
            self.blade_length
        )

        rotor_form.addRow(
            "Blade root width (m):",
            self.blade_root_width
        )

        rotor_form.addRow(
            "Blade tip width (m):",
            self.blade_tip_width
        )

        rotor_form.addRow(
            "Blade thickness (m):",
            self.blade_thickness
        )

        layout.addWidget(rotor_group)

        layout.addStretch()

        scroll.setWidget(content)

        main_layout.addWidget(scroll)

        # ======================================
        # BUTTONS
        # ======================================

        buttons = QHBoxLayout()

        cancel_button = QPushButton("Cancel")

        cancel_button.clicked.connect(
            self.reject
        )

        generate_button = QPushButton(
            "Generate Geometry"
        )

        generate_button.setObjectName(
            "PrimaryButton"
        )

        generate_button.clicked.connect(
            self.save_dimensions
        )

        buttons.addStretch()

        buttons.addWidget(cancel_button)

        buttons.addWidget(generate_button)

        main_layout.addLayout(buttons)


    # ==========================================
    # CREATE DIMENSION INPUT
    # ==========================================

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