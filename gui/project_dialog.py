import os
import json

from datetime import datetime

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

from PySide6.QtCore import Qt


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

        description.setStyleSheet(
            "color: #A5ABB4;"
        )

        main_layout.addWidget(title)
        main_layout.addWidget(description)

        main_layout.addSpacing(15)

        form = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(
            "Enter project name"
        )

        form.addRow("Project Name:", self.name_input)

        location_layout = QHBoxLayout()

        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText(
    "Select a folder using Browse..."
)

# Prevent manual typing
        self.location_input.setReadOnly(True)

                    # Show selected folder path
        self.location_input.setCursor(Qt.PointingHandCursor)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(
            self.browse_location
        )

        location_layout.addWidget(self.location_input)
        location_layout.addWidget(browse_button)

        form.addRow("Location:", location_layout)

        main_layout.addLayout(form)

        main_layout.addStretch()

        buttons = QHBoxLayout()

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        create_button = QPushButton("Create Project")
        create_button.setObjectName("PrimaryButton")
        create_button.clicked.connect(
            self.create_project
        )

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
        location = self.location_input.text().strip()

        if not project_name or not location:

            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter both project name and location."
            )

            return

        # Validate project name
        if (
            project_name in (".", "..")
            or any(char in project_name for char in '<>:"/\\|?*')
            or project_name.endswith((" ", "."))
        ):

            QMessageBox.warning(
                self,
                "Invalid Project Name",
                "Please enter a valid project name."
            )

            return

        if not os.path.isdir(location):

            QMessageBox.warning(
                self,
                "Invalid Location",
                "Please select an existing folder."
            )

            return

        project_path = os.path.join(
            location,
            project_name
        )

        if os.path.exists(project_path):

            QMessageBox.warning(
                self,
                "Project Already Exists",
                "A folder with this project name already exists."
            )

            return

        try:

            os.makedirs(project_path)

            folders = [
                "geometry",
                "mesh",
                "results",
                "reports",
                "config"
            ]

            for folder in folders:

                os.makedirs(
                    os.path.join(project_path, folder)
                )

            metadata = {
                "project_name": project_name,
                "project_path": project_path,
                "created_on": datetime.now().isoformat(
                    timespec="seconds"
                ),
                "application": "Wind Turbine Structural Analyser",
                "version": "1.0"
            }

            with open(
                os.path.join(project_path, "project.json"),
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    metadata,
                    file,
                    indent=4
                )

            self.project_data = metadata

            QMessageBox.information(
                self,
                "Project Created",
                f"Project created successfully!\n\n"
                f"Location:\n{project_path}"
            )

            self.accept()

        except OSError as error:

            QMessageBox.critical(
                self,
                "Project Creation Failed",
                str(error)
            )