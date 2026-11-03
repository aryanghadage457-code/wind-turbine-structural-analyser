"""Model source dialog: built-in turbine or imported STEP file.

Result (unchanged): dialog.model_source == "builtin" or "step"
(None if cancelled).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from gui.components.dialog_parts import make_footer, make_header
from gui.theme.icons import pixmap
from gui.theme.styles import COLORS


class ModelSourceDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.model_source = None

        self.setWindowTitle("Select Turbine Model")
        self.setMinimumSize(740, 470)

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
                "cube",
                "Choose Your Turbine Model",
                "How would you like to define the geometry "
                "for your wind turbine?"
            )
        )

        body = QVBoxLayout()
        body.setContentsMargins(26, 24, 26, 20)

        cards = QHBoxLayout()
        cards.setSpacing(20)

        builtin_card = self.create_card(
            "turbine",
            "PARAMETRIC",
            "Built-in CAD Model",
            "Start with the predefined wind turbine model "
            "and customise the dimensions of its components.",
            "Customise Dimensions"
        )
        builtin_card.button.clicked.connect(self.select_builtin)

        step_card = self.create_card(
            "cube",
            "CAD IMPORT",
            "Import STEP Model",
            "Import your existing wind turbine CAD model "
            "using the STEP file format (.step, .stp).",
            "Import STEP File"
        )
        step_card.button.clicked.connect(self.select_step)

        cards.addWidget(builtin_card)
        cards.addWidget(step_card)

        body.addLayout(cards)
        body.addStretch()

        root.addLayout(body, 1)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        root.addWidget(make_footer(cancel_button))

    # ==========================================
    # MODEL CARD
    # ==========================================

    def create_card(
        self,
        icon_name,
        tag,
        title,
        description,
        button_text
    ):

        card = QFrame()
        card.setObjectName("ActionCard")
        card.setMinimumHeight(270)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(8)

        glyph = QLabel()
        glyph.setPixmap(pixmap(icon_name, COLORS["accent"], 40))
        glyph.setFixedHeight(44)

        tag_label = QLabel(tag)
        tag_label.setObjectName("GroupLabel")

        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        heading.setWordWrap(True)

        description_label = QLabel(description)
        description_label.setObjectName("SecondaryText")
        description_label.setWordWrap(True)

        button = QPushButton(button_text)
        button.setObjectName("PrimaryButton")
        button.setMinimumHeight(42)
        button.setCursor(Qt.PointingHandCursor)

        layout.addWidget(glyph)
        layout.addSpacing(4)
        layout.addWidget(tag_label)
        layout.addWidget(heading)
        layout.addWidget(description_label)
        layout.addStretch()
        layout.addWidget(button)

        # Store button reference
        card.button = button

        return card

    # ==========================================
    # SELECTION
    # ==========================================

    def select_builtin(self):

        self.model_source = "builtin"

        self.accept()

    def select_step(self):

        self.model_source = "step"

        self.accept()