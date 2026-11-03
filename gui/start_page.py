"""Starting Window (ANSYS-style start screen).

Public interface used by main.py (unchanged):
    signals   new_project_requested(), open_project_requested(str path)
    methods   update_recent_projects(projects), show_empty_projects()
"""
from datetime import datetime

from PySide6.QtCore import (
    QEasingCurve, QParallelAnimationGroup, QPauseAnimation, QPropertyAnimation,
    QSequentialAnimationGroup, QSize, QVariantAnimation, Qt, Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

APP_NAME = "Wind Turbine Structural Analyser"
APP_TAGLINE = "Shell finite-element analysis of wind turbine structures"
APP_VERSION = "v1.0"


# ---------------------------------------------------------------- animation helpers
def fade_in(widgets, delay=0, step=70, duration=380):
    """Fade widgets in one after another. Returns the animation group.

    The opacity effect is removed when finished so normal rendering resumes.
    """
    group = QParallelAnimationGroup()
    effects = []
    for i, w in enumerate(widgets):
        fx = QGraphicsOpacityEffect(w)
        fx.setOpacity(0.0)
        w.setGraphicsEffect(fx)
        effects.append((w, fx))
        seq = QSequentialAnimationGroup()
        seq.addAnimation(QPauseAnimation(delay + i * step))
        anim = QPropertyAnimation(fx, b"opacity")
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        seq.addAnimation(anim)
        group.addAnimation(seq)

    def cleanup():
        for w, fx in effects:
            try:
                if w.graphicsEffect() is fx:
                    w.setGraphicsEffect(None)
            except RuntimeError:
                pass  # widget already deleted

    group.finished.connect(cleanup)
    group.start()
    return group


class GlowButton(QPushButton):
    """Button with an animated glow on hover and a stronger pulse on press."""

    def __init__(self, glow="#00B8D9", parent=None):
        super().__init__(parent)
        self._glow = QColor(glow)
        self._glow.setAlpha(170)
        self._fx = None
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._apply)
        self.setCursor(Qt.PointingHandCursor)

    def _ensure_effect(self):
        if self._fx is None:  # installed lazily so it never clashes with the intro fade
            self._fx = QGraphicsDropShadowEffect(self)
            self._fx.setOffset(0, 0)
            self._fx.setColor(self._glow)
            self._fx.setBlurRadius(0)
            self.setGraphicsEffect(self._fx)

    def _apply(self, value):
        if self._fx is not None:
            self._fx.setBlurRadius(float(value))

    def _go(self, target):
        self._ensure_effect()
        self._anim.stop()
        self._anim.setStartValue(float(self._fx.blurRadius()))
        self._anim.setEndValue(float(target))
        self._anim.start()

    def enterEvent(self, event):
        self._go(22)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._go(0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._go(38)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._go(22 if self.underMouse() else 0)
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------- small widgets
def action_button(glyph, title, description, primary=False):
    """Large clickable row: glyph + title + description."""
    btn = GlowButton("#0078D4" if primary else "#00B8D9")
    btn.setObjectName("StartActionPrimary" if primary else "StartAction")
    btn.setMinimumHeight(80)
    btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    row = QHBoxLayout(btn)
    row.setContentsMargins(18, 10, 18, 10)
    row.setSpacing(16)

    g = QLabel(glyph)
    g.setObjectName("StartActionGlyphPrimary" if primary else "StartActionGlyph")
    g.setFixedWidth(40)
    g.setAlignment(Qt.AlignCenter)

    text = QVBoxLayout()
    text.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("StartActionTitle")
    d = QLabel(description)
    d.setObjectName("StartActionDescPrimary" if primary else "SecondaryText")
    d.setWordWrap(True)
    text.addStretch()
    text.addWidget(t)
    text.addWidget(d)
    text.addStretch()

    row.addWidget(g)
    row.addLayout(text, 1)
    for w in (g, t, d):
        w.setAttribute(Qt.WA_TransparentForMouseEvents)
    return btn


def info_card(top, title, description, min_height=118):
    card = QFrame()
    card.setObjectName("ActionCard")
    card.setMinimumHeight(min_height)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(6)
    n = QLabel(top)
    n.setObjectName("StepNumber")
    t = QLabel(title)
    t.setStyleSheet("font-weight: bold; font-size: 11pt;")
    d = QLabel(description)
    d.setObjectName("SecondaryText")
    d.setWordWrap(True)
    lay.addWidget(n)
    lay.addWidget(t)
    lay.addWidget(d)
    lay.addStretch()
    return card


def group_label(text):
    l = QLabel(text.upper())
    l.setObjectName("GroupLabel")
    return l


class RecentRow(QFrame):
    def __init__(self, name, meta, path):
        super().__init__()
        self.setObjectName("RecentRow")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(3)
        n = QLabel(name)
        n.setStyleSheet("font-weight: bold; font-size: 10.5pt; padding: 0px 0px 3px 0px; margin: 0px;")
        n.setMinimumHeight(24)
        m = QLabel(meta)
        m.setObjectName("SecondaryText")
        m.setStyleSheet("font-size: 8.5pt;")
        lay.addWidget(n)
        lay.addWidget(m)
        self.setToolTip(path)


# ---------------------------------------------------------------- page
class StartPage(QWidget):

    new_project_requested = Signal()
    open_project_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("StartPage")
        self._anims = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.left = self._build_left()
        body.addWidget(self.left)
        body.addWidget(self._build_right(), 1)
        root.addLayout(body, 1)

        root.addWidget(self._build_footer())

        self.show_empty_projects()

    # ------------------------------------------------------------ header
    def _build_header(self):
        header = QFrame()
        header.setObjectName("StartHeader")
        header.setFixedHeight(76)
        lay = QHBoxLayout(header)
        lay.setContentsMargins(28, 0, 28, 0)
        lay.setSpacing(14)

        logo = QLabel("◈")
        logo.setObjectName("StartLogo")

        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addStretch()
        title = QLabel(APP_NAME)
        title.setObjectName("StartAppTitle")
        tag = QLabel(APP_TAGLINE)
        tag.setObjectName("SecondaryText")
        titles.addWidget(title)
        titles.addWidget(tag)
        titles.addStretch()

        chip = QLabel(APP_VERSION)
        chip.setObjectName("VersionChip")

        lay.addWidget(logo)
        lay.addLayout(titles)
        lay.addStretch()
        chip.setFixedHeight(24)
        lay.addWidget(chip, 0, Qt.AlignVCenter)
        return header

    # ------------------------------------------------------------ left column
    def _build_left(self):
        left = QFrame()
        left.setObjectName("StartLeft")
        left.setFixedWidth(410)
        lay = QVBoxLayout(left)
        lay.setContentsMargins(26, 26, 26, 20)
        lay.setSpacing(12)

        lay.addWidget(group_label("Start"))

        self.new_btn = action_button(
            "＋", "New Project",
            "Create a new wind turbine analysis project", primary=True)
        self.new_btn.clicked.connect(self.new_project_requested.emit)
        lay.addWidget(self.new_btn)

        self.open_btn = action_button(
            "▣", "Open Project…",
            "Browse for an existing project folder")
        self.open_btn.clicked.connect(self._browse_project)
        lay.addWidget(self.open_btn)

        lay.addSpacing(14)
        lay.addWidget(group_label("Recent Projects"))

        self.recent_stack = QStackedWidget()

        self.recent_list = QListWidget()
        self.recent_list.setObjectName("RecentList")
        self.recent_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.recent_list.itemDoubleClicked.connect(self._open_item)
        self.recent_list.itemActivated.connect(self._open_item)

        empty = QWidget()
        elay = QVBoxLayout(empty)
        elay.setAlignment(Qt.AlignCenter)
        eg = QLabel("▤")
        eg.setAlignment(Qt.AlignCenter)
        eg.setStyleSheet("color: #414751; font-size: 30pt;")
        et = QLabel("No recent projects")
        et.setObjectName("EmptyTitle")
        et.setAlignment(Qt.AlignCenter)
        ed = QLabel("Projects you create or open will appear here.")
        ed.setObjectName("SecondaryText")
        ed.setAlignment(Qt.AlignCenter)
        ed.setWordWrap(True)
        for w in (eg, et, ed):
            elay.addWidget(w)
        empty.setStyleSheet("background-color: #202329;")
        for w in (eg, et, ed):
            w.setStyleSheet(w.styleSheet() + "background: transparent;")

        self.recent_stack.addWidget(empty)            # index 0
        self.recent_stack.addWidget(self.recent_list)  # index 1
        lay.addWidget(self.recent_stack, 1)

        tip = QLabel("Tip: double-click a project to open it.")
        tip.setObjectName("SecondaryText")
        tip.setStyleSheet("font-size: 8.5pt;")
        lay.addWidget(tip)
        return left

    # ------------------------------------------------------------ right column
    def _build_right(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(48, 38, 48, 34)
        lay.setSpacing(14)
        self._intro = []

        def add(widget):
            lay.addWidget(widget)
            self._intro.append(widget)
            return widget

        eyebrow = QLabel("GETTING STARTED")
        eyebrow.setObjectName("Eyebrow")
        add(eyebrow)

        title = QLabel("Structural analysis of wind turbines")
        title.setObjectName("PageTitle")
        title.setWordWrap(True)
        add(title)

        intro = QLabel(
            "Study the structural behaviour of a wind turbine tower, nacelle, hub "
            "and blades under wind loading. Define the turbine, set up the wind "
            "case, solve, and review deformation, stress and failure wind speed."
        )
        intro.setObjectName("SecondaryText")
        intro.setWordWrap(True)
        add(intro)

        lay.addSpacing(10)
        add(group_label("Workflow"))

        steps = [
            ("01", "Geometry", "Built-in turbine model or STEP import"),
            ("02", "Setup", "Material, wind and air conditions"),
            ("03", "Solve", "Shell finite-element solution"),
            ("04", "Results", "Stress, strain, displacement, failure speed"),
        ]
        flow = QHBoxLayout()
        flow.setSpacing(10)
        flow_holder = QWidget()
        flow_holder.setObjectName("FlowHolder")
        flow_holder.setLayout(flow)
        flow.setContentsMargins(0, 0, 0, 0)
        for i, (n, t, d) in enumerate(steps):
            flow.addWidget(info_card(n, t, d, 124), 1)
            if i < len(steps) - 1:
                arrow = QLabel("›")
                arrow.setObjectName("StepArrow")
                flow.addWidget(arrow)
        add(flow_holder)

        lay.addSpacing(10)
        add(group_label("Capabilities"))

        caps = [
            ("●", "Structural Analysis", "Evaluate the structural response of turbine components."),
            ("●", "Wind Loading", "Study the effect of wind forces on the structure."),
            ("●", "Stress & Failure Analysis", "Investigate stress, strain and the wind speed at first yield."),
            ("●", "3D Visualisation", "View the turbine and its structural results in 3D."),
        ]
        grid = QGridLayout()
        grid.setSpacing(14)
        grid_holder = QWidget()
        grid_holder.setLayout(grid)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, (g, t, d) in enumerate(caps):
            grid.addWidget(info_card(g, t, d, 100), i // 2, i % 2)
        add(grid_holder)

        lay.addSpacing(10)
        add(group_label("Analysis assumptions"))

        panel = QFrame()
        panel.setObjectName("Panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(20, 16, 20, 16)
        pl.setSpacing(6)
        for line in (
            "Parked rotor, no rotor thrust",
            "Static, linear-elastic analysis of outer-surface shells",
            "Gusts, fatigue and rotor vibration are not modelled",
            "SI units internally (m, kg, N, Pa, s)",
        ):
            l = QLabel("•  " + line)
            l.setObjectName("SecondaryText")
            pl.addWidget(l)
        add(panel)

        lay.addStretch()
        scroll.setWidget(content)
        return scroll

    # ------------------------------------------------------------ footer
    def _build_footer(self):
        footer = QFrame()
        footer.setObjectName("StartFooter")
        footer.setFixedHeight(30)
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(20, 0, 20, 0)
        ready = QLabel('<span style="color:#4CAF50;">●</span>  Ready')
        ready.setObjectName("SecondaryText")
        ver = QLabel(f"{APP_NAME}  {APP_VERSION}")
        ver.setObjectName("SecondaryText")
        lay.addWidget(ready)
        lay.addStretch()
        lay.addWidget(ver)
        return footer

    # ------------------------------------------------------------ intro animation
    def play_intro(self):
        for g in self._anims:
            g.stop()
        self._anims = [
            fade_in([self.left], delay=0, duration=420),
            fade_in(self._intro, delay=120, step=75, duration=420),
        ]

    def showEvent(self, event):
        super().showEvent(event)
        if not event.spontaneous():
            self.play_intro()

    # ------------------------------------------------------------ actions
    def _browse_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Project Folder")
        if folder:
            self.open_project_requested.emit(folder)

    def _open_item(self, item):
        path = item.data(Qt.UserRole)
        if path:
            self.open_project_requested.emit(path)

    # ------------------------------------------------------------ recent projects
    def show_empty_projects(self):
        self.recent_list.clear()
        self.recent_stack.setCurrentIndex(0)

    def update_recent_projects(self, projects):
        self.recent_list.clear()
        if not projects:
            self.show_empty_projects()
            return

        for project in projects:
            try:
                date = datetime.fromisoformat(project.get("last_opened", ""))
                when = date.strftime("%d-%m-%Y %H:%M")
            except (ValueError, TypeError):
                when = "-"

            path = project["project_path"]
            row = RecentRow(project["project_name"], f"Opened {when}", path)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, path)
            item.setSizeHint(QSize(0, row.sizeHint().height() + 14))
            self.recent_list.addItem(item)
            self.recent_list.setItemWidget(item, row)

        self.recent_stack.setCurrentIndex(1)