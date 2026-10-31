from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox,
    QStackedWidget
)

from PySide6.QtCore import Qt, Signal


class StartPage(QWidget):

    new_project_requested = Signal()
    import_step_requested = Signal()
    open_project_requested = Signal(str)

    def __init__(self):
        super().__init__()

        self.setObjectName("StartPage")

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # =====================================
        # SIDEBAR
        # =====================================

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(230)

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(15, 35, 15, 20)
        sidebar_layout.setSpacing(12)

        sidebar_layout.addSpacing(20)

        self.home_btn = self.create_nav_button("⌂    Home", True)
        self.projects_btn = self.create_nav_button("▣    Projects")
        self.settings_btn = self.create_nav_button("⚙    Settings")

        sidebar_layout.addWidget(self.home_btn)
        sidebar_layout.addWidget(self.projects_btn)
        sidebar_layout.addWidget(self.settings_btn)

        sidebar_layout.addStretch()

        root.addWidget(sidebar)

        # =====================================
        # PAGE CONTAINER
        # =====================================

        self.pages = QStackedWidget()

        self.home_page = self.create_home_page()
        self.projects_page = self.create_projects_page()
        self.settings_page = self.create_settings_page()

        self.pages.addWidget(self.home_page)
        self.pages.addWidget(self.projects_page)
        self.pages.addWidget(self.settings_page)

        root.addWidget(self.pages)

        # =====================================
        # NAVIGATION CONNECTIONS
        # =====================================

        self.home_btn.clicked.connect(
            lambda: self.change_page(0)
        )

        self.projects_btn.clicked.connect(
            lambda: self.change_page(1)
        )

        self.settings_btn.clicked.connect(
            lambda: self.change_page(2)
        )

    # =====================================
    # NAVIGATION BUTTON
    # =====================================

    def create_nav_button(self, text, active=False):

        button = QPushButton(text)
        button.setMinimumHeight(46)
        button.setCursor(Qt.PointingHandCursor)

        button.setObjectName(
            "ActiveNavButton" if active else "NavButton"
        )

        return button

    # =====================================
    # CHANGE PAGE
    # =====================================

    def change_page(self, index):

        self.pages.setCurrentIndex(index)

        buttons = [
            self.home_btn,
            self.projects_btn,
            self.settings_btn
        ]

        for i, button in enumerate(buttons):

            button.setObjectName(
                "ActiveNavButton" if i == index else "NavButton"
            )

            button.style().unpolish(button)
            button.style().polish(button)

    # =====================================
    # PAGE HEADER
    # =====================================

    def create_header(self, title, subtitle):

        layout = QVBoxLayout()

        heading = QLabel(title)
        heading.setObjectName("PageTitle")

        description = QLabel(subtitle)
        description.setObjectName("SecondaryText")
        description.setWordWrap(True)

        layout.addWidget(heading)
        layout.addWidget(description)

        return layout

    # =====================================
    # HOME PAGE
    # =====================================

    def create_home_page(self):

        page = QWidget()

        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 35, 40, 35)
        layout.setSpacing(25)

        # Header

        layout.addLayout(
            self.create_header(
                "Wind Turbine Structural Analyser",
                "A platform for structural design, simulation and engineering analysis."
            )
        )

        layout.addSpacing(10)

        intro_title = QLabel("About This Software")
        intro_title.setObjectName("SectionTitle")

        intro = QLabel(
            "Wind Turbine Structural Analyser is a mechanical engineering "
            "application designed to study the structural behaviour of "
            "wind turbine components under different loading conditions. "
            "It helps users investigate deformation, stress distribution "
            "and structural failure."
        )

        intro.setObjectName("SecondaryText")
        intro.setWordWrap(True)

        layout.addWidget(intro_title)
        layout.addWidget(intro)

        layout.addSpacing(15)

        capabilities_title = QLabel("What Can You Do?")
        capabilities_title.setObjectName("SectionTitle")

        layout.addWidget(capabilities_title)

        features = [
            (
                "01",
                "Structural Analysis",
                "Evaluate the structural response of wind turbine components."
            ),
            (
                "02",
                "Wind Loading",
                "Study the effect of wind forces on turbine structures."
            ),
            (
                "03",
                "Stress & Failure Analysis",
                "Investigate stress, strain and possible failure conditions."
            ),
            (
                "04",
                "3D Visualisation",
                "View turbine geometry and visualise structural analysis results."
            )
        ]

        grid = QGridLayout()
        grid.setSpacing(16)

        for i, (number, title, description) in enumerate(features):

            card = QFrame()
            card.setObjectName("Panel")

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(20, 20, 20, 20)
            card_layout.setSpacing(10)

            number_label = QLabel(number)
            number_label.setStyleSheet(
                "color: #00B8D9; font-size: 15px; font-weight: bold;"
            )

            title_label = QLabel(title)
            title_label.setObjectName("SectionTitle")

            description_label = QLabel(description)
            description_label.setObjectName("SecondaryText")
            description_label.setWordWrap(True)

            card_layout.addWidget(number_label)
            card_layout.addWidget(title_label)
            card_layout.addWidget(description_label)
            card_layout.addStretch()

            grid.addWidget(card, i // 2, i % 2)

        layout.addLayout(grid)

        layout.addStretch()

        return page

    # =====================================
    # PROJECTS PAGE
    # =====================================

    def create_projects_page(self):

        page = QWidget()

        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 35, 40, 35)
        layout.setSpacing(22)

        layout.addLayout(
            self.create_header(
                "Projects",
                "Create a new analysis project or continue working on an existing one."
            )
        )

        # Action cards

        cards = QGridLayout()
        cards.setSpacing(18)

        new_card = self.create_action_card(
            "＋",
            "NEW PROJECT",
            "Create a new wind turbine structural analysis project.",
            "Create New Project"
        )

        import_card = self.create_action_card(
            "⇧",
            "IMPORT STEP MODEL",
            "Import an existing 3D CAD model for structural analysis.",
            "Browse STEP Files"
        )

        new_card.button.clicked.connect(
            self.new_project_requested.emit
        )

        import_card.button.clicked.connect(
            self.import_step_requested.emit
        )

        cards.addWidget(new_card, 0, 0)
        cards.addWidget(import_card, 0, 1)

        layout.addLayout(cards)

        # Recent projects

        recent_title = QLabel("Recent Projects")
        recent_title.setObjectName("SectionTitle")

        layout.addWidget(recent_title)

        panel = QFrame()
        panel.setObjectName("Panel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(15, 15, 15, 15)

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

        self.project_table.setAlternatingRowColors(True)

        self.project_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )

        self.project_table.setMinimumHeight(220)

        panel_layout.addWidget(self.project_table)

        layout.addWidget(panel)

        self.show_empty_projects()

        layout.addStretch()

        return page

    # =====================================
    # ACTION CARD
    # =====================================

    def create_action_card(
        self, icon, title, description, button_text
    ):

        card = QFrame()
        card.setObjectName("ActionCard")
        card.setMinimumHeight(205)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(12)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(
            "color: #00B8D9; font-size: 30px;"
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

        card_layout.addWidget(icon_label)
        card_layout.addWidget(heading)
        card_layout.addWidget(description_label)
        card_layout.addStretch()
        card_layout.addWidget(button)

        card.button = button

        return card

    # =====================================
    # SETTINGS PAGE
    # =====================================

    def create_settings_page(self):

        page = QWidget()

        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 35, 40, 35)
        layout.setSpacing(20)

        layout.addLayout(
            self.create_header(
                "Settings",
                "Manage application preferences and configuration."
            )
        )

        message = QLabel(
            "Application settings will be available here."
        )

        message.setObjectName("SecondaryText")

        layout.addWidget(message)

        layout.addStretch()

        return page

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