"""One reusable Element Details panel: text block + Mohr circle canvas.
show_element() is called every time a new element is picked — the widget
itself is created once and updated in place.
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QTextEdit, QVBoxLayout

from gui.components.mohr_canvas import MohrCircleCanvas
from visualization.element_details import get_element_details


def _format_details_text(details):
    stress = details["stress"]
    strain = details["strain"]
    lines = [
        f"ELEMENT ID: {details['element_id']}",
        f"COMPONENT: {details['group_name']}",
        f"SURFACE: {details['surface']}",
        "",
        "STRESS COMPONENTS (MPa)",
    ]
    lines += [f"  {n}: {v / 1e6:.4f}" for n, v in stress["components"].items()]
    lines += ["", "PRINCIPAL STRESSES (MPa)"]
    lines += [f"  {n}: {v / 1e6:.4f}" for n, v in stress["principal"].items()]
    lines += [
        "",
        f"Von Mises: {stress['von_mises'] / 1e6:.4f} MPa",
        f"Maximum shear: {stress['maximum_shear'] / 1e6:.4f} MPa",
        "",
        "STRAIN COMPONENTS",
    ]
    lines += [f"  {n}: {v:.6e}" for n, v in strain["tensorial_components"].items()]
    lines += ["", "ENGINEERING SHEAR STRAINS"]
    lines += [f"  {n}: {v:.6e}" for n, v in strain["engineering_shear"].items()]
    lines += ["", "PRINCIPAL STRAINS"]
    lines += [f"  {n}: {v:.6e}" for n, v in strain["principal"].items()]
    lines += [
        "",
        f"Equivalent strain: {strain['equivalent']:.6e}",
        f"Maximum shear strain: {strain['maximum_shear']:.6e}",
    ]
    return "\n".join(lines)


class ElementDetailsPanel(QFrame):

    surface_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidePanel")
        self._results_data = None
        self._element_index = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("PanelHeader")
        header.setFixedHeight(28)
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 0, 12, 0)
        title = QLabel("ELEMENT DETAILS")
        title.setObjectName("PanelTitle")
        h.addWidget(title)
        h.addStretch()
        self.surface_box = QComboBox()
        self.surface_box.addItems(["outer", "inner"])
        self.surface_box.currentTextChanged.connect(self._on_surface_changed)
        h.addWidget(self.surface_box)
        root.addWidget(header)

        body = QHBoxLayout()
        body.setContentsMargins(10, 10, 10, 10)
        body.setSpacing(10)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("Click an element in the 3D view to see its details.")
        self.text.setMinimumWidth(260)

        self.mohr = MohrCircleCanvas()
        self.mohr.setMinimumWidth(320)

        body.addWidget(self.text, 1)
        body.addWidget(self.mohr, 1)
        root.addLayout(body)

    def set_results_data(self, results_data):
        self._results_data = results_data
        self._element_index = None
        self.text.clear()

    def show_element(self, element_index):
        if self._results_data is None:
            return
        self._element_index = element_index
        self._refresh()

    def _on_surface_changed(self, surface):
        if self._element_index is not None:
            self._refresh()
        self.surface_changed.emit(surface)

    def _refresh(self):
        surface = self.surface_box.currentText()
        details = get_element_details(
            self._results_data.results,
            self._results_data.mesh,
            self._element_index,
            surface=surface,
        )
        self.text.setPlainText(_format_details_text(details))
        self.mohr.plot_circles(details["mohr"], details["element_id"])