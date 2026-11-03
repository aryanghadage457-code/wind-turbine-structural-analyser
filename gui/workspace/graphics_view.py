"""Central graphics area: view toolbar + a swappable viewport.

Until the geometry module is connected a placeholder is shown (isometric
grid, axes triad). The real PyVista viewport replaces it with:

    graphics.set_viewport(real_widget)

Signals
    view_requested(str)   "fit" | "iso" | "front" | "top" | "wireframe"
"""
from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget,
)

from gui.theme.styles import COLORS
from gui.workspace.ribbon_icons import ribbon_icon


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

        # faint turbine silhouette on the grid
        p.setPen(QPen(QColor(COLORS["accent"]), 1.4))
        base = QPointF(cx, cy)
        hub = QPointF(cx, cy - s * 6.5)
        p.drawLine(base, hub)
        for dx, dy in ((0, -3.2), (-2.8, 1.6), (2.8, 1.6)):
            p.drawLine(hub, QPointF(hub.x() + dx * s, hub.y() + dy * s))
        p.drawEllipse(hub, s * 0.25, s * 0.25)

        # axes triad (bottom-left)
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

        # message
        p.setPen(QColor(COLORS["text3"]))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(self.rect().adjusted(0, 0, 0, -14),
                   Qt.AlignHCenter | Qt.AlignBottom, self.message)
        p.end()


class GraphicsView(QFrame):

    view_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidePanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- toolbar ----
        bar = QFrame()
        bar.setObjectName("GraphicsToolbar")
        bar.setFixedHeight(40)
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(4)

        self._buttons = {}
        for key, text, icon_name, checkable in (
            ("fit", "Fit", "fit", False),
            ("iso", "Isometric", "cube", False),
            ("front", "Front", "cube", False),
            ("top", "Top", "mesh", False),
            ("wireframe", "Wireframe", "mesh", True),
        ):
            btn = QToolButton()
            btn.setObjectName("ViewButton")
            btn.setText(text)
            btn.setIcon(ribbon_icon(icon_name, 18))
            btn.setIconSize(QSize(18, 18))
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            btn.setCheckable(checkable)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self.view_requested.emit(k))
            self._buttons[key] = btn
            row.addWidget(btn)

        row.addStretch()
        self.caption = QLabel("Graphics")
        self.caption.setObjectName("PanelSubtitle")
        row.addWidget(self.caption)
        root.addWidget(bar)

        # ---- viewport slot ----
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