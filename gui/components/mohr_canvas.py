"""Small Matplotlib canvas embedded in Qt, showing the three Mohr's circles
for one selected element (same circle data as test_element_selection.py).
"""
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class MohrCircleCanvas(FigureCanvasQTAgg):

    def __init__(self, parent=None):
        fig = Figure(figsize=(4, 4), tight_layout=True)
        super().__init__(fig)
        self.setParent(parent)
        self.ax = fig.add_subplot(111)
        fig.patch.set_facecolor("#171614")
        self.ax.set_facecolor("#171614")
        self._style_axes()

    def _style_axes(self):
        self.ax.tick_params(colors="#B0A593")
        for spine in self.ax.spines.values():
            spine.set_color("#4A453E")
        self.ax.xaxis.label.set_color("#F1ECE4")
        self.ax.yaxis.label.set_color("#F1ECE4")
        self.ax.title.set_color("#F1ECE4")

    def plot_circles(self, mohr, element_id):
        self.ax.clear()
        self._style_axes()
        colors = {"xy": "#9A8873", "xz": "#7FA38A", "yz": "#D4686B"}
        for name, circle in mohr["circles"].items():
            sigma = np.asarray(circle["sigma"]) / 1e6
            tau = np.asarray(circle["tau"]) / 1e6
            tau_negative = np.asarray(circle["tau_negative"]) / 1e6
            c = colors.get(name, "#9A8873")
            self.ax.plot(sigma, tau, color=c, label=name)
            self.ax.plot(sigma, tau_negative, color=c)
        self.ax.axhline(0, color="#4A453E", linewidth=0.8)
        self.ax.axvline(0, color="#4A453E", linewidth=0.8)
        self.ax.set_xlabel("Normal Stress (MPa)")
        self.ax.set_ylabel("Shear Stress (MPa)")
        self.ax.set_title(f"Mohr's Circles — Element {element_id}")
        self.ax.grid(True, color="#262320")
        self.ax.set_aspect("equal")
        self.ax.legend(fontsize=8, facecolor="#221F1D", edgecolor="#4A453E", labelcolor="#F1ECE4")
        self.draw()