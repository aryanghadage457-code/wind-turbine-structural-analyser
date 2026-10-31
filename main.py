from gui.theme.styles import APP_STYLESHEET 
import sys

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QFileDialog,
    QMessageBox
)

from gui.start_page import StartPage
from gui.main_window import MainWindow


class Application(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "Wind Turbine Structural Analyser"
        )

        self.resize(1450, 900)

        # Display Start Screen
        self.start_page = StartPage()

        self.setCentralWidget(self.start_page)

        # Connect buttons
        self.start_page.new_project_requested.connect(
            self.create_project
        )

        self.start_page.import_step_requested.connect(
            self.import_step
        )

    def create_project(self):

        # Temporary navigation for now.
        # We will create the actual project dialog next.

        self.open_workspace()

    def import_step(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import STEP Model",
            "",
            "STEP Files (*.step *.stp)"
        )

        if file_path:

            QMessageBox.information(
                self,
                "STEP Model Selected",
                f"Selected model:\n{file_path}\n\n"
                "STEP processing will be connected next."
            )

    def open_workspace(self):

        self.workspace = MainWindow()

        self.workspace.show()

        self.close()


if __name__ == "__main__":

    app = QApplication(sys.argv)

    app.setStyleSheet(APP_STYLESHEET)   

    window = Application()

    window.show()

    sys.exit(app.exec())