from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QStackedWidget
)

from gui.components.sidebar import Sidebar


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Wind Turbine Structural Analyser"
        )

        self.resize(1400, 850)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()

        # Main workspace
        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)

        # Top bar
        topbar = QLabel("Wind Turbine Structural Analyser")
        topbar.setFixedHeight(65)

        topbar.setStyleSheet("""
            color: white;
            font-size: 20px;
            font-weight: bold;
            padding-left: 25px;
            background-color: #202c3b;
        """)

        workspace_layout.addWidget(topbar)

        # Pages
        self.pages = QStackedWidget()

        dashboard = QLabel("Welcome to the Dashboard")
        dashboard.setStyleSheet(
            "color: white; font-size: 25px;"
        )

        self.pages.addWidget(dashboard)

        workspace_layout.addWidget(self.pages)

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(workspace)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #101923;
            }
        """)