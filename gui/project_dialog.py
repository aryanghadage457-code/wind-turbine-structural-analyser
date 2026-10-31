import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QFormLayout
)


class ProjectDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle("Create New Project")
        self.setFixedSize(520, 300)

        self.project_data = None

        self.setStyleSheet("""
            QDialog {
                background-color: #202329;
                color: white;
            }

            QLabel {
                color: #F2F3F5;
            }

            QLineEdit {
                background-color: #343941;
                color: white;
                border: 1px solid #414751;
                border-radius: 5px;
                padding: 9px;
            }

            QPushButton {
                background-color: #343941;
                color: white;
                border: 1px solid #414751;
                border-radius: 5px;
                padding: 9px 15px;
            }

            QPushButton:hover {
                background-color: #0078D4;
            }

            QPushButton#PrimaryButton {
                background-color: #0078D4;
                border: none;
            }

            QPushButton#PrimaryButton:hover {
                background-color: #0063B1;
            }
        """)

        self.create_interface()


    def create_interface(self):

        main_layout = QVBoxLayout(self)

        title = QLabel("Create New Project")
        title.setStyleSheet("""
            font-size: 21px;
            font-weight: bold;
        """)

        description = QLabel(
            "Enter your project details and choose a save location."
        )

        description.setStyleSheet("color: #A5ABB4;")

        main_layout.addWidget(title)
        main_layout.addWidget(description)

        main_layout.addSpacing(15)

        form = QFormLayout()

        # Project name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter project name")

        form.addRow("Project Name:", self.name_input)

        # Project location
        location_layout = QHBoxLayout()

        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText(
            "Select a folder using Browse..."
        )

        self.location_input.setReadOnly(True)
        self.location_input.setCursor(Qt.PointingHandCursor)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_location)

        location_layout.addWidget(self.location_input)
        location_layout.addWidget(browse_button)

        form.addRow("Location:", location_layout)

        main_layout.addLayout(form)

        main_layout.addStretch()

        # Buttons
        buttons = QHBoxLayout()

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        create_button = QPushButton("Create Project")
        create_button.setObjectName("PrimaryButton")
        create_button.clicked.connect(self.create_project)

        buttons.addStretch()
        buttons.addWidget(cancel_button)
        buttons.addWidget(create_button)

        main_layout.addLayout(buttons)


    def browse_location(self):

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Project Location"
        )

        if folder:
            self.location_input.setText(folder)


    def create_project(self):

        project_name = self.name_input.text().strip()
        project_location = self.location_input.text().strip()

        # Validate project name
        if not project_name:

            QMessageBox.warning(
                self,
                "Missing Project Name",
                "Please enter a project name."
            )

            return

        # Validate project location
        if not project_location:

            QMessageBox.warning(
                self,
                "Missing Location",
                "Please select a project location."
            )

            return

        # Validate project name as a folder name
        if (
            project_name in (".", "..")
            or Path(project_name).name != project_name
            or any(char in project_name for char in '<>:"/\\|?*')
        ):

            QMessageBox.warning(
                self,
                "Invalid Project Name",
                "Please enter a valid project name."
            )

            return

        project_path = Path(project_location) / project_name

        # Prevent overwriting an existing project
        if project_path.exists():

            QMessageBox.warning(
                self,
                "Project Already Exists",
                "A folder with this project name already exists. "
                "Please choose another name."
            )

            return

        # Store project information in memory only.
        # No folder or file is created at this stage.
        self.project_data = {

            "project_name": project_name,

            "project_path": str(project_path.resolve()),

            "created_on": datetime.now().isoformat(
                timespec="seconds"
            )

        }

        self.accept()