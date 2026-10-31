from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame
)

from PySide6.QtCore import Qt


class ModelSourceDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.model_source = None

        self.setWindowTitle("Select Turbine Model")
        self.setMinimumSize(700, 430)

        self.setStyleSheet("""

            QDialog {
                background-color: #202329;
                color: #F2F3F5;
            }

            QLabel {
                color: #F2F3F5;
            }

            QFrame#ModelCard {
                background-color: #292D34;
                border: 1px solid #414751;
                border-radius: 10px;
            }

            QPushButton {
                background-color: #343941;
                color: white;
                border: 1px solid #414751;
                border-radius: 5px;
                padding: 10px;
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

        layout = QVBoxLayout(self)

        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(20)

        # Heading
        title = QLabel("Choose Your Turbine Model")

        title.setStyleSheet("""
            font-size: 23px;
            font-weight: bold;
        """)

        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel(
            "How would you like to define the geometry "
            "for your wind turbine?"
        )

        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignCenter)

        subtitle.setStyleSheet(
            "color: #A5ABB4; font-size: 13px;"
        )

        layout.addWidget(title)
        layout.addWidget(subtitle)

        # ======================================
        # MODEL OPTIONS
        # ======================================

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)

        # Built-in model card
        builtin_card = self.create_card(

            "BUILT-IN CAD MODEL",

            "Start with our predefined wind turbine model "
            "and customize the dimensions of its components.",

            "Customize Dimensions"

        )

        builtin_card.button.clicked.connect(
            self.select_builtin
        )

        # STEP model card
        step_card = self.create_card(

            "IMPORT STEP MODEL",

            "Import your existing wind turbine CAD model "
            "using STEP file format.",

            "Import STEP File"

        )

        step_card.button.clicked.connect(
            self.select_step
        )

        cards_layout.addWidget(builtin_card)
        cards_layout.addWidget(step_card)

        layout.addLayout(cards_layout)

        layout.addStretch()

        # ======================================
        # CANCEL BUTTON
        # ======================================

        cancel_button = QPushButton("Cancel")

        cancel_button.clicked.connect(
            self.reject
        )

        layout.addWidget(cancel_button)


    # ==========================================
    # CREATE MODEL CARD
    # ==========================================

    def create_card(
        self,
        title,
        description,
        button_text
    ):

        card = QFrame()

        card.setObjectName("ModelCard")
        card.setMinimumHeight(230)

        card_layout = QVBoxLayout(card)

        card_layout.setContentsMargins(
            20, 20, 20, 20
        )

        card_layout.setSpacing(15)

        # Card heading
        heading = QLabel(title)

        heading.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #00B8D9;
        """)

        heading.setWordWrap(True)

        # Description
        description_label = QLabel(description)

        description_label.setWordWrap(True)

        description_label.setStyleSheet(
            "color: #A5ABB4;"
        )

        # Button
        button = QPushButton(button_text)

        button.setObjectName("PrimaryButton")

        button.setMinimumHeight(42)

        button.setCursor(Qt.PointingHandCursor)

        card_layout.addWidget(heading)

        card_layout.addWidget(description_label)

        card_layout.addStretch()

        card_layout.addWidget(button)

        # Store button reference
        card.button = button

        return card


    # ==========================================
    # SELECT BUILT-IN MODEL
    # ==========================================

    def select_builtin(self):

        self.model_source = "builtin"

        self.accept()


    # ==========================================
    # SELECT STEP MODEL
    # ==========================================

    def select_step(self):

        self.model_source = "step"

        self.accept()