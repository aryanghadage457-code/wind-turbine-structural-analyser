import sys
from PySide6.QtWidgets import QApplication
from gui.theme.styles import install_theme
from gui.components.viewport_3d import TurbineViewport

if __name__ == "__main__":          # required: the geometry process is "spawned"
    app = QApplication(sys.argv)
    install_theme(app)
    view = TurbineViewport()
    view.status_message.connect(print)
    view.resize(1100, 750)
    view.show()
    view.ensure_geometry_loaded()
    sys.exit(app.exec())