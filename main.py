"""Application entry point: ONE window holding the Start page and the workspace.

    Start page  --(New / Open project)-->  Engineering workspace
    Start page  <--(File > Close Project)--  Engineering workspace

The window opens maximized directly (no timers, no resize flicker).
"""
import json
import shutil
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
)

from gui.main_window import MainWindow
from gui.model_source_dialog import ModelSourceDialog
from gui.project_dialog import ProjectDialog
from gui.start_page import StartPage
from gui.theme.styles import install_theme
from gui.turbine_config_dialog import TurbineConfigDialog
from project_manager import add_recent_project, get_valid_recent_projects

APP_TITLE = "Wind Turbine Structural Analyser"


class Application(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1100, 700)

        self.current_project = None
        self.workspace = None

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.start_page = StartPage()
        self.stack.addWidget(self.start_page)

        self.start_page.new_project_requested.connect(self.create_project)
        self.start_page.open_project_requested.connect(
            self.open_existing_project
        )

        self.refresh_recent_projects()

    # ==========================================
    # REFRESH RECENT PROJECTS
    # ==========================================

    def refresh_recent_projects(self):

        self.start_page.update_recent_projects(get_valid_recent_projects())

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

            self.open_workspace(created=True)

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
            raise ValueError("Project information is missing.")

        project_path = Path(self.current_project["project_path"])

        if project_path.exists():
            raise FileExistsError(
                "The selected project folder already exists."
            )

        folders = ["geometry", "mesh", "results", "reports", "config"]

        try:

            project_path.mkdir(parents=True, exist_ok=False)

            for folder in folders:
                (project_path / folder).mkdir(exist_ok=True)

            project_metadata = {
                **self.current_project,
                "model_source": model_config["model_source"]
            }

            with open(
                project_path / "project.json", "w", encoding="utf-8"
            ) as file:
                json.dump(project_metadata, file, indent=4)

            with open(
                project_path / "config" / "model_config.json",
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(model_config, file, indent=4)

            self.current_project = project_metadata

            projects = add_recent_project(self.current_project)

            self.start_page.update_recent_projects(projects)

        except Exception:

            if project_path.exists():
                shutil.rmtree(project_path, ignore_errors=True)

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

            with open(metadata_file, "r", encoding="utf-8") as file:
                self.current_project = json.load(file)

            self.current_project["project_path"] = str(
                project_path.resolve()
            )

            projects = add_recent_project(self.current_project)

            self.start_page.update_recent_projects(projects)

            self.open_workspace()

        except (OSError, json.JSONDecodeError, KeyError) as error:

            QMessageBox.critical(
                self,
                "Project Error",
                f"Unable to open project:\n{error}"
            )

    # ==========================================
    # WORKSPACE <-> START PAGE
    # ==========================================

    def open_workspace(self, created=False):

        self._discard_workspace()

        self.workspace = MainWindow(self.current_project)
        self.workspace.close_requested.connect(self.close_project)
        self.workspace.project_action.connect(self.on_project_action)

        self.stack.addWidget(self.workspace)
        self.stack.setCurrentWidget(self.workspace)

        name = self.current_project.get("project_name", "Project")
        self.setWindowTitle(f"{name} - {APP_TITLE}")

        if created:
            self.workspace.dock.add_message(
                "Project created successfully."
            )
            self.workspace.status.set_status("Project created", "ready")

    def close_project(self):

        self._discard_workspace()

        self.current_project = None
        self.setWindowTitle(APP_TITLE)

        self.refresh_recent_projects()

        self.stack.setCurrentWidget(self.start_page)

    def _discard_workspace(self):

        if self.workspace is not None:

            self.stack.removeWidget(self.workspace)
            self.workspace.deleteLater()
            self.workspace = None

    def on_project_action(self, action_id):
        """File menu: New Project / Open Project from inside the workspace."""

        if action_id == "project.new":

            self.close_project()
            self.create_project()

        elif action_id == "project.open":

            folder = QFileDialog.getExistingDirectory(
                self, "Open Project Folder"
            )

            if folder:
                self.close_project()
                self.open_existing_project(folder)


# ==============================================
# APPLICATION ENTRY POINT
# ==============================================

if __name__ == "__main__":

    app = QApplication(sys.argv)

    install_theme(app)

    window = Application()

    # Open maximized directly: no timers, no visible resize.
    window.showMaximized()

    sys.exit(app.exec())