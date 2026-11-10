from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QPushButton
)

from PySide6.QtCore import Qt, Signal


class DashboardPage(QWidget):

    geometry_requested = Signal()
    analysis_requested = Signal()

    def __init__(self, project_data=None):

        super().__init__()

        self.project_data = project_data or {}

        self.setObjectName("dashboardPage")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 25, 30, 25)
        main_layout.setSpacing(22)

        # Welcome section
        project_name = self.project_data.get(
            "project_name",
            "New Wind Turbine Project"
        )

        welcome = QLabel(f"Welcome to {project_name}")
        welcome.setObjectName("welcomeTitle")
        welcome.setWordWrap(True)

        subtitle = QLabel(
            "Structural Analysis and Engineering Workspace"
        )
        subtitle.setObjectName("subtitle")

        main_layout.addWidget(welcome)
        main_layout.addWidget(subtitle)

        # Project information
        info_title = QLabel("Project Overview")
        info_title.setObjectName("sectionTitle")

        main_layout.addWidget(info_title)

        cards_layout = QGridLayout()
        cards_layout.setSpacing(15)

        model_source = self.project_data.get(
            "model_source",
            "Not configured"
        )

        if model_source == "builtin":
            model_source = "Built-in CAD Model"

        elif model_source == "step":
            model_source = "Imported STEP Model"

        project_location = self.project_data.get(
            "project_path",
            "Not available"
        )

        card_data = [
            ("PROJECT NAME", project_name),
            ("MODEL SOURCE", model_source),
            ("ANALYSIS STATUS", "Not Started"),
            ("PROJECT LOCATION", project_location)
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
                index // 2,
                index % 2
            )

        main_layout.addLayout(cards_layout)

        # Quick actions
        actions_title = QLabel("Quick Actions")
        actions_title.setObjectName("sectionTitle")

        main_layout.addWidget(actions_title)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(15)

        self.geometry_btn = QPushButton("Open Geometry")
        self.analysis_btn = QPushButton("Start Analysis")

        for button in [
            self.geometry_btn,
            self.analysis_btn
        ]:

            button.setMinimumHeight(48)
            button.setCursor(Qt.PointingHandCursor)

            actions_layout.addWidget(button)

        main_layout.addLayout(actions_layout)

        self.geometry_btn.clicked.connect(
            self.geometry_requested.emit
        )

        self.analysis_btn.clicked.connect(
            self.analysis_requested.emit
        )

        main_layout.addStretch()

        # Styling
        self.setStyleSheet("""
            QWidget#dashboardPage {
                background-color: #17191D;
            }

            QLabel#welcomeTitle {
                color: #F2F3F5;
                font-size: 27px;
                font-weight: bold;
            }

            QLabel#subtitle {
                color: #A5ABB4;
                font-size: 14px;
            }

            QFrame#infoCard {
                background-color: #292D34;
                border: 1px solid #414751;
                border-radius: 9px;
                min-height: 100px;
            }

            QLabel#cardTitle {
                color: #A5ABB4;
                font-size: 11px;
                font-weight: bold;
            }

            QLabel#cardValue {
                color: #F2F3F5;
                font-size: 17px;
                font-weight: bold;
            }

            QLabel#sectionTitle {
                color: #F2F3F5;
                font-size: 19px;
                font-weight: bold;
            }

            QPushButton {
                background-color: #0078D4;
                color: white;
                border: none;
                border-radius: 7px;
                padding: 10px;
                font-size: 13px;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #168DE5;
            }
        """)