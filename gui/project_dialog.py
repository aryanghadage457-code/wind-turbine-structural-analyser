"""Create New Project dialog.

Result (unchanged): dialog.project_data = {
    "project_name", "project_path", "created_on"
}  or None if cancelled. Nothing is written to disk here.
"""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from gui.components.dialog_parts import make_footer, make_header
from gui.theme.icons import icon
from gui.theme.styles import COLORS


class ProjectDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle("Create New Project")
        self.setFixedSize(600, 440)

        self.project_data = None

        self.create_interface()

    # ==========================================
    # INTERFACE
    # ==========================================

    def create_interface(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(
            make_header(
                "plus",
                "Create New Project",
                "Enter your project details and choose a save location."
            )
        )

        body = QVBoxLayout()
        body.setContentsMargins(26, 22, 26, 18)
        body.setSpacing(8)

        # Project name
        name_label = QLabel("PROJECT NAME")
        name_label.setObjectName("FieldLabel")

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter project name")
        self.name_input.textChanged.connect(self.on_input_changed)

        body.addWidget(name_label)
        body.addWidget(self.name_input)

        body.addSpacing(10)

        # Project location
        location_label = QLabel("LOCATION")
        location_label.setObjectName("FieldLabel")

        location_row = QHBoxLayout()
        location_row.setSpacing(8)

        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText(
            "Select a folder using Browse..."
        )
        self.location_input.setReadOnly(True)
        self.location_input.textChanged.connect(self.on_input_changed)

        browse_button = QPushButton("Browse")
        browse_button.setIcon(icon("folder", COLORS["text2"], 18))
        browse_button.setCursor(Qt.PointingHandCursor)
        browse_button.clicked.connect(self.browse_location)

        location_row.addWidget(self.location_input, 1)
        location_row.addWidget(browse_button)

        body.addWidget(location_label)
        body.addLayout(location_row)

        body.addSpacing(10)

        # Live preview of the folder that will be created
        preview_label = QLabel("PROJECT FOLDER")
        preview_label.setObjectName("FieldLabel")

        self.path_preview = QLabel()
        self.path_preview.setObjectName("PathPreview")
        self.path_preview.setWordWrap(True)

        body.addWidget(preview_label)
        body.addWidget(self.path_preview)

        # Inline validation message
        self.error_label = QLabel()
        self.error_label.setObjectName("ErrorText")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        body.addWidget(self.error_label)

        body.addStretch()

        root.addLayout(body, 1)

        # Footer
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        create_button = QPushButton("Create Project")
        create_button.setObjectName("PrimaryButton")
        create_button.setDefault(True)
        create_button.clicked.connect(self.create_project)

        root.addWidget(make_footer(cancel_button, create_button))

        self.update_preview()

    # ==========================================
    # HELPERS
    # ==========================================

    def update_preview(self):

        name = self.name_input.text().strip()
        location = self.location_input.text().strip()

        if name and location:
            self.path_preview.setText(str(Path(location) / name))
        else:
            self.path_preview.setText(
                "Enter a name and choose a location to preview the folder."
            )

    def on_input_changed(self, _text=""):

        self.update_preview()
        self.clear_error()

    def show_error(self, message, field=None):

        self.error_label.setText(message)
        self.error_label.show()

        if field is not None:
            self.set_invalid(field, True)
            field.setFocus()

    def clear_error(self):

        self.error_label.hide()

        self.set_invalid(self.name_input, False)
        self.set_invalid(self.location_input, False)

    @staticmethod
    def set_invalid(widget, invalid):

        widget.setProperty("invalid", "true" if invalid else "false")
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    # ==========================================
    # ACTIONS
    # ==========================================

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

            self.show_error(
                "Please enter a project name.",
                self.name_input
            )

            return

        # Validate project location
        if not project_location:

            self.show_error(
                "Please select a project location.",
                self.location_input
            )

            return

        # Validate project name as a folder name
        if (
            project_name in (".", "..")
            or Path(project_name).name != project_name
            or any(char in project_name for char in '<>:"/\\|?*')
        ):

            self.show_error(
                "Please enter a valid project name. "
                "It cannot contain any of  < > : \" / \\ | ? *",
                self.name_input
            )

            return

        project_path = Path(project_location) / project_name

        # Prevent overwriting an existing project
        if project_path.exists():

            self.show_error(
                "A folder with this project name already exists. "
                "Please choose another name.",
                self.name_input
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