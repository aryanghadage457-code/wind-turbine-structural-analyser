from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QStackedWidget,
    QPushButton,
    QFrame,
    QTreeWidget,
    QTreeWidgetItem,
    QSplitter,
    QTextEdit,
)
from PySide6.QtCore import Qt

from gui.components.sidebar import Sidebar
from gui.components.viewport_3d import TurbineViewport
from gui.dashboard import DashboardPage


class MainWindow(QMainWindow):
    def __init__(self, project_data=None):
        super().__init__()
        self.project_data = project_data or {}
        self.project_name = self.project_data.get("project_name", "Wind Turbine Project")

        self.setWindowTitle("Wind Turbine Structural Analyser")
        self.setMinimumSize(1100, 700)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        self.create_topbar(workspace_layout)

        self.pages = QStackedWidget()
        workspace_layout.addWidget(self.pages)
        main_layout.addWidget(workspace)

        self.page_names = ["Dashboard", "Geometry", "Materials", "Environment", "Analysis", "Results"]
        self.page_widgets = {}

        for name in self.page_names:
            if name == "Dashboard":
                page = DashboardPage(self.project_data)
                page.geometry_requested.connect(lambda: self.change_page("Geometry"))
                page.analysis_requested.connect(lambda: self.change_page("Analysis"))
            elif name == "Geometry":
                page = self.create_geometry_page()
            else:
                page = self.create_placeholder_page(name)
            self.pages.addWidget(page)
            self.page_widgets[name] = page

        for name in self.page_names:
            self.sidebar.buttons[name].clicked.connect(
                lambda checked=False, page_name=name: self.change_page(page_name)
            )

        self.change_page("Dashboard")
        self.setStyleSheet("""
            QMainWindow { background-color: #17191D; }
            QWidget { color: #F2F3F5; }
            QFrame { border: none; }
        """)

    def create_topbar(self, parent_layout):
        topbar = QFrame()
        topbar.setFixedHeight(65)
        topbar.setObjectName("topbar")
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(25, 0, 25, 0)

        self.topbar_title = QLabel("Dashboard")
        self.topbar_title.setStyleSheet("color: #F2F3F5; font-size: 20px; font-weight: bold;")
        layout.addWidget(self.topbar_title)
        layout.addStretch()

        project_label = QLabel(self.project_name)
        project_label.setStyleSheet("color: #A5ABB4; font-size: 13px; padding-right: 15px;")
        layout.addWidget(project_label)

        self.save_button = QPushButton("Save")
        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")
        self.run_button = QPushButton("Run Analysis")

        for button in (self.save_button, self.undo_button, self.redo_button):
            button.setMinimumHeight(34)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet("""
                QPushButton { background-color: #343941; color: #F2F3F5;
                    border: 1px solid #414751; border-radius: 5px; padding: 5px 14px; }
                QPushButton:hover { background-color: #414751; }
            """)
            layout.addWidget(button)

        self.run_button.setMinimumHeight(34)
        self.run_button.setCursor(Qt.PointingHandCursor)
        self.run_button.setStyleSheet("""
            QPushButton { background-color: #0078D4; color: white; border: none;
                border-radius: 5px; padding: 5px 16px; font-weight: bold; }
            QPushButton:hover { background-color: #168DE5; }
        """)
        layout.addWidget(self.run_button)
        topbar.setStyleSheet("QFrame#topbar { background-color: #202329; border-bottom: 1px solid #414751; }")
        parent_layout.addWidget(topbar)

    def create_geometry_page(self):
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)
        splitter = QSplitter(Qt.Horizontal)

        # Left: model tree
        tree_panel = QFrame()
        tree_panel.setMinimumWidth(190)
        tree_panel.setMaximumWidth(280)
        tree_panel.setObjectName("workspacePanel")
        tree_layout = QVBoxLayout(tree_panel)
        tree_layout.setContentsMargins(12, 12, 12, 12)
        tree_title = QLabel("MODEL TREE")
        tree_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #00B8D9;")
        tree_layout.addWidget(tree_title)

        self.model_tree = QTreeWidget()
        self.model_tree.setHeaderHidden(True)
        turbine = QTreeWidgetItem(self.model_tree, ["Wind Turbine"])
        for component in ["Tower", "Nacelle", "Hub", "Blade 1", "Blade 2", "Blade 3"]:
            QTreeWidgetItem(turbine, [component])
        turbine.setExpanded(True)
        self.model_tree.itemClicked.connect(self.select_component)
        tree_layout.addWidget(self.model_tree)
        splitter.addWidget(tree_panel)

        # Centre: interactive 3D viewport
        viewport_panel = QFrame()
        viewport_panel.setObjectName("viewportPanel")
        viewport_layout = QVBoxLayout(viewport_panel)
        viewport_layout.setContentsMargins(0, 0, 0, 0)
        viewport_layout.setSpacing(0)
        viewport_header = QLabel("3D MODEL VIEWPORT")
        viewport_header.setFixedHeight(42)
        viewport_header.setStyleSheet("""
            background-color: #292D34; color: #A5ABB4; font-size: 12px;
            font-weight: bold; padding-left: 15px;
        """)
        viewport_layout.addWidget(viewport_header)
        self.viewport = TurbineViewport(self.project_data)
        self.viewport.status_message.connect(self.append_console)
        viewport_layout.addWidget(self.viewport, 1)
        splitter.addWidget(viewport_panel)

        # Right: properties
        properties_panel = QFrame()
        properties_panel.setMinimumWidth(210)
        properties_panel.setMaximumWidth(310)
        properties_panel.setObjectName("workspacePanel")
        properties_layout = QVBoxLayout(properties_panel)
        properties_layout.setContentsMargins(12, 12, 12, 12)
        properties_title = QLabel("PROPERTIES")
        properties_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #00B8D9;")
        properties_layout.addWidget(properties_title)

        self.selected_component = QLabel("Selected: None")
        self.selected_component.setWordWrap(True)
        self.selected_component.setStyleSheet("color: #F2F3F5; font-size: 14px; font-weight: bold; padding: 10px 0;")
        properties_layout.addWidget(self.selected_component)
        self.properties_text = QTextEdit()
        self.properties_text.setReadOnly(True)
        self.properties_text.setPlaceholderText("Select a component from the Model Tree to view its properties.")
        properties_layout.addWidget(self.properties_text)
        splitter.addWidget(properties_panel)
        splitter.setSizes([220, 800, 260])
        main_layout.addWidget(splitter, 1)

        # Bottom console
        console_panel = QFrame()
        console_panel.setFixedHeight(115)
        console_panel.setObjectName("workspacePanel")
        console_layout = QVBoxLayout(console_panel)
        console_layout.setContentsMargins(12, 8, 12, 8)
        console_title = QLabel("CONSOLE / STATUS")
        console_title.setStyleSheet("color: #00B8D9; font-size: 11px; font-weight: bold;")
        console_layout.addWidget(console_title)
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(65)
        self.console.setText("Engineering workspace initialized successfully.\nOpen Geometry to generate the 3D turbine visualization.")
        console_layout.addWidget(self.console)
        main_layout.addWidget(console_panel)

        page.setStyleSheet("""
            QWidget { background-color: #17191D; }
            QFrame#workspacePanel { background-color: #292D34; border: 1px solid #414751; border-radius: 7px; }
            QFrame#viewportPanel { background-color: #202329; border: 1px solid #414751; border-radius: 7px; }
            QTreeWidget { background-color: #292D34; color: #F2F3F5; border: none; outline: none; font-size: 13px; }
            QTreeWidget::item { padding: 7px; }
            QTreeWidget::item:selected { background-color: #173B57; color: white; }
            QTextEdit { background-color: #202329; color: #A5ABB4; border: 1px solid #414751; border-radius: 5px; font-size: 12px; }
        """)
        return page

    def select_component(self, item, column):
        component_name = item.text(column)
        if component_name == "Wind Turbine":
            self.viewport.select_component(None)
            self.selected_component.setText("Selected: Wind Turbine")
            self.properties_text.setText("Complete wind turbine assembly.\n\nSelect an individual component to inspect it.")
            return

        self.selected_component.setText(f"Selected: {component_name}")
        self.viewport.select_component(component_name)
        self.properties_text.setText(
            f"Component: {component_name}\n\n"
            "Geometry: Generated for visualization\n"
            "Material: Not assigned\n"
            "Structural mesh: Not generated\n"
            "Analysis status: Not yet analysed"
        )
        self.append_console(f"Selected component: {component_name}")

    def append_console(self, message):
        if hasattr(self, "console"):
            self.console.append(message)

    def create_placeholder_page(self, name):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)
        title = QLabel(name)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #F2F3F5; font-size: 30px; font-weight: bold;")
        description = QLabel(f"The {name} module will be implemented in the next development stages.")
        description.setAlignment(Qt.AlignCenter)
        description.setStyleSheet("color: #A5ABB4; font-size: 14px;")
        layout.addWidget(title)
        layout.addWidget(description)
        page.setStyleSheet("background-color: #17191D;")
        return page

    def change_page(self, name):
        if name not in self.page_widgets:
            return
        page = self.page_widgets[name]
        self.pages.setCurrentWidget(page)
        self.topbar_title.setText(name)
        self.sidebar.set_active_page(name)
        if name == "Geometry":
            try:
                self.viewport.ensure_geometry_loaded()
            except Exception as exc:
                # The viewport already displays the exception. Keep the GUI alive.
                self.append_console(f"Viewport error: {type(exc).__name__}: {exc}")
