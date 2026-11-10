"""Lightweight utilisation-vs-wind-speed plot, drawn with QPainter.
No charting library dependency — just Qt.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from gui.theme.styles import COLORS

_MARGIN_LEFT = 55
_MARGIN_RIGHT = 115
_MARGIN_TOP = 34        # must stay >= the top-label height + its gap below it
_MARGIN_BOTTOM = 40
_Y_PAD_FRACTION = 0.18  # headroom above the curve's own peak, inside plot_rect
_TOP_LABEL_GAP = 8      # px between the top axis label and plot_rect's top edge


class UtilisationPlot(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self._speeds = []
        self._utilisation = []
        self._operating_speed = None

    def set_curve(self, speeds, utilisation, operating_speed=None):
        self._speeds = list(speeds or [])
        self._utilisation = list(utilisation or [])
        self._operating_speed = operating_speed
        self.update()

    def clear_curve(self):
        self._speeds, self._utilisation, self._operating_speed = [], [], None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        plot_rect = QRectF(
            _MARGIN_LEFT, _MARGIN_TOP,
            max(w - _MARGIN_LEFT - _MARGIN_RIGHT, 10),
            max(h - _MARGIN_TOP - _MARGIN_BOTTOM, 10),
        )

        if not self._speeds or not self._utilisation:
            painter.setPen(QColor(COLORS["text2"]))
            painter.drawText(self.rect(), Qt.AlignCenter,
                              "No solve results yet — run Solve to see the utilisation curve.")
            return

        v_max = max(self._speeds) or 1.0
        # The curve's own peak never exceeds plot_rect's top by more than
        # _Y_PAD_FRACTION of the plotted range — the top axis label sits
        # ABOVE plot_rect entirely (in the margin), so the two can never
        # collide regardless of how close the data gets to u_max.
        u_max = max(max(self._utilisation) * (1.0 + _Y_PAD_FRACTION), 1.2)

        def to_px(v, u):
            x = plot_rect.left() + (v / v_max) * plot_rect.width()
            y = plot_rect.bottom() - (u / u_max) * plot_rect.height()
            return QPointF(x, y)

        # axes
        axis_pen = QPen(QColor(COLORS["text2"]))
        axis_pen.setWidth(1)
        painter.setPen(axis_pen)
        painter.drawLine(plot_rect.bottomLeft(), plot_rect.bottomRight())
        painter.drawLine(plot_rect.bottomLeft(), plot_rect.topLeft())

        label_font = QFont("", 8)
        metrics = QFontMetrics(label_font)

        # allowable threshold line at utilisation = 1.0
        if u_max >= 1.0:
            y1 = to_px(0, 1.0).y()
            dash_pen = QPen(QColor(COLORS["danger"]))
            dash_pen.setStyle(Qt.DashLine)
            dash_pen.setWidth(1)
            painter.setPen(dash_pen)
            painter.drawLine(QPointF(plot_rect.left(), y1), QPointF(plot_rect.right(), y1))
            painter.setFont(label_font)
            painter.setPen(QColor(COLORS["danger"]))
            label = "Allowable (1.0)"
            label_w = metrics.horizontalAdvance(label)
            painter.drawText(QPointF(w - label_w - 10, y1 - 4), label)

        # the curve itself
        line_pen = QPen(QColor(COLORS["accent"]))
        line_pen.setWidth(2)
        painter.setPen(line_pen)
        points = [to_px(v, u) for v, u in zip(self._speeds, self._utilisation)]
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])

        # operating-speed marker
        if self._operating_speed is not None:
            mx = to_px(self._operating_speed, 0).x()
            marker_pen = QPen(QColor(COLORS["text"]))
            marker_pen.setStyle(Qt.DashLine)
            painter.setPen(marker_pen)
            painter.drawLine(QPointF(mx, plot_rect.top()), QPointF(mx, plot_rect.bottom()))
            painter.setFont(label_font)
            painter.drawText(QPointF(mx + 4, plot_rect.top() + 12), f"{self._operating_speed:g} m/s")

        # axis labels
        painter.setPen(QColor(COLORS["text2"]))
        axis_font = QFont("", 9)
        painter.setFont(axis_font)
        axis_metrics = QFontMetrics(axis_font)
        painter.drawText(QPointF(plot_rect.left(), h - 10), "0")
        painter.drawText(QPointF(plot_rect.right() - 36, h - 10), f"{v_max:.0f} m/s")
        painter.drawText(QPointF(8, plot_rect.bottom() + 4), "0")

        # Top y-axis label: drawn ABOVE plot_rect, in the margin reserved
        # by _MARGIN_TOP, so it can never sit on top of the curve even
        # when the curve's peak is right at the top of the plotted area.
        top_label = f"{u_max:.2f}"
        top_label_baseline = plot_rect.top() - _TOP_LABEL_GAP
        painter.drawText(QPointF(8, top_label_baseline), top_label)

        painter.save()
        painter.translate(14, plot_rect.center().y())
        painter.rotate(-90)
        painter.drawText(QPointF(-40, 0), "Utilisation")
        painter.restore()
        painter.drawText(QRectF(plot_rect.left(), h - 24, plot_rect.width(), 16),
                          Qt.AlignCenter, "Wind speed")