"""Placeholder data for the Engineering Workspace.

Used until the teammates' modules are connected. Component names
(Tower, Nacelle, Hub, Blade 1-3) match the real 3D viewport.
"""

# (label, status)  status: "done" | "pending" | "locked"
OUTLINE = [
    ("Geometry", "done", ["Tower", "Nacelle", "Hub", "Blade 1", "Blade 2", "Blade 3"]),
    ("Materials", "pending", []),
    ("Environment", "pending", []),
    ("Mesh", "locked", []),
    ("Solution", "locked", []),
    ("Results", "locked", []),
]

DETAILS = {
    "Tower": [("Component", "Tower"), ("Sections", "4"), ("Material", "Not assigned"),
              ("Mesh", "Not generated"), ("Status", "Not analysed")],
    "Nacelle": [("Component", "Nacelle"), ("Material", "Not assigned"),
                ("Mesh", "Not generated"), ("Status", "Not analysed")],
    "Hub": [("Component", "Hub"), ("Material", "Not assigned"),
            ("Mesh", "Not generated"), ("Status", "Not analysed")],
    "Blade 1": [("Component", "Blade 1"), ("Material", "Not assigned"),
                ("Mesh", "Not generated"), ("Status", "Not analysed")],
    "Blade 2": [("Component", "Blade 2"), ("Material", "Not assigned"),
                ("Mesh", "Not generated"), ("Status", "Not analysed")],
    "Blade 3": [("Component", "Blade 3"), ("Material", "Not assigned"),
                ("Mesh", "Not generated"), ("Status", "Not analysed")],
    "default": [("Selection", "Nothing selected"),
                ("Hint", "Select an item in the Outline")],
}

LOG_MESSAGES = [
    "Workspace initialised.",
    "Project loaded.",
    "Geometry viewport is a placeholder until the geometry module is connected.",
]