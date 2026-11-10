import json
from pathlib import Path
from datetime import datetime


# Store recent projects in the user's application data folder
APP_DATA = Path.home() / ".wind_turbine_structural_analyser"

RECENT_PROJECTS_FILE = APP_DATA / "recent_projects.json"


def load_recent_projects():

    APP_DATA.mkdir(parents=True, exist_ok=True)

    if not RECENT_PROJECTS_FILE.exists():
        return []

    try:
        with open(RECENT_PROJECTS_FILE, "r", encoding="utf-8") as file:
            projects = json.load(file)

        if not isinstance(projects, list):
            return []

        return projects

    except (json.JSONDecodeError, OSError):
        return []


def save_recent_projects(projects):

    APP_DATA.mkdir(parents=True, exist_ok=True)

    with open(RECENT_PROJECTS_FILE, "w", encoding="utf-8") as file:
        json.dump(projects, file, indent=4)


def add_recent_project(project_data):

    projects = load_recent_projects()

    project_path = str(Path(project_data["project_path"]).resolve())

    now = datetime.now().isoformat(timespec="seconds")

    # Remove an older entry for the same project
    projects = [
        project for project in projects
        if Path(project.get("project_path", "")).resolve() != Path(project_path)
    ]

    project_entry = {
        "project_name": project_data["project_name"],
        "project_path": project_path,
        "created_on": project_data.get("created_on", now),
        "last_opened": now
    }

    # Put the latest opened project first
    projects.insert(0, project_entry)

    # Keep only the 10 most recent projects
    projects = projects[:10]

    save_recent_projects(projects)

    return projects


def get_valid_recent_projects():

    projects = load_recent_projects()

    valid_projects = []

    for project in projects:

        project_path = Path(project.get("project_path", ""))

        metadata_file = project_path / "project.json"

        if project_path.is_dir() and metadata_file.is_file():
            valid_projects.append(project)

    save_recent_projects(valid_projects)

    return valid_projects