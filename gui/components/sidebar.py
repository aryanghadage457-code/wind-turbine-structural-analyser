from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QLabel
)


class Sidebar(QWidget):

    def __init__(self):
        super().__init__()

        self.setFixedWidth(220)

        layout = QVBoxLayout(self)

        title = QLabel("TURBINE ANALYSER")
        title.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: white;
            padding: 15px;
        """)

        layout.addWidget(title)

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
                text-align: left;
                padding-left: 20px;
                font-size: 14px;
            }

            QPushButton:hover {
                background-color: #26374d;
            }
        """)