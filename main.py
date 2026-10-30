import sys
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QWidget,
    QVBoxLayout
)
from PySide6.QtCore import Qt


class TurbineAnalyzer(QMainWindow):

    def __init__(self):
        super().__init__()

        # Window properties
        self.setWindowTitle("Wind Turbine Structural Analyser")
        self.setGeometry(200, 100, 1000, 650)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Layout
        layout = QVBoxLayout()

        # Title
        title = QLabel("WIND TURBINE STRUCTURAL ANALYSER")
        title.setAlignment(Qt.AlignCenter)

        title.setStyleSheet("""
            font-size: 26px;
            font-weight: bold;
            color: white;
            background-color: #183153;
            padding: 25px;
        """)

        layout.addWidget(title)

        # Welcome message
        message = QLabel("Welcome to the Structural Analysis Application")
        message.setAlignment(Qt.AlignCenter)

        message.setStyleSheet("""
            font-size: 18px;
            color: #333333;
            padding: 30px;
        """)

        layout.addWidget(message)

        central_widget.setLayout(layout)


# Run application
app = QApplication(sys.argv)

window = TurbineAnalyzer()
window.show()

sys.exit(app.exec())