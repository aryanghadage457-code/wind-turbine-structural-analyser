"""Starting Window (ANSYS-style start screen).

Public interface used by main.py (unchanged):
    new_project_requested         Signal()
    open_project_requested(str)   Signal(str)  -> project folder path
    update_recent_projects(list)  list of dicts from project_manager

All colours come from gui.theme.styles.COLORS and the object names in styles.py.
"""
import math
from datetime import datetime

from PySide6.QtCore import (
    QEasingCurve, QEvent, QObject, QPointF, QPropertyAnimation, QRectF,
    QSize, QTimer, QVariantAnimation, Qt, Signal
)
from PySide6.QtGui import (
    QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
)
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget
)

from gui.theme.icons import pixmap
from gui.theme.styles import COLORS


# ======================================================================
# Small animation helpers
# ======================================================================

class GlowFilter(QObject):
    """Soft taupe glow that fades in on hover and out on leave."""

    def __init__(self, widget, color, radius=30, max_alpha=170):
        super().__init__(widget)
        self._color = QColor(color)
        self._radius = radius
        self._alpha = max_alpha
        self._p = 0.0

        self._effect = QGraphicsDropShadowEffect(widget)
        self._effect.setOffset(0, 0)
        self._apply(0.0)
        widget.setGraphicsEffect(self._effect)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._apply)

        widget.installEventFilter(self)

    def _apply(self, value):
        self._p = float(value)
        c = QColor(self._color)
        c.setAlpha(int(self._alpha * self._p))
        self._effect.setColor(c)
        self._effect.setBlurRadius(self._radius * self._p)

    def _run(self, end):
        self._anim.stop()
        self._anim.setStartValue(self._p)
        self._anim.setEndValue(end)
        self._anim.start()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Enter:
            self._run(1.0)
        elif event.type() == QEvent.Leave:
            self._run(0.0)
        return False


def fade_in(widget, delay_ms, duration=450):
    """Fade a widget in after delay_ms, then remove the effect."""
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)

    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))

    def start():
        try:
            anim.start()
        except RuntimeError:
            pass  # widget was closed before the delay ended

    QTimer.singleShot(delay_ms, start)


# ======================================================================
# Hero banner with a countryside wind-farm outline
# ======================================================================

