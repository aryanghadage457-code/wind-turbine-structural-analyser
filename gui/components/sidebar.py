from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QLabel
)

from PySide6.QtCore import Qt


class Sidebar(QWidget):

    def __init__(self):
        super().__init__()

        self.setFixedWidth(230)

        layout = QVBoxLayout(self)

        layout.setContentsMargins(10, 20, 10, 20)
        layout.setSpacing(10)

        # Application title
        title = QLabel("TURBINE ANALYSER")

        title.setAlignment(Qt.AlignCenter)

        title.setStyleSheet("""
            color: white;
            font-size: 17px;
            font-weight: bold;
            padding: 15px;
        """)

        layout.addWidget(title)

        # Navigation buttons
        self.buttons = {}

        pages = [
            "Dashboard",
            "Geometry",
            "Materials",
            "Environment",
            "Analysis",
            "Results"
        ]

        for page in pages:

            button = QPushButton(page)

            button.setMinimumHeight(45)

            button.setCursor(Qt.PointingHandCursor)

            layout.addWidget(button)

            self.buttons[page] = button

        layout.addStretch()

        self.setStyleSheet("""
            QWidget {
                background-color: #17212f;
            }

            QPushButton {
                color: #dce6f2;
                background-color: transparent;
                border: none;
                border-radius: 6px;
                text-align: left;
                padding-left: 20px;
                font-size: 14px;
            }

            QPushButton:hover {
                background-color: #30435c;
            }
        """)