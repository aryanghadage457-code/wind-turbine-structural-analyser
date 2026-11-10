"""Central graphics area: a thin title header + a swappable viewport.

Until the geometry module is connected a placeholder is shown (isometric
grid, axes triad). The real PyVista viewport replaces it with:

    graphics.set_viewport(real_widget)

View controls (Fit, Isometric, Wireframe, etc.) now live in the ribbon's
Home tab, so this widget dedicates almost all of its space to the 3D view.
"""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gui.theme.styles import COLORS


class PlaceholderViewport(QWidget):
    """Isometric ground grid, axes triad and a message."""

    message = "3D viewport\nGeometry module not connected yet"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 240)

    @staticmethod
    def _iso(x, y, cx, cy, s):
        return QPointF(cx + (x - y) * s * 0.866, cy + (x + y) * s * 0.5)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(COLORS["bg0"]))

        w, h = self.width(), self.height()
        s = min(w, h) / 16.0
        cx, cy = w / 2, h * 0.62
        n = 6

        p.setPen(QPen(QColor(COLORS["border"]), 1))
        for i in range(-n, n + 1):
            p.drawLine(self._iso(i, -n, cx, cy, s), self._iso(i, n, cx, cy, s))
            p.drawLine(self._iso(-n, i, cx, cy, s), self._iso(n, i, cx, cy, s))

        p.setPen(QPen(QColor(COLORS["accent"]), 1.4))
        base = QPointF(cx, cy)
        hub = QPointF(cx, cy - s * 6.5)
        p.drawLine(base, hub)
        for dx, dy in ((0, -3.2), (-2.8, 1.6), (2.8, 1.6)):
            p.drawLine(hub, QPointF(hub.x() + dx * s, hub.y() + dy * s))
        p.drawEllipse(hub, s * 0.25, s * 0.25)

        ox, oy = 46.0, h - 40.0
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        for dx, dy, colour, label in (
            (30, 15, COLORS["danger"], "X"),
            (-30, 15, COLORS["success"], "Y"),
            (0, -34, COLORS["accent_hover"], "Z"),
        ):
            p.setPen(QPen(QColor(colour), 2))
            p.drawLine(QPointF(ox, oy), QPointF(ox + dx, oy + dy))
            p.drawText(QPointF(ox + dx * 1.2 - 3, oy + dy * 1.2 + 4), label)

        p.setPen(QColor(COLORS["text3"]))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(self.rect().adjusted(0, 0, 0, -14),
                   Qt.AlignHCenter | Qt.AlignBottom, self.message)
        p.end()


class GraphicsView(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidePanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("PanelHeader")
        header.setFixedHeight(28)
        row = QHBoxLayout(header)
        row.setContentsMargins(12, 0, 12, 0)

        title = QLabel("3D VIEWPORT")
        title.setObjectName("PanelTitle")
        self.caption = QLabel("")
        self.caption.setObjectName("PanelSubtitle")

        row.addWidget(title)
        row.addStretch()
        row.addWidget(self.caption)
        root.addWidget(header)

        self._slot = QVBoxLayout()
        self._slot.setContentsMargins(0, 0, 0, 0)
        root.addLayout(self._slot, 1)

        self._viewport = PlaceholderViewport()
        self._slot.addWidget(self._viewport)

    def set_viewport(self, widget):
        """Swap the placeholder (or current viewport) for a real widget."""
        self._slot.removeWidget(self._viewport)
        self._viewport.setParent(None)
        self._viewport.deleteLater()
        self._viewport = widget
        self._slot.addWidget(widget)

    def viewport(self):
        return self._viewport

    def set_caption(self, text):
        self.caption.setText(text)