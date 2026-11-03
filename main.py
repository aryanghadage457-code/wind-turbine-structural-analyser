import sys
import json
import shutil

from pathlib import Path
from PySide6.QtCore import QTimer, Qt

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QFileDialog,
    QMessageBox
)

from gui.project_dialog import ProjectDialog
from gui.model_source_dialog import ModelSourceDialog
from gui.turbine_config_dialog import TurbineConfigDialog

from gui.theme.styles import install_theme
from gui.start_page import StartPage
from gui.main_window import MainWindow

from project_manager import (
    get_valid_recent_projects,
    add_recent_project
)


class Application(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "Wind Turbine Structural Analyser"
        )

        

        self.current_project = None

        self.start_page = StartPage()

        self.setCentralWidget(self.start_page)

        self.start_page.new_project_requested.connect(
            self.create_project
        )

        self.start_page.open_project_requested.connect(
            self.open_existing_project
        )

        self.refresh_recent_projects()

    # ==========================================
    # REFRESH RECENT PROJECTS
    # ==========================================

    def refresh_recent_projects(self):

        projects = get_valid_recent_projects()

        self.start_page.update_recent_projects(projects)

    # ==========================================
    # CREATE NEW PROJECT
    # ==========================================

    def create_project(self):

        self.current_project = None

        project_dialog = ProjectDialog(self)

        if not project_dialog.exec():

            return

        project_data = project_dialog.project_data

        if not project_data:

            return

        # Select model source
        source_dialog = ModelSourceDialog(self)

        if not source_dialog.exec():

            return

        model_source = source_dialog.model_source

        model_config = {}

        # Built-in CAD model
        if model_source == "builtin":

            config_dialog = TurbineConfigDialog(self)

            if not config_dialog.exec():

                return

            model_config = {
                "model_source": "builtin",
                "dimensions": config_dialog.dimensions
            }

        # Imported STEP model
        elif model_source == "step":

            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Import STEP Model",
                "",
                "STEP Files (*.step *.stp)"
            )

            if not file_path:

                return

            step_path = Path(file_path)

            if not step_path.is_file():

                QMessageBox.warning(
                    self,
                    "Invalid STEP File",
                    "The selected STEP file does not exist."
                )

                return

            model_config = {
                "model_source": "step",
                "step_file": str(step_path.resolve())
            }

        else:

            QMessageBox.warning(
                self,
                "Model Source Error",
                "Please select a valid model source."
            )

            return

        # Save project
        self.current_project = project_data

        try:

            self.save_project(model_config)

            QMessageBox.information(
                self,
                "Project Created",
                "Your project has been created successfully."
            )

            self.open_workspace()

        except (OSError, ValueError, KeyError, TypeError) as error:

            QMessageBox.critical(
                self,
                "Project Creation Failed",
                f"Unable to save project:\n{error}"
            )

            self.current_project = None

    # ==========================================
    # SAVE PROJECT
    # ==========================================

    def save_project(self, model_config):

        if not self.current_project:

            raise ValueError(
                "Project information is missing."
            )

        project_path = Path(
            self.current_project["project_path"]
        )

        if project_path.exists():

            raise FileExistsError(
                "The selected project folder already exists."
            )

        folders = [
            "geometry",
            "mesh",
            "results",
            "reports",
            "config"
        ]

        try:

            project_path.mkdir(
                parents=True,
                exist_ok=False
            )

            for folder in folders:

                (project_path / folder).mkdir(
                    exist_ok=True
                )

            project_metadata = {
                **self.current_project,
                "model_source": model_config["model_source"]
            }

            with open(
                project_path / "project.json",
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    project_metadata,
                    file,
                    indent=4
                )

            with open(
                project_path / "config" / "model_config.json",
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    model_config,
                    file,
                    indent=4
                )

            self.current_project = project_metadata

            projects = add_recent_project(
                self.current_project
            )

            self.start_page.update_recent_projects(projects)

        except Exception:

            if project_path.exists():

                shutil.rmtree(
                    project_path,
                    ignore_errors=True
                )

            raise

    # ==========================================
    # OPEN EXISTING PROJECT
    # ==========================================

    def open_existing_project(self, project_path):

        project_path = Path(project_path)

        metadata_file = project_path / "project.json"

        if not metadata_file.is_file():

            QMessageBox.warning(
                self,
                "Project Not Found",
                "The project configuration file could not be found."
            )

            self.refresh_recent_projects()

            return

        try:

            with open(
                metadata_file,
                "r",
                encoding="utf-8"
            ) as file:

                self.current_project = json.load(file)

            self.current_project["project_path"] = str(
                project_path.resolve()
            )

            projects = add_recent_project(
                self.current_project
            )

            self.start_page.update_recent_projects(projects)

            self.open_workspace()

        except (OSError, json.JSONDecodeError, KeyError) as error:

            QMessageBox.critical(
                self,
                "Project Error",
                f"Unable to open project:\n{error}"
            )

    # ==========================================
    # OPEN ENGINEERING WORKSPACE
    # ==========================================

    def open_workspace(self):

        self.workspace = MainWindow(
            self.current_project
        )

        self.workspace.show()

        QTimer.singleShot(
            100,
            self.workspace.showMaximized
        )

        self.close()

# ==============================================
# APPLICATION ENTRY POINT
# ==============================================

if __name__ == "__main__":

    app = QApplication(sys.argv)

    install_theme(app)

    window = Application()

    # First display the window
    window.show()

    # Then maximize it after the window is displayed
    QTimer.singleShot(
        100,
        lambda: window.setWindowState(
            window.windowState() | Qt.WindowMaximized
        )
    )

    sys.exit(app.exec())