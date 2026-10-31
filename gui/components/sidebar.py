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
        layout.setContentsMargins(12, 20, 12, 20)
        layout.setSpacing(8)

        # Application title
        title = QLabel("WIND TURBINE")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            color: #F2F3F5;
            font-size: 17px;
            font-weight: bold;
            padding: 15px 5px 5px 5px;
        """)

        subtitle = QLabel("STRUCTURAL ANALYSER")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("""
            color: #00B8D9;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
            padding-bottom: 25px;
        """)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Navigation
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
            button.setMinimumHeight(46)
            button.setCursor(Qt.PointingHandCursor)
            button.setCheckable(True)

            layout.addWidget(button)

            self.buttons[page] = button

        layout.addStretch()

        # Footer
        footer = QLabel("Version 1.0")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("""
            color: #737D89;
            font-size: 11px;
            padding: 10px;
        """)

        layout.addWidget(footer)

        self.setStyleSheet("""
            QWidget {
                background-color: #202329;
            }

            QPushButton {
                color: #A5ABB4;
                background-color: transparent;
                border: none;
                border-radius: 6px;
                text-align: left;
                padding-left: 22px;
                font-size: 14px;
            }

            QPushButton:hover {
                background-color: #343941;
                color: white;
            }

            QPushButton:checked {
                background-color: #173B57;
                color: #FFFFFF;
                border-left: 4px solid #00B8D9;
                font-weight: bold;
                padding-left: 18px;
            }
        """)

    def set_active_page(self, page_name):

        for name, button in self.buttons.items():

            button.setChecked(name == page_name)