class HeroBanner(QWidget):
    """Rounded banner. Text sits on the left, rolling hills and slowly
    turning wind turbines are drawn as outlines on the right."""

    # base / amp are fractions of the banner height.
    # turbines: (x position 0..1 across the right side, tower px, spin speed)
    _LAYERS = [
        dict(base=0.62, amp=0.035, freq=1.3, phase=0.4, fill="#2C1F17",
             alpha=75, turbines=[(0.12, 58, 1.0), (0.52, 66, -0.8),
                                 (0.90, 52, 1.2)]),
        dict(base=0.77, amp=0.030, freq=1.9, phase=1.7, fill="#251A14",
             alpha=105, turbines=[(0.30, 92, 0.9), (0.73, 84, -1.1)]),
        dict(base=0.91, amp=0.025, freq=2.4, phase=3.1, fill="#1E1511",
             alpha=140, turbines=[(0.52, 120, -0.7)]),
    ]

    def __init__(self, eyebrow, title, description, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(250)

        self._tick = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._advance)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 30, 34, 30)
        layout.setSpacing(8)

        eyebrow_label = QLabel(eyebrow)
        eyebrow_label.setObjectName("Eyebrow")

        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        title_label.setWordWrap(True)
        title_label.setMaximumWidth(620)

        desc_label = QLabel(description)
        desc_label.setObjectName("SecondaryText")
        desc_label.setWordWrap(True)
        desc_label.setMaximumWidth(560)

        layout.addWidget(eyebrow_label)
        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addStretch()

    # ---- animation control ------------------------------------------

    def _advance(self):
        self._tick += 1.0
        self.update()

    def showEvent(self, event):
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    # ---- drawing -----------------------------------------------------

    @staticmethod
    def _ground(x, w, h, layer):
        t = 2 * math.pi * layer["freq"] * x / max(w, 1)
        wave = (math.sin(t + layer["phase"])
                + 0.5 * math.sin(2.3 * t + 2 * layer["phase"]))
        return h * (layer["base"] + layer["amp"] * wave)

    def _draw_turbine(self, p, x, ground_y, height, angle, alpha):
        taupe = QColor(COLORS["accent"])
        taupe.setAlpha(alpha)
        pen = QPen(taupe, 1.4)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        half_base = height * 0.045
        half_top = height * 0.022
        top_y = ground_y - height

        p.drawPolygon(QPolygonF([
            QPointF(x - half_base, ground_y),
            QPointF(x + half_base, ground_y),
            QPointF(x + half_top, top_y),
            QPointF(x - half_top, top_y),
        ]))

        nac_w, nac_h = height * 0.13, height * 0.05
        p.drawRoundedRect(
            QRectF(x - nac_w * 0.35, top_y - nac_h, nac_w, nac_h), 2, 2
        )

        hub = QPointF(x, top_y - nac_h * 0.5)
        p.drawEllipse(hub, height * 0.028, height * 0.028)

        blade_len = height * 0.46
        root = height * 0.03
        blade = QPolygonF([
            QPointF(0, -root * 0.5),
            QPointF(blade_len * 0.2, -root * 0.95),
            QPointF(blade_len, -root * 0.10),
            QPointF(blade_len, root * 0.10),
            QPointF(blade_len * 0.15, root * 0.55),
        ])

        for k in range(3):
            p.save()
            p.translate(hub)
            p.rotate(angle + k * 120.0)
            p.drawPolygon(blade)
            p.restore()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 14, 14)
        p.setClipPath(clip)

        sky = QLinearGradient(0, 0, 0, h)
        sky.setColorAt(0.0, QColor(COLORS["bg2"]))
        sky.setColorAt(1.0, QColor("#2B1D15"))
        p.fillRect(self.rect(), sky)

        # pale moon outline
        moon = QColor(COLORS["accent"])
        moon.setAlpha(70)
        p.setPen(QPen(moon, 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(w * 0.88, h * 0.2), 28, 28)

        left = w * 0.46
        span = w * 0.52

        for layer in self._LAYERS:
            line = QPainterPath()
            line.moveTo(0, self._ground(0, w, h, layer))
            x = 6
            while x <= w:
                line.lineTo(x, self._ground(x, w, h, layer))
                x += 6

            fill = QPainterPath(line)
            fill.lineTo(w, h)
            fill.lineTo(0, h)
            fill.closeSubpath()

            p.setPen(Qt.NoPen)
            p.setBrush(QColor(layer["fill"]))
            p.drawPath(fill)

            edge = QColor(COLORS["accent"])
            edge.setAlpha(layer["alpha"])
            p.setPen(QPen(edge, 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(line)

            for xf, tower, speed in layer["turbines"]:
                tx = left + span * xf
                ty = self._ground(tx, w, h, layer)
                self._draw_turbine(
                    p, tx, ty, tower, self._tick * speed, layer["alpha"] + 30
                )

        p.setClipping(False)
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 14, 14)


# ======================================================================
# Start page
# ======================================================================

class StartPage(QWidget):

    new_project_requested = Signal()
    open_project_requested = Signal(str)

    def __init__(self):
        super().__init__()

        self.setObjectName("StartPage")

        self._fade_targets = []
        self._animated = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_left())
        body.addWidget(self._build_right(), 1)
        root.addLayout(body, 1)

        root.addWidget(self._build_footer())

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self):
        header = QFrame()
        header.setObjectName("StartHeader")
        header.setFixedHeight(88)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(30, 0, 30, 0)
        layout.setSpacing(16)

        logo = QLabel()
        logo.setPixmap(pixmap("turbine", COLORS["accent"], 42))
        logo.setFixedSize(46, 46)

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addStretch()

        title = QLabel("Wind Turbine Structural Analyser")
        title.setObjectName("StartAppTitle")

        subtitle = QLabel(
            "Shell finite-element analysis of wind turbine structures"
        )
        subtitle.setObjectName("SecondaryText")

        text.addWidget(title)
        text.addWidget(subtitle)
        text.addStretch()

        chip = QLabel("v1.0")
        chip.setObjectName("HintText")

        layout.addWidget(logo)
        layout.addLayout(text)
        layout.addStretch()
        layout.addWidget(chip)

        return header

    # ------------------------------------------------------------------
    # Left column: start actions and recent projects
    # ------------------------------------------------------------------

    def _action_button(self, icon_name, title, description, primary=False):
        button = QPushButton()
        button.setObjectName(
            "StartActionPrimary" if primary else "StartAction"
        )
        button.setCursor(Qt.PointingHandCursor)
        button.setMinimumHeight(92)

        layout = QHBoxLayout(button)
        layout.setContentsMargins(22, 14, 22, 14)
        layout.setSpacing(18)

        glyph = QLabel()
        glyph.setPixmap(pixmap(
            icon_name,
            COLORS["on_primary"] if primary else COLORS["accent"],
            34,
        ))
        glyph.setFixedWidth(40)

        text = QVBoxLayout()
        text.setSpacing(3)
        text.addStretch()

        title_label = QLabel(title)
        title_label.setObjectName("StartActionTitle")

        desc_label = QLabel(description)
        desc_label.setObjectName(
            "StartActionDescPrimary" if primary else "SecondaryText"
        )
        desc_label.setWordWrap(True)

        text.addWidget(title_label)
        text.addWidget(desc_label)
        text.addStretch()

        layout.addWidget(glyph)
        layout.addLayout(text, 1)

        # let clicks fall through the labels to the button
        for child in (glyph, title_label, desc_label):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)

        GlowFilter(button, COLORS["accent"])

        return button

    def _build_left(self):
        left = QFrame()
        left.setObjectName("StartLeft")
        left.setFixedWidth(440)

        layout = QVBoxLayout(left)
        layout.setContentsMargins(28, 28, 28, 18)
        layout.setSpacing(12)

        start_label = QLabel("START")
        start_label.setObjectName("GroupLabel")
        layout.addWidget(start_label)

        self.new_button = self._action_button(
            "plus",
            "New Project",
            "Create a new wind turbine analysis project",
            primary=True,
        )
        self.new_button.clicked.connect(self.new_project_requested.emit)
        layout.addWidget(self.new_button)

        self.open_button = self._action_button(
            "folder",
            "Open Project…",
            "Browse for an existing project folder",
        )
        self.open_button.clicked.connect(self._browse_project)
        layout.addWidget(self.open_button)

        layout.addSpacing(14)

        recent_label = QLabel("RECENT PROJECTS")
        recent_label.setObjectName("GroupLabel")
        layout.addWidget(recent_label)

        self.recent_stack = QStackedWidget()

        self.recent_list = QListWidget()
        self.recent_list.setObjectName("RecentList")
        self.recent_list.setVerticalScrollMode(
            QListWidget.ScrollPerPixel
        )
        self.recent_list.itemActivated.connect(self._on_recent_activated)
        self.recent_stack.addWidget(self.recent_list)

        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(6)

        empty_icon = QLabel()
        empty_icon.setPixmap(pixmap("folder", COLORS["text3"], 36))
        empty_icon.setAlignment(Qt.AlignCenter)

        empty_title = QLabel("No recent projects")
        empty_title.setObjectName("EmptyTitle")
        empty_title.setAlignment(Qt.AlignCenter)

        empty_hint = QLabel("Projects you create or open will appear here.")
        empty_hint.setObjectName("HintText")
        empty_hint.setAlignment(Qt.AlignCenter)
        empty_hint.setWordWrap(True)

        empty_layout.addWidget(empty_icon)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_hint)
        self.recent_stack.addWidget(empty)

        self.recent_stack.setCurrentIndex(1)
        layout.addWidget(self.recent_stack, 1)

        tip = QLabel("Tip: double-click a project to open it.")
        tip.setObjectName("HintText")
        layout.addWidget(tip)

        return left

    # ------------------------------------------------------------------
    # Right column: getting started
    # ------------------------------------------------------------------

    def _build_right(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setObjectName("StartContent")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(16)

        hero = HeroBanner(
            "GETTING STARTED",
            "Structural analysis of wind turbines",
            "Study the structural behaviour of a wind turbine tower, "
            "nacelle, hub and blades under wind loading. Define the "
            "turbine, set up the wind case, solve, and review "
            "deformation, stress and failure wind speed.",
        )
        layout.addWidget(hero)
        self._fade_targets.append(hero)

        # ---- workflow ----
        layout.addSpacing(6)
        layout.addWidget(self._group_label("WORKFLOW"))

        steps = [
            ("01", "cube", "Geometry",
             "Built-in turbine model or STEP import"),
            ("02", "sliders", "Setup",
             "Material, wind and air conditions"),
            ("03", "bolt", "Solve",
             "Shell finite-element solution"),
            ("04", "chart", "Results",
             "Stress, strain, displacement, failure speed"),
        ]

        row = QHBoxLayout()
        row.setSpacing(10)
        for i, (number, icon_name, title, desc) in enumerate(steps):
            card = self._step_card(number, icon_name, title, desc)
            row.addWidget(card, 1)
            self._fade_targets.append(card)
            if i < len(steps) - 1:
                arrow = QLabel("›")
                arrow.setObjectName("StepArrow")
                arrow.setAlignment(Qt.AlignCenter)
                row.addWidget(arrow)
        layout.addLayout(row)

        # ---- capabilities ----
        layout.addSpacing(6)
        layout.addWidget(self._group_label("CAPABILITIES"))

        capabilities = [
            ("turbine", "Structural Analysis",
             "Evaluate the structural response of turbine components."),
            ("wind", "Wind Loading",
             "Study the effect of wind forces on the structure."),
            ("stress", "Stress & Failure Analysis",
             "Investigate stress, strain and the wind speed at first yield."),
            ("cube", "3D Visualisation",
             "View the turbine and its structural results in 3D."),
        ]

        grid = QGridLayout()
        grid.setSpacing(14)
        for i, (icon_name, title, desc) in enumerate(capabilities):
            card = self._capability_card(icon_name, title, desc)
            grid.addWidget(card, i // 2, i % 2)
            self._fade_targets.append(card)
        layout.addLayout(grid)

        # ---- assumptions ----
        layout.addSpacing(6)
        layout.addWidget(self._group_label("ANALYSIS ASSUMPTIONS"))

        assumptions = QFrame()
        assumptions.setObjectName("Panel")
        a_layout = QVBoxLayout(assumptions)
        a_layout.setContentsMargins(22, 18, 22, 18)
        a_layout.setSpacing(7)

        for line in (
            "Parked rotor, no rotor thrust",
            "Static, linear-elastic analysis of outer-surface shells",
            "Gusts, fatigue and rotor vibration are not modelled",
            "SI units internally (m, kg, N, Pa, s)",
        ):
            label = QLabel(f"•   {line}")
            label.setObjectName("SecondaryText")
            a_layout.addWidget(label)

        layout.addWidget(assumptions)
        self._fade_targets.append(assumptions)

        layout.addStretch()

        scroll.setWidget(content)
        return scroll

    def _group_label(self, text):
        label = QLabel(text)
        label.setObjectName("GroupLabel")
        return label

    def _step_card(self, number, icon_name, title, description):
        card = QFrame()
        card.setObjectName("Panel")
        card.setMinimumHeight(132)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        top = QHBoxLayout()
        number_label = QLabel(number)
        number_label.setObjectName("StepNumber")
        glyph = QLabel()
        glyph.setPixmap(pixmap(icon_name, COLORS["accent"], 20))
        top.addWidget(number_label)
        top.addStretch()
        top.addWidget(glyph)

        title_label = QLabel(title)
        title_label.setObjectName("StartActionTitle")

        desc_label = QLabel(description)
        desc_label.setObjectName("SecondaryText")
        desc_label.setWordWrap(True)

        layout.addLayout(top)
        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addStretch()

        return card

    def _capability_card(self, icon_name, title, description):
        card = QFrame()
        card.setObjectName("Panel")
        card.setMinimumHeight(104)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        glyph = QLabel()
        glyph.setPixmap(pixmap(icon_name, COLORS["accent"], 30))
        glyph.setFixedWidth(34)
        glyph.setAlignment(Qt.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("StartActionTitle")

        desc_label = QLabel(description)
        desc_label.setObjectName("SecondaryText")
        desc_label.setWordWrap(True)

        text.addWidget(title_label)
        text.addWidget(desc_label)
        text.addStretch()

        layout.addWidget(glyph)
        layout.addLayout(text, 1)

        return card

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------

    def _build_footer(self):
        footer = QFrame()
        footer.setObjectName("StartFooter")
        footer.setFixedHeight(34)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(8)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {COLORS['success']}; font-size: 8pt;")

        ready = QLabel("Ready")
        ready.setObjectName("SecondaryText")

        version = QLabel("Wind Turbine Structural Analyser  v1.0")
        version.setObjectName("HintText")

        layout.addWidget(dot)
        layout.addWidget(ready)
        layout.addStretch()
        layout.addWidget(version)

        return footer

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._animated:
            self._animated = True
            for index, widget in enumerate(self._fade_targets):
                fade_in(widget, 80 + index * 70)

    def _browse_project(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Open Project Folder"
        )
        if folder:
            self.open_project_requested.emit(folder)

    def _on_recent_activated(self, item):
        path = item.data(Qt.UserRole)
        if path:
            self.open_project_requested.emit(path)

    def _recent_row(self, name, opened_text):
        row = QFrame()
        row.setObjectName("RecentRow")

        layout = QVBoxLayout(row)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(1)

        name_label = QLabel(name)
        name_label.setStyleSheet("font-weight: bold;")

        date_label = QLabel(opened_text)
        date_label.setObjectName("HintText")

        layout.addWidget(name_label)
        layout.addWidget(date_label)

        # clicks pass through to the list item
        for widget in (row, name_label, date_label):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents)

        return row

    def update_recent_projects(self, projects):

        self.recent_list.clear()

        if not projects:
            self.recent_stack.setCurrentIndex(1)
            return

        self.recent_stack.setCurrentIndex(0)

        for project in projects:

            name = project.get("project_name", "Untitled project")
            path = project.get("project_path", "")

            try:
                opened = datetime.fromisoformat(
                    project.get("last_opened", "")
                ).strftime("Opened %d-%m-%Y %H:%M")
            except (ValueError, TypeError):
                opened = "Opened: unknown"

            item = QListWidgetItem()
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            item.setSizeHint(QSize(0, 58))

            self.recent_list.addItem(item)
            self.recent_list.setItemWidget(
                item, self._recent_row(name, opened)
            )