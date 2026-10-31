from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox,
    QScrollArea
)

from PySide6.QtCore import Qt, Signal


class StartPage(QWidget):

    new_project_requested = Signal()
    import_step_requested = Signal()
    open_project_requested = Signal(str)

    def __init__(self):
        super().__init__()

        self.setObjectName("StartPage")

        # Main layout
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # =====================================
        # LEFT SIDEBAR
        # =====================================

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(245)

        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 28, 18, 20)
        side_layout.setSpacing(12)

        logo = QLabel("WT  WIND TURBINE")
        logo.setStyleSheet(
            "font-size: 18px; font-weight: bold; padding: 12px;"
        )

        side_layout.addWidget(logo)

        subtitle = QLabel("STRUCTURAL ANALYSER")
        subtitle.setObjectName("SecondaryText")
        subtitle.setStyleSheet("font-size: 9px; padding-left: 12px;")

        side_layout.addWidget(subtitle)
        side_layout.addSpacing(30)

        self.home_btn = self.create_nav_button("⌂    Home", True)
        self.projects_btn = self.create_nav_button("▣    Projects")
        self.settings_btn = self.create_nav_button("⚙    Settings")

        side_layout.addWidget(self.home_btn)
        side_layout.addWidget(self.projects_btn)
        side_layout.addWidget(self.settings_btn)

        side_layout.addStretch()

        footer = QLabel(
            "WIND TURBINE ANALYSER\nVersion 1.0"
        )
        footer.setObjectName("SecondaryText")
        footer.setStyleSheet("font-size: 10px; padding: 12px;")

        side_layout.addWidget(footer)

        root.addWidget(sidebar)

        # =====================================
        # MAIN CONTENT
        # =====================================

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(38, 28, 38, 30)
        content_layout.setSpacing(24)

        scroll.setWidget(content)

        root.addWidget(scroll)

        # =====================================
        # TOP TOOLBAR
        # =====================================

        topbar = QHBoxLayout()

        page_label = QLabel("HOME")
        page_label.setObjectName("SecondaryText")

        settings_button = QPushButton("⚙  Settings")
        settings_button.setMinimumHeight(38)

        settings_button.clicked.connect(self.show_settings)

        topbar.addWidget(page_label)
        topbar.addStretch()
        topbar.addWidget(settings_button)

        content_layout.addLayout(topbar)

        # =====================================
        # WELCOME SECTION
        # =====================================

        welcome = QLabel(
            "Welcome to Wind Turbine\nStructural Analyser"
        )
        welcome.setObjectName("PageTitle")

        subtitle = QLabel(
            "Design, simulate and analyse wind turbine structures."
        )
        subtitle.setObjectName("SecondaryText")

        content_layout.addWidget(welcome)
        content_layout.addWidget(subtitle)

        # =====================================
        # ACTION CARDS
        # =====================================

        cards_layout = QGridLayout()
        cards_layout.setSpacing(18)

        new_card = self.create_action_card(
            "＋",
            "NEW PROJECT",
            "Start a new structural analysis project.",
            "Create New Project"
        )

        import_card = self.create_action_card(
            "⇧",
            "IMPORT CAD MODEL",
            "Import an existing STEP model for analysis.",
            "Browse STEP Files"
        )

        new_card.button.clicked.connect(
            self.new_project_requested.emit
        )

        import_card.button.clicked.connect(
            self.import_step_requested.emit
        )

        cards_layout.addWidget(new_card, 0, 0)
        cards_layout.addWidget(import_card, 0, 1)

        content_layout.addLayout(cards_layout)

        # =====================================
        # RECENT PROJECTS
        # =====================================

        recent_heading = QLabel("Recent Projects")
        recent_heading.setObjectName("SectionTitle")

        content_layout.addWidget(recent_heading)

        recent_panel = QFrame()
        recent_panel.setObjectName("Panel")

        recent_layout = QVBoxLayout(recent_panel)
        recent_layout.setContentsMargins(15, 15, 15, 15)

        self.project_table = QTableWidget(0, 3)

        self.project_table.setHorizontalHeaderLabels([
            "PROJECT NAME",
            "LAST OPENED",
            "ACTION"
        ])

        self.project_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        self.project_table.verticalHeader().setVisible(False)
        self.project_table.setMinimumHeight(130)
        self.project_table.setAlternatingRowColors(True)
        self.project_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )

        recent_layout.addWidget(self.project_table)

        content_layout.addWidget(recent_panel)

        self.show_empty_projects()

        # =====================================
        # QUICK INFORMATION
        # =====================================

        info_heading = QLabel("Analysis Capabilities")
        info_heading.setObjectName("SectionTitle")

        content_layout.addWidget(info_heading)

        features = [
            ("01", "Structural Analysis",
             "Evaluate structural response under applied loads."),

            ("02", "Wind Loading",
             "Study the effects of wind loads on the turbine."),

            ("03", "Stress & Failure Analysis",
             "Investigate stress distribution and failure."),

            ("04", "3D Visualisation",
             "Visualise geometry and analysis results.")
        ]

        info_grid = QGridLayout()
        info_grid.setSpacing(14)

        for index, (number, title, description) in enumerate(features):

            panel = QFrame()
            panel.setObjectName("Panel")

            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(18, 15, 18, 15)
            panel_layout.setSpacing(8)

            number_label = QLabel(number)
            number_label.setStyleSheet(
                "color: #00B8D9; font-size: 13px; font-weight: bold;"
            )

            title_label = QLabel(title)
            title_label.setObjectName("SectionTitle")

            description_label = QLabel(description)
            description_label.setObjectName("SecondaryText")
            description_label.setWordWrap(True)

            panel_layout.addWidget(number_label)
            panel_layout.addWidget(title_label)
            panel_layout.addWidget(description_label)

            info_grid.addWidget(
                panel,
                index // 2,
                index % 2
            )

        content_layout.addLayout(info_grid)
        content_layout.addStretch()

        # =====================================
        # NAVIGATION CONNECTIONS
        # =====================================

        self.home_btn.clicked.connect(self.show_home)
        self.projects_btn.clicked.connect(self.show_projects)
        self.settings_btn.clicked.connect(self.show_settings)

    # =====================================
    # NAVIGATION BUTTON
    # =====================================

    def create_nav_button(self, text, active=False):

        button = QPushButton(text)
        button.setMinimumHeight(45)
        button.setCursor(Qt.PointingHandCursor)

        if active:
            button.setObjectName("ActiveNavButton")
        else:
            button.setObjectName("NavButton")

        return button

    # =====================================
    # ACTION CARD
    # =====================================

    def create_action_card(
        self, icon, title, description, button_text
    ):

        card = QFrame()
        card.setObjectName("ActionCard")
        card.setMinimumHeight(210)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(
            "font-size: 30px; color: #00B8D9;"
        )

        heading = QLabel(title)
        heading.setObjectName("SectionTitle")

        description_label = QLabel(description)
        description_label.setObjectName("SecondaryText")
        description_label.setWordWrap(True)

        button = QPushButton(button_text)
        button.setObjectName("PrimaryButton")
        button.setMinimumHeight(42)
        button.setCursor(Qt.PointingHandCursor)

        layout.addWidget(icon_label)
        layout.addWidget(heading)
        layout.addWidget(description_label)
        layout.addStretch()
        layout.addWidget(button)

        card.button = button

        return card

    # =====================================
    # RECENT PROJECTS
    # =====================================

    def show_empty_projects(self):

        self.project_table.setRowCount(1)

        self.project_table.setItem(
            0, 0, QTableWidgetItem("No recent projects")
        )

        self.project_table.setItem(
            0, 1, QTableWidgetItem("-")
        )

        self.project_table.setItem(
            0, 2, QTableWidgetItem("-")
        )

    # =====================================
    # NAVIGATION ACTIONS
    # =====================================

    def show_home(self):
        pass

    def show_projects(self):

        QMessageBox.information(
            self,
            "Projects",
            "Project management will be implemented next."
        )

    def show_settings(self):

        QMessageBox.information(
            self,
            "Settings",
            "Application settings will be implemented next."
        )