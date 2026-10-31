from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QStackedWidget
)

from PySide6.QtCore import Qt

from gui.components.sidebar import Sidebar
from gui.dashboard import DashboardPage


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Wind Turbine Structural Analyser"
        )

        self.resize(1400, 850)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        # Workspace
        workspace = QWidget()

        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        # Top bar
        self.topbar = QLabel("Dashboard")
        self.topbar.setFixedHeight(65)
        self.topbar.setAlignment(
            Qt.AlignVCenter | Qt.AlignLeft
        )

        self.topbar.setStyleSheet("""
            background-color: #202c3b;
            color: white;
            font-size: 21px;
            font-weight: bold;
            padding-left: 25px;
        """)

        workspace_layout.addWidget(self.topbar)

        # Stacked widget
        self.pages = QStackedWidget()

        workspace_layout.addWidget(self.pages)

        main_layout.addWidget(workspace)

        # Page names and storage
        self.page_names = [
            "Dashboard",
            "Geometry",
            "Materials",
            "Environment",
            "Analysis",
            "Results"
        ]

        self.page_widgets = {}

        # Create pages
        for name in self.page_names:

            if name == "Dashboard":
                page = DashboardPage()

            else:
                page = self.create_page(name)

            self.pages.addWidget(page)

            self.page_widgets[name] = page

        # Connect navigation buttons
        for name in self.page_names:

            self.sidebar.buttons[name].clicked.connect(
                lambda checked=False, page_name=name:
                self.change_page(page_name)
            )

        # Open Dashboard by default
        self.change_page("Dashboard")

    def create_page(self, name):

        page = QWidget()

        layout = QVBoxLayout(page)

        title = QLabel(name)
        title.setAlignment(Qt.AlignCenter)

        title.setStyleSheet("""
            color: white;
            font-size: 30px;
            font-weight: bold;
        """)

        description = QLabel(
            f"Welcome to the {name} section"
        )

        description.setAlignment(Qt.AlignCenter)

        description.setStyleSheet("""
            color: #91a4b8;
            font-size: 16px;
        """)

        layout.addWidget(title)
        layout.addWidget(description)

        page.setStyleSheet("""
            background-color: #101923;
        """)

        return page

    def change_page(self, name):

        page = self.page_widgets[name]

        self.pages.setCurrentWidget(page)

        self.topbar.setText(name)