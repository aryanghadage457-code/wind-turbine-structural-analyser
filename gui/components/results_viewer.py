"""Results viewer: embeds a PyVista plotter with a stress/strain/displacement
contour, a quantity/surface toolbar, and the reusable Element Details panel
below it. Swapped into GraphicsView in place of the geometry viewport once
a solve has completed.

The Details/Mohr's-circle panel is hidden by default so the 3D view gets
the full pane; use the toolbar toggle to show it alongside.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QSplitter, QToolButton,
    QVBoxLayout, QWidget,
)
from pyvistaqt import QtInteractor

from visualization import contour_plots as cp
from visualization.contour_plots import enable_element_selection
from gui.components.element_details_panel import ElementDetailsPanel

BACKGROUND = "#171614"

# Scalar-bar styling — light backing panel + dark bold text so the legend
# reads clearly regardless of what colours the contour itself uses.
_BAR_BG = (1.0, 1.0, 1.0)         # pure white
_BAR_BG_OPACITY = 1.0             # fully opaque, not just tinted
_BAR_TEXT = (0.09, 0.086, 0.078)  # dark text on that panel

STRESS_QUANTITIES = {
    "Von Mises": lambda p, g, r, surf, sub: cp.plot_von_mises(p, g, r, surface=surf),
    "Max Shear Stress": lambda p, g, r, surf, sub: cp.plot_max_shear_stress(p, g, r, surface=surf),
    "Mean Stress": lambda p, g, r, surf, sub: cp.plot_mean_stress(p, g, r, surface=surf),
    "Principal Stress": lambda p, g, r, surf, sub: cp.plot_principal_stress(p, g, r, component=sub, surface=surf),
    "Stress Component": lambda p, g, r, surf, sub: cp.plot_stress_component(p, g, r, component=sub, surface=surf),
}
STRAIN_QUANTITIES = {
    "Equivalent Strain": lambda p, g, r, surf, sub: cp.plot_equivalent_strain(p, g, r, surface=surf),
    "Max Shear Strain": lambda p, g, r, surf, sub: cp.plot_max_shear_strain(p, g, r, surface=surf),
    "Principal Strain": lambda p, g, r, surf, sub: cp.plot_principal_strain(p, g, r, component=sub, surface=surf),
    "Strain Component": lambda p, g, r, surf, sub: cp.plot_strain_component(p, g, r, component=sub, surface=surf),
}
SUB_OPTIONS = {
    "Principal Stress": ["max", "intermediate", "min"],
    "Principal Strain": ["max", "intermediate", "min"],
    "Stress Component": ["xx", "yy", "zz", "xy", "xz", "yz"],
    "Strain Component": ["xx", "yy", "zz", "xy", "xz", "yz"],
    "Displacement": ["magnitude", "x", "y", "z"],
}


class ResultsViewer(QWidget):

    status_message = Signal(str)

    def __init__(self, results_data, parent=None):
        super().__init__(parent)
        self.results_data = results_data
        self._picking_enabled = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("GraphicsToolbar")
        toolbar.setFixedHeight(40)
        t = QHBoxLayout(toolbar)
        t.setContentsMargins(10, 0, 10, 0)
        t.setSpacing(8)

        quantities = list(STRESS_QUANTITIES) + list(STRAIN_QUANTITIES)
        if results_data.displacement is not None:
            quantities.append("Displacement")

        self.quantity_box = QComboBox()
        self.quantity_box.addItems(quantities)
        self.quantity_box.currentTextChanged.connect(self._on_quantity_changed)

        self.sub_box = QComboBox()
        self.sub_box.currentTextChanged.connect(self._refresh)
        self.sub_box.setVisible(False)

        self.surface_box = QComboBox()
        self.surface_box.addItems(["outer", "inner"])
        self.surface_box.currentTextChanged.connect(self._refresh)

        self.details_toggle = QToolButton()
        self.details_toggle.setObjectName("ViewButton")
        self.details_toggle.setText("Details && Mohr's Circle")
        self.details_toggle.setCheckable(True)
        self.details_toggle.toggled.connect(self._toggle_details)

        t.addWidget(QLabel("Quantity:"))
        t.addWidget(self.quantity_box)
        t.addWidget(self.sub_box)
        t.addWidget(QLabel("Surface:"))
        t.addWidget(self.surface_box)
        t.addStretch()
        t.addWidget(self.details_toggle)
        root.addWidget(toolbar)

        self.splitter = QSplitter(Qt.Vertical)

        self.plotter = QtInteractor(self)
        self.plotter.set_background(BACKGROUND)
        self.splitter.addWidget(self.plotter.interactor)

        self.details_panel = ElementDetailsPanel()
        self.details_panel.set_results_data(self.results_data)
        self.splitter.addWidget(self.details_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, True)
        # Start collapsed: the 3D view gets the whole pane until the user
        # asks for Details/Mohr's circle via the toolbar toggle.
        self.splitter.setSizes([1, 0])
        root.addWidget(self.splitter, 1)

        self._on_quantity_changed(self.quantity_box.currentText())

    def _toggle_details(self, checked):
        if checked:
            total = max(self.splitter.height(), 500)
            self.splitter.setSizes([int(total * 0.55), int(total * 0.45)])
            self.details_toggle.setText("Hide Details & Mohr's Circle")
        else:
            self.splitter.setSizes([max(self.splitter.height(), 1), 0])
            self.details_toggle.setText("Details && Mohr's Circle")

    def _on_quantity_changed(self, quantity):
        options = SUB_OPTIONS.get(quantity)
        self.sub_box.blockSignals(True)
        self.sub_box.clear()
        if options:
            self.sub_box.addItems(options)
            self.sub_box.setVisible(True)
        else:
            self.sub_box.setVisible(False)
        self.sub_box.blockSignals(False)
        self.surface_box.setVisible(quantity != "Displacement")
        self._refresh()

    def _refresh(self):
        quantity = self.quantity_box.currentText()
        surface = self.surface_box.currentText()
        sub = self.sub_box.currentText() if self.sub_box.isVisible() else None

        self.plotter.clear()
        self._picking_enabled = False  # clear() may drop the contour actor; re-attach below

        before = len(self.plotter.renderer.actors)

        try:
            if quantity == "Displacement":
                if self.results_data.displacement is None:
                    self.status_message.emit("No displacement data available for this solve.")
                    return
                cp.plot_displacement(
                    self.plotter, self.results_data.grid,
                    self.results_data.displacement, component=sub or "magnitude",
                )
            else:
                func = STRESS_QUANTITIES.get(quantity) or STRAIN_QUANTITIES.get(quantity)
                func(self.plotter, self.results_data.grid, self.results_data.results, surface, sub)
        except Exception as exc:
            self.status_message.emit(f"Could not display {quantity}: {exc}")
            return

        after = len(self.plotter.renderer.actors)
        if after <= before:
            # The call didn't raise, but nothing was actually added to the
            # scene — this is the "blank view" symptom, not a crash.
            self.status_message.emit(
                f"{quantity} ({surface}) produced no geometry to display — "
                "likely missing or empty data for this surface/component in contour_plots.py."
            )
            return

        if quantity != "Displacement":
            # Element picking needs the per-element contour grid, not the
            # displacement (nodal) one, so only enable it for stress/strain.
            enable_element_selection(
                self.plotter, self.results_data.grid,
                on_element_selected=self._on_element_selected,
            )

        self._brighten_scalar_bar()
        self.plotter.view_isometric()
        self.plotter.reset_camera()
        self.plotter.render()
        self.status_message.emit(f"Showing {quantity}" + (f" ({surface})" if quantity != "Displacement" else "") + ".")

    def _brighten_scalar_bar(self):
        """Give the colour-legend a light backing panel and dark bold text
        so it stays readable against the dark 3D background, regardless of
        the colour map underneath it."""
        try:
            for actor in self.plotter.scalar_bars.values():
                for tp in (actor.GetLabelTextProperty(), actor.GetTitleTextProperty()):
                    tp.SetColor(*_BAR_TEXT)
                    tp.SetBold(True)
                    tp.SetShadow(False)
                actor.DrawBackgroundOn()
                bg = actor.GetBackgroundProperty()
                bg.SetColor(*_BAR_BG)
                bg.SetOpacity(_BAR_BG_OPACITY)
        except Exception:
            pass

    def _on_element_selected(self, original_cell_id, element_id):
        self.details_panel.show_element(original_cell_id)
        if not self.details_toggle.isChecked():
            self.details_toggle.setChecked(True)

    def shutdown(self):
        if self.plotter is not None:
            try:
                self.plotter.close()
            except Exception:
                pass