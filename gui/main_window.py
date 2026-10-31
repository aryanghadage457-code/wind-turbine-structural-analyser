from gui.dashboard import DashboardPage

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


class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        # Window properties
        self.setWindowTitle(
            "Wind Turbine Structural Analyser"
        )

        self.resize(1400, 850)

        # Main central widget
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)

        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -------------------------
        # SIDEBAR
        # -------------------------

        self.sidebar = Sidebar()

        main_layout.addWidget(self.sidebar)

        # -------------------------
        # MAIN WORKSPACE
        # -------------------------

        workspace = QWidget()

        workspace_layout = QVBoxLayout(workspace)

        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        # Top navigation bar
        self.topbar = QLabel("Dashboard")

        self.topbar.setFixedHeight(65)

        self.topbar.setStyleSheet("""
            color: white;
            font-size: 20px;
            font-weight: bold;
            padding-left: 25px;
            background-color: #202c3b;
        """)

        self.topbar.setAlignment(
            Qt.AlignVCenter | Qt.AlignLeft
        )

        workspace_layout.addWidget(self.topbar)

        # -------------------------
        # STACKED WIDGET
        # -------------------------

        self.pages = QStackedWidget()

        self.pages.setStyleSheet("""
            QStackedWidget {
                background-color: #101923;
            }
        """)

        workspace_layout.addWidget(self.pages)

        main_layout.addWidget(workspace)

        # -------------------------
        # CREATE ALL PAGES
        # -------------------------

        self.page_names = [
            "Dashboard",
            "Geometry",
            "Materials",
            "Environment",
            "Analysis",
            "Results"
        ]

        for name in self.page_names:
                if name == "Dashboard":
                     page = DashboardPage()

                else:
                    page = self.create_page(name)

                    self.pages.addWidget(page)

        # -------------------------
        # CONNECT SIDEBAR BUTTONS
        # -------------------------

        for index, name in enumerate(self.page_names):

            self.sidebar.buttons[name].clicked.connect(
                lambda checked=False, i=index, n=name:
                self.change_page(i, n)
            )

        # Initial page
        self.change_page(0, "Dashboard")

    # -------------------------
    # CREATE PAGE
    # -------------------------

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
            color: #9caec2;
            font-size: 16px;
        """)

        layout.addWidget(title)
        layout.addWidget(description)

        return page

    # -------------------------
    # CHANGE PAGE
    # -------------------------

    def change_page(self, index, name):

        self.pages.setCurrentIndex(index)

        self.topbar.setText(name)