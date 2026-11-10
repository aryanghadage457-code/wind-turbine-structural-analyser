"""Application theme: dark, built on the Onyx / Dark Coffee / Bitter Chocolate /
Dusty Taupe / Charcoal Brown palette, with the Inter font.

All colours and fonts live in COLORS / FONTS below. Change a value here and the
whole application follows. Other modules can import them:

    from gui.theme.styles import COLORS

main.py should call  install_theme(app)  once, right after creating QApplication.
It registers the bundled Inter fonts (assets/fonts) and applies the stylesheet.

Palette roles
    Onyx            #171614  window and canvas
    Dark Coffee     #3A2618  selected rows, pressed states
    Bitter Chocolate#754043  primary actions
    Dusty Taupe     #9A8873  highlights, focus rings, small labels
    Charcoal Brown  #37423D  card hover tint, subtle accents
"""
from pathlib import Path
from string import Template

COLORS = {
    # surfaces: Onyx and its lighter steps (a warm, slightly brown neutral ramp)
    "bg0": "#171614",        # window / canvas                 (Onyx)
    "bg1": "#1C1A18",        # side panels, headers, bars
    "bg2": "#221F1D",        # cards, panels
    "bg3": "#2A2724",        # inputs, neutral buttons
    "bg4": "#34302C",        # hover
    "card_hover": "#232A27", # card hover tint                 (Charcoal Brown, deepened)
    "charcoal": "#37423D",   # Charcoal Brown
    # lines
    "border": "#34302B",
    "border_strong": "#4A453E",
    "border_soft": "#262320",
    # text
    "text": "#F1ECE4",       # 15.4:1 on bg0
    "text2": "#B0A593",      # secondary
    "text3": "#8F8576",      # muted, 5.0:1 on bg0 (was too faint at 3.8:1)
    # highlight colour (Dusty Taupe)
    "accent": "#9A8873",
    "accent_hover": "#B5A28B",
    "accent_press": "#7F6F5C",
    "accent_dim": "#3A2618", # selected rows                  (Dark Coffee)
    "on_accent": "#171614",
    # primary action colour (Bitter Chocolate)
    "primary": "#754043",
    "primary_top": "#85494D",     # gradient top edge
    "primary_hover": "#8B4C50",
    "primary_hover_top": "#9A575B",
    "primary_press": "#613336",
    "on_primary": "#F6EFE8",
    "on_primary_soft": "#E9D6D2",
    # status
    "success": "#7FA38A",
    "warning": "#D1A85A",
    "danger": "#D4686B",
}

# Inter is bundled in assets/fonts. If it cannot be loaded Qt falls back down the list.
FONTS = {
    "body": '"Inter", "Segoe UI Variable Text", "Segoe UI", Arial',
    "display": '"Inter Display", "Inter", "Segoe UI Variable Display", "Segoe UI", Arial',
    "mono": 'Consolas, "Cascadia Mono", monospace',
}

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

_QSS = Template("""

/* ================================================== */
/*                     GLOBAL                         */
/* ================================================== */

QWidget {
    background-color: $bg0;
    color: $text;
    font-family: $body;
    font-size: 10pt;
}

QLabel {
    background-color: transparent;
    border: none;
}

QLabel#PageTitle {
    font-family: $display;
    font-size: 24pt;
    font-weight: bold;
    color: $text;
}

QLabel#SectionTitle {
    font-family: $display;
    font-size: 13pt;
    font-weight: bold;
    color: $text;
}

QLabel#SecondaryText {
    color: $text2;
}

QLabel#GroupLabel {
    color: $text3;
    font-family: $display;
    font-size: 8.5pt;
    font-weight: bold;
    letter-spacing: 2px;
}

QLabel#Eyebrow {
    color: $accent;
    font-family: $display;
    font-size: 9pt;
    font-weight: bold;
    letter-spacing: 3px;
}

QToolTip {
    background-color: $bg2;
    color: $text;
    border: 1px solid $accent;
    padding: 5px 9px;
}


/* ================================================== */
/*                  BUTTONS AND INPUTS                */
/* ================================================== */

QPushButton {
    background-color: $bg3;
    color: $text;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 8px 16px;
}

QPushButton:hover {
    background-color: $bg4;
    border: 1px solid $accent;
}

QPushButton:pressed {
    background-color: $accent_dim;
    border: 1px solid $accent_press;
}

QPushButton:focus {
    border: 1px solid $accent;
}

QPushButton:disabled {
    background-color: $bg2;
    color: $text3;
    border: 1px solid $border_soft;
}

QPushButton#PrimaryButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 $primary_top, stop:1 $primary);
    color: $on_primary;
    border: 1px solid $primary_hover;
    font-weight: bold;
}

QPushButton#PrimaryButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 $primary_hover_top, stop:1 $primary_hover);
    border: 1px solid $accent;
}

QPushButton#PrimaryButton:pressed {
    background-color: $primary_press;
    border: 1px solid $primary_press;
}

QPushButton#PrimaryButton:disabled {
    background-color: $bg3;
    color: $text3;
    border: 1px solid $border_soft;
}

QPushButton#GhostButton {
    background-color: transparent;
    border: 1px solid transparent;
    color: $text2;
}

QPushButton#GhostButton:hover {
    color: $text;
    border: 1px solid $border_strong;
    background-color: $bg3;
}

QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox {
    background-color: $bg3;
    color: $text;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: $accent;
    selection-color: $on_accent;
}

QLineEdit:hover,
QComboBox:hover,
QSpinBox:hover,
QDoubleSpinBox:hover {
    border: 1px solid $border_strong;
}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {
    border: 1px solid $accent;
    background-color: $bg2;
}

QLineEdit:disabled,
QComboBox:disabled,
QSpinBox:disabled,
QDoubleSpinBox:disabled {
    color: $text3;
    background-color: $bg1;
}

QLineEdit[invalid="true"] {
    border: 1px solid $danger;
}

QComboBox::drop-down {
    border: none;
    width: 26px;
}

QComboBox QAbstractItemView {
    background-color: $bg2;
    border: 1px solid $border_strong;
    selection-background-color: $accent_dim;
    selection-color: $text;
    outline: none;
}

QCheckBox {
    spacing: 9px;
    background-color: transparent;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid $border_strong;
    border-radius: 4px;
    background-color: $bg3;
}

QCheckBox::indicator:hover {
    border: 1px solid $accent;
}

QCheckBox::indicator:checked {
    background-color: $accent;
    border: 1px solid $accent;
}

QGroupBox {
    background-color: $bg2;
    border: 1px solid $border;
    border-radius: 10px;
    margin-top: 14px;
    padding: 14px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: $accent;
}


/* ================================================== */
/*                  PANELS AND CARDS                  */
/* ================================================== */

QFrame#Panel {
    background-color: $bg2;
    border: 1px solid $border;
    border-radius: 12px;
}

QFrame#ActionCard {
    background-color: $bg2;
    border: 1px solid $border;
    border-radius: 12px;
}

QFrame#ActionCard:hover {
    background-color: $card_hover;
    border: 1px solid $accent;
}


/* ================================================== */
/*                  TABLES / LISTS / SCROLL           */
/* ================================================== */

QTableWidget {
    background-color: $bg2;
    alternate-background-color: #1F1D1A;
    color: $text;
    gridline-color: $border_soft;
    border: 1px solid $border;
    border-radius: 8px;
}

QHeaderView::section {
    background-color: $bg3;
    color: $text2;
    padding: 9px;
    border: none;
    font-weight: bold;
}

QTableWidget::item:selected {
    background-color: $accent_dim;
    color: $text;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: $border_strong;
    min-height: 28px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: $accent;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: $border_strong;
    min-width: 28px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background: $accent;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
}

QMenu {
    background-color: $bg2;
    border: 1px solid $border_strong;
    border-radius: 8px;
    padding: 5px;
}

QMenu::item {
    padding: 8px 30px 8px 18px;
    border-radius: 6px;
}

QMenu::item:selected {
    background-color: $accent_dim;
}

QMenu::separator {
    height: 1px;
    background: $border;
    margin: 5px 8px;
}

QMessageBox {
    background-color: $bg1;
}


/* ================================================== */
/*                  DIALOGS                           */
/* ================================================== */

QDialog {
    background-color: $bg1;
}

QFrame#DialogHeader {
    background-color: $bg2;
    border-bottom: 1px solid $border;
}

QFrame#DialogFooter {
    background-color: $bg2;
    border-top: 1px solid $border;
}

QLabel#DialogGlyph {
    color: $accent;
    font-size: 22pt;
}

QLabel#DialogTitle {
    font-family: $display;
    font-size: 16pt;
    font-weight: bold;
}

QLabel#FieldLabel {
    color: $text2;
    font-family: $display;
    font-size: 8.5pt;
    font-weight: bold;
    letter-spacing: 1px;
}

QLabel#HintText {
    color: $text3;
    font-size: 8.5pt;
}

QLabel#ErrorText {
    color: $danger;
    font-size: 9pt;
}

QLabel#PathPreview {
    color: $text2;
    font-family: $mono;
    font-size: 9pt;
}


/* ================================================== */
/*                  START WINDOW                      */
/* ================================================== */

QFrame#StartHeader {
    background-color: $bg1;
    border-bottom: 1px solid $border;
}

QLabel#StartLogo {
    color: $accent;
    font-size: 26pt;
}

QLabel#StartAppTitle {
    font-family: $display;
    font-size: 16pt;
    font-weight: bold;
}

QFrame#StartLeft {
    background-color: $bg1;
    border-right: 1px solid $border;
}

QPushButton#StartAction {
    background-color: $bg2;
    border: 1px solid $border;
    border-radius: 12px;
    padding: 0px;
    text-align: left;
}

QPushButton#StartAction:hover {
    background-color: $card_hover;
    border: 1px solid $accent;
}

QPushButton#StartAction:pressed {
    background-color: $accent_dim;
}

QPushButton#StartActionPrimary {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 $primary_top, stop:1 $primary);
    border: 1px solid $primary_hover;
    border-radius: 12px;
    padding: 0px;
    text-align: left;
}

QPushButton#StartActionPrimary:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 $primary_hover_top, stop:1 $primary_hover);
    border: 1px solid $accent;
}

QPushButton#StartActionPrimary:pressed {
    background-color: $primary_press;
}

QLabel#StartActionGlyph {
    color: $accent;
    font-size: 20pt;
}

QLabel#StartActionGlyphPrimary {
    color: $on_primary;
    font-size: 20pt;
}

QLabel#StartActionTitle {
    font-family: $display;
    font-size: 11.5pt;
    font-weight: bold;
}

QPushButton#StartActionPrimary QLabel#StartActionTitle {
    color: $on_primary;
}

QLabel#StartActionDescPrimary {
    color: $on_primary_soft;
}

QLabel#VersionChip {
    border: 1px solid $border_strong;
    border-radius: 10px;
    padding: 2px 12px;
    color: $text2;
    font-size: 9pt;
}

QListWidget#RecentList {
    background-color: $bg1;
    border: none;
    outline: none;
}

QListWidget#RecentList::item {
    padding: 9px 10px;
    margin: 2px 0px;
}

QListWidget#RecentList::item:hover {
    background-color: $bg3;
    border-radius: 10px;
}

QListWidget#RecentList::item:selected {
    background-color: $accent_dim;
    border-radius: 10px;
    color: $text;
}

QFrame#RecentRow {
    background-color: transparent;
}

QLabel#EmptyTitle {
    font-weight: bold;
    color: $text2;
}

QFrame#StartFooter {
    background-color: $bg1;
    border-top: 1px solid $border;
}

QLabel#StepNumber {
    color: $accent;
    font-family: $display;
    font-weight: bold;
    font-size: 10pt;
}

QLabel#StepArrow {
    color: $text3;
    font-size: 18pt;
}


/* ================================================== */
/*       SIDEBAR  (used by the current main_window)   */
/* ================================================== */

QFrame#Sidebar {
    background-color: $bg1;
    border-right: 1px solid $border;
}

QPushButton#NavButton {
    background-color: transparent;
    color: $text2;
    border: none;
    text-align: left;
    padding: 12px 16px;
    border-radius: 8px;
}

QPushButton#NavButton:hover {
    background-color: $bg3;
    color: $text;
}

QPushButton#ActiveNavButton {
    background-color: $bg3;
    color: $accent;
    border-left: 3px solid $accent;
    text-align: left;
    padding: 12px 16px;
}


/* ================================================== */
/*                WORKSPACE: RIBBON                   */
/* ================================================== */

QFrame#RibbonTabRow {
    background-color: $bg1;
    border-bottom: 1px solid $border;
}

QPushButton#FileTab {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 $primary_top, stop:1 $primary);
    color: $on_primary;
    border: none;
    border-radius: 0px;
    padding: 6px 20px;
    font-weight: bold;
}

QPushButton#FileTab:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 $primary_hover_top, stop:1 $primary_hover);
}

QPushButton#FileTab::menu-indicator {
    image: none;
}

QTabBar#RibbonTabBar {
    background: transparent;
}

QTabBar#RibbonTabBar::tab {
    background: transparent;
    color: $text2;
    padding: 9px 20px;
    border: none;
    border-bottom: 2px solid transparent;
}

QTabBar#RibbonTabBar::tab:hover {
    color: $text;
    background-color: $bg2;
}

QTabBar#RibbonTabBar::tab:selected {
    color: $text;
    background-color: $bg2;
    border-bottom: 2px solid $accent;
}

QLabel#RibbonProject {
    color: $text2;
    padding-right: 16px;
}

QFrame#RibbonBody {
    background-color: $bg2;
    border-bottom: 1px solid $border;
}

QFrame#RibbonGroup {
    background-color: transparent;
    border-right: 1px solid $border;
}

QLabel#RibbonGroupLabel {
    color: $text3;
    font-size: 8pt;
}

QToolButton#RibbonButton {
    background-color: transparent;
    color: $text;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 8px;
    min-width: 60px;
}

QToolButton#RibbonButton:hover {
    background-color: $bg4;
    border: 1px solid $accent;
}

QToolButton#RibbonButton:checked {
    background-color: $accent_dim;
    border: 1px solid $accent;
}

QToolButton#RibbonButton:disabled {
    color: $text3;
}


/* ================================================== */
/*                WORKSPACE: PANELS                   */
/* ================================================== */

QFrame#SidePanel {
    background-color: $bg1;
    border: 1px solid $border;
}

QFrame#PanelHeader {
    background-color: $bg2;
    border-bottom: 1px solid $border;
}

QLabel#PanelTitle {
    font-family: $display;
    font-weight: bold;
    color: $text;
}

QLabel#PanelSubtitle {
    color: $text2;
    font-size: 9pt;
}

QTreeWidget#OutlineTree {
    background-color: $bg1;
    border: none;
    outline: none;
}

QTreeWidget#OutlineTree::item {
    padding: 4px 2px;
}

QTreeWidget#OutlineTree::item:hover {
    background-color: $bg2;
}

QTreeWidget#OutlineTree::item:selected {
    background-color: $accent_dim;
    color: $text;
}

QTableWidget#DetailsTable {
    background-color: $bg1;
    alternate-background-color: $bg1;
    border: none;
    border-radius: 0px;
    gridline-color: $border_soft;
}

QTableWidget#DetailsTable::item {
    padding: 4px 6px;
}

QFrame#GraphicsToolbar {
    background-color: $bg2;
    border-bottom: 1px solid $border;
}

QToolButton#ViewButton {
    background-color: transparent;
    color: $text;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 12px;
}

QToolButton#ViewButton:hover {
    background-color: $bg4;
    border: 1px solid $accent;
}

QToolButton#ViewButton:checked {
    background-color: $accent_dim;
    border: 1px solid $accent;
}

QTabWidget#BottomDock::pane {
    border: 1px solid $border;
    background-color: $bg1;
}

QTabWidget#BottomDock QTabBar::tab {
    background-color: $bg2;
    color: $text2;
    padding: 7px 20px;
    border: 1px solid $border;
    border-bottom: none;
}

QTabWidget#BottomDock QTabBar::tab:selected {
    background-color: $bg1;
    color: $text;
    border-top: 2px solid $accent;
}

QPlainTextEdit#LogView {
    background-color: $bg0;
    border: none;
    font-family: $mono;
    font-size: 9pt;
    color: $text2;
}

QFrame#StatusBar {
    background-color: $bg1;
    border-top: 1px solid $border;
}

QFrame#StatusBar QLabel {
    color: $text2;
    font-size: 9pt;
}

QProgressBar {
    background-color: $bg3;
    border: none;
    border-radius: 3px;
    max-height: 8px;
}

QProgressBar::chunk {
    background-color: $accent;
    border-radius: 3px;
}

QSplitter::handle {
    background-color: $bg0;
}

QSplitter::handle:horizontal {
    width: 3px;
}

QSplitter::handle:vertical {
    height: 3px;
}

""")

APP_STYLESHEET = _QSS.substitute({**COLORS, **FONTS})


def install_theme(app):
    """Register the bundled fonts, set the default font and apply the stylesheet."""
    from PySide6.QtGui import QFont, QFontDatabase

    loaded = 0
    if FONT_DIR.is_dir():
        for ttf in sorted(FONT_DIR.glob("*.ttf")):
            if QFontDatabase.addApplicationFont(str(ttf)) != -1:
                loaded += 1
    if loaded:
        app.setFont(QFont("Inter", 10))
    app.setStyleSheet(APP_STYLESHEET)
    return loaded