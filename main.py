import sys
import json
import shutil

from pathlib import Path
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QStackedWidget,
    QFileDialog,
    QMessageBox,
)

from gui.project_dialog import ProjectDialog
from gui.turbine_config_dialog import TurbineConfigDialog
from gui.components.viewport_3d import TurbineViewport
from gui.components.loading_dialog import LoadingOverlay

from gui.theme.styles import install_theme
from gui.start_page import StartPage
from gui.main_window import MainWindow

from project_manager import (
    get_valid_recent_projects,
    add_recent_project,
)


class Application(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Wind Turbine Structural Analyser")

        self.current_project = None
        self.workspace = None
        self._pending_viewport = None
        self._loading = None

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.start_page = StartPage()
        self.stack.addWidget(self.start_page)

        self.start_page.new_project_requested.connect(self.create_project)
        self.start_page.open_project_requested.connect(self.open_existing_project)

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

        config_dialog = TurbineConfigDialog(self)

        if not config_dialog.exec():

            return

        model_config = {
            "model_source": "builtin",
            "dimensions": config_dialog.dimensions
        }

        self.current_project = project_data

        try:
            self.save_project(model_config)
        except (OSError, ValueError, KeyError, TypeError) as error:
            QMessageBox.critical(
                self, "Project Creation Failed", f"Unable to save project:\n{error}"
            )
            self.current_project = None
            return

        self._begin_workspace(self.current_project)

    # ==========================================
    # SAVE PROJECT
    # ==========================================

    def save_project(self, model_config):
        if not self.current_project:
            raise ValueError("Project information is missing.")

        project_path = Path(self.current_project["project_path"])

        if project_path.exists():
            raise FileExistsError("The selected project folder already exists.")

        folders = ["geometry", "mesh", "results", "reports", "config"]

        try:
            project_path.mkdir(parents=True, exist_ok=False)
            for folder in folders:
                (project_path / folder).mkdir(exist_ok=True)

            project_metadata = {
                **self.current_project,
                "model_source": model_config["model_source"],
            }

            with open(project_path / "project.json", "w", encoding="utf-8") as file:
                json.dump(project_metadata, file, indent=4)

            with open(
                project_path / "config" / "model_config.json", "w", encoding="utf-8"
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
                self, "Project Not Found",
                "The project configuration file could not be found.",
            )
            self.refresh_recent_projects()
            return

        try:
            with open(metadata_file, "r", encoding="utf-8") as file:
                self.current_project = json.load(file)

            self.current_project["project_path"] = str(project_path.resolve())

            projects = add_recent_project(self.current_project)
            self.start_page.update_recent_projects(projects)

        except (OSError, json.JSONDecodeError, KeyError) as error:
            QMessageBox.critical(self, "Project Error", f"Unable to open project:\n{error}")
            return

        self._begin_workspace(self.current_project)

    # ==========================================
    # BUILD GEOMETRY, THEN OPEN THE WORKSPACE
    # ==========================================

    def _begin_workspace(self, project_data):
        self.start_page.setEnabled(False)

        self._loading = LoadingOverlay(self, "Starting turbine geometry generation...")
        self._loading.show()
        self._loading.center_on(self)

        self._pending_viewport = TurbineViewport(project_data)
        self._pending_viewport.status_message.connect(self._loading.set_message)
        self._pending_viewport.build_finished.connect(
            lambda success: self._on_geometry_prebuilt(success, project_data)
        )
        self._pending_viewport.ensure_geometry_loaded()

    def _on_geometry_prebuilt(self, success, project_data):
        if self._loading is not None:
            self._loading.close()
            self._loading = None
        self.start_page.setEnabled(True)

        viewport = self._pending_viewport
        self._pending_viewport = None

        # If a workspace was already open (e.g. re-opening another project
        # without going back to Start first), clean it up first.
        if self.workspace is not None:
            self.stack.removeWidget(self.workspace)
            self.workspace.shutdown()
            self.workspace.deleteLater()
            self.workspace = None

        self.workspace = MainWindow(project_data, viewport=viewport)
        self.workspace.close_requested.connect(self._return_to_start)
        self.workspace.project_action.connect(self._on_workspace_project_action)

        self.stack.addWidget(self.workspace)
        self.stack.setCurrentWidget(self.workspace)

        project_name = project_data.get("project_name", "Project")
        self.setWindowTitle(f"{project_name} - Wind Turbine Structural Analyser")

        if not success:
            self.workspace.dock.add_message(
                "Geometry generation failed. See the message above for details.",
                "error",
            )

    def _return_to_start(self):
        if self.workspace is not None:
            self.stack.setCurrentWidget(self.start_page)
            self.stack.removeWidget(self.workspace)
            self.workspace.shutdown()
            self.workspace.deleteLater()
            self.workspace = None

        self.setWindowTitle("Wind Turbine Structural Analyser")
        self.refresh_recent_projects()

    def _on_workspace_project_action(self, action_id):
        self._return_to_start()
        if action_id == "project.new":
            self.create_project()
        elif action_id == "project.open":
            folder = QFileDialog.getExistingDirectory(self, "Open Project")
            if folder:
                self.open_existing_project(folder)

    # ==========================================
    # CLEANUP
    # ==========================================

    def closeEvent(self, event):
        if self.workspace is not None:
            self.workspace.shutdown()
        if self._pending_viewport is not None:
            self._pending_viewport.shutdown()
        super().closeEvent(event)


# ==============================================
# APPLICATION ENTRY POINT
# ==============================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    install_theme(app)

    window = Application()
    window.showMaximized()

    sys.exit(app.exec())