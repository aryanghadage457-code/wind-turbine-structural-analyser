from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QPushButton,
    QGridLayout
)

from PySide6.QtCore import Qt


class DashboardPage(QWidget):

    def __init__(self):
        super().__init__()

        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(30, 25, 30, 25)
        main_layout.setSpacing(25)

        # -------------------------
        # WELCOME SECTION
        # -------------------------

        welcome = QLabel("Welcome to Wind Turbine Analysis")

        welcome.setStyleSheet("""
            color: white;
            font-size: 27px;
            font-weight: bold;
        """)

        subtitle = QLabel(
            "Structural Analysis and Performance Evaluation"
        )

        subtitle.setStyleSheet("""
            color: #91a4b8;
            font-size: 14px;
        """)

        main_layout.addWidget(welcome)
        main_layout.addWidget(subtitle)

        # -------------------------
        # INFORMATION CARDS
        # -------------------------

        cards_layout = QGridLayout()
        cards_layout.setSpacing(18)

        card_data = [
            ("Turbine Height", "90 m"),
            ("Wind Speed", "45 m/s"),
            ("Material", "Structural Steel"),
            ("Analysis Status", "Not Started")
        ]

        for index, (title, value) in enumerate(card_data):

            card = QFrame()
            card.setObjectName("infoCard")

            card_layout = QVBoxLayout(card)

            title_label = QLabel(title)

            title_label.setStyleSheet("""
                color: #9aafc4;
                font-size: 14px;
            """)

            value_label = QLabel(value)

            value_label.setStyleSheet("""
                color: white;
                font-size: 23px;
                font-weight: bold;
            """)

            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)

            cards_layout.addWidget(
                card,
                0,
                index
            )

        main_layout.addLayout(cards_layout)

        # -------------------------
        # QUICK ACTIONS
        # -------------------------

        actions_title = QLabel("Quick Actions")

        actions_title.setStyleSheet("""
            color: white;
            font-size: 20px;
            font-weight: bold;
        """)

        main_layout.addWidget(actions_title)

        actions_layout = QHBoxLayout()

        actions = [
            "Create New Analysis",
            "Import STEP Model",
            "Load Project"
        ]

        for action in actions:

            button = QPushButton(action)

            button.setMinimumHeight(50)

            button.setCursor(Qt.PointingHandCursor)

            actions_layout.addWidget(button)

        main_layout.addLayout(actions_layout)

        # -------------------------
        # RECENT PROJECTS
        # -------------------------

        recent_title = QLabel("Recent Projects")

        recent_title.setStyleSheet("""
            color: white;
            font-size: 20px;
            font-weight: bold;
        """)

        main_layout.addWidget(recent_title)

        recent_project = QLabel(
            "No recent projects available."
        )

        recent_project.setStyleSheet("""
            color: #91a4b8;
            font-size: 14px;
            padding: 15px;
            background-color: #1b2938;
            border-radius: 8px;
        """)

        main_layout.addWidget(recent_project)

        main_layout.addStretch()

        # -------------------------
        # PAGE STYLING
        # -------------------------

        self.setStyleSheet("""
            QWidget {
                background-color: #101923;
            }

            QFrame#infoCard {
                background-color: #1b2938;
                border: 1px solid #2b3d50;
                border-radius: 10px;
                min-height: 110px;
            }

            QPushButton {
                background-color: #1769aa;
                color: white;
                border: none;
                border-radius: 7px;
                font-size: 14px;
                padding: 10px;
            }

            QPushButton:hover {
                background-color: #2585cf;
            }
        """)