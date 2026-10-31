from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QPushButton
)

from PySide6.QtCore import Qt


class DashboardPage(QWidget):

    def __init__(self):
        super().__init__()

        self.setObjectName("dashboardPage")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 25, 30, 25)
        main_layout.setSpacing(22)

        # Welcome section
        welcome = QLabel("Welcome to Wind Turbine Analysis")
        welcome.setObjectName("welcomeTitle")

        subtitle = QLabel(
            "Structural Analysis and Performance Evaluation"
        )
        subtitle.setObjectName("subtitle")

        main_layout.addWidget(welcome)
        main_layout.addWidget(subtitle)

        # Information cards
        cards_layout = QGridLayout()
        cards_layout.setSpacing(15)

        card_data = [
            ("TURBINE HEIGHT", "90 m"),
            ("WIND SPEED", "45 m/s"),
            ("SELECTED MATERIAL", "Structural Steel"),
            ("ANALYSIS STATUS", "Not Started")
        ]

        for index, (title, value) in enumerate(card_data):

            card = QFrame()
            card.setObjectName("infoCard")

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(20, 18, 20, 18)

            title_label = QLabel(title)
            title_label.setObjectName("cardTitle")

            value_label = QLabel(value)
            value_label.setObjectName("cardValue")
            value_label.setWordWrap(True)

            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)

            cards_layout.addWidget(
                card,
                0,
                index
            )

        main_layout.addLayout(cards_layout)

        # Quick actions
        actions_title = QLabel("Quick Actions")
        actions_title.setObjectName("sectionTitle")

        main_layout.addWidget(actions_title)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(15)

        self.new_analysis_btn = QPushButton(
            "+ Create New Analysis"
        )

        self.import_btn = QPushButton(
            "Import STEP Model"
        )

        self.load_btn = QPushButton(
            "Load Existing Project"
        )

        for button in [
            self.new_analysis_btn,
            self.import_btn,
            self.load_btn
        ]:
            button.setMinimumHeight(48)
            button.setCursor(Qt.PointingHandCursor)
            actions_layout.addWidget(button)

        main_layout.addLayout(actions_layout)

        # Recent projects
        recent_title = QLabel("Recent Projects")
        recent_title.setObjectName("sectionTitle")

        main_layout.addWidget(recent_title)

        recent_box = QFrame()
        recent_box.setObjectName("recentBox")

        recent_layout = QVBoxLayout(recent_box)

        recent_label = QLabel(
            "No recent projects available.\n"
            "Create a new analysis to get started."
        )

        recent_label.setObjectName("recentText")
        recent_label.setAlignment(Qt.AlignCenter)

        recent_layout.addWidget(recent_label)

        main_layout.addWidget(recent_box)

        main_layout.addStretch()

        # Styling
        self.setStyleSheet("""
            QWidget#dashboardPage {
                background-color: #101923;
            }

            QLabel#welcomeTitle {
                color: white;
                font-size: 27px;
                font-weight: bold;
            }

            QLabel#subtitle {
                color: #91a4b8;
                font-size: 14px;
            }

            QFrame#infoCard {
                background-color: #1b2938;
                border: 1px solid #2b3d50;
                border-radius: 10px;
                min-height: 110px;
            }

            QLabel#cardTitle {
                color: #9aafc4;
                font-size: 12px;
                font-weight: bold;
            }

            QLabel#cardValue {
                color: white;
                font-size: 21px;
                font-weight: bold;
            }

            QLabel#sectionTitle {
                color: white;
                font-size: 19px;
                font-weight: bold;
            }

            QPushButton {
                background-color: #1769aa;
                color: white;
                border: none;
                border-radius: 7px;
                padding: 10px;
                font-size: 13px;
            }

            QPushButton:hover {
                background-color: #2585cf;
            }

            QFrame#recentBox {
                background-color: #1b2938;
                border: 1px solid #2b3d50;
                border-radius: 10px;
                min-height: 110px;
            }

            QLabel#recentText {
                color: #91a4b8;
                font-size: 14px;
            }
        """)