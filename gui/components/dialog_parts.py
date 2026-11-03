"""Reusable header and footer for the application dialogs.

    root.addWidget(make_header("sliders", "Title", "Subtitle"))
    ...
    root.addWidget(make_footer(cancel_button, primary_button))

Styling comes entirely from the DialogHeader / DialogFooter / DialogTitle
rules in gui/theme/styles.py.
"""
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from gui.theme.icons import pixmap
from gui.theme.styles import COLORS


def make_header(icon_name, title, subtitle):

    header = QFrame()
    header.setObjectName("DialogHeader")

    layout = QHBoxLayout(header)
    layout.setContentsMargins(26, 20, 26, 20)
    layout.setSpacing(16)

    glyph = QLabel()
    glyph.setPixmap(pixmap(icon_name, COLORS["accent"], 34))
    glyph.setFixedSize(38, 38)

    text = QVBoxLayout()
    text.setSpacing(2)

    title_label = QLabel(title)
    title_label.setObjectName("DialogTitle")

    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("SecondaryText")
    subtitle_label.setWordWrap(True)

    text.addWidget(title_label)
    text.addWidget(subtitle_label)

    layout.addWidget(glyph)
    layout.addLayout(text, 1)

    return header


def make_footer(*buttons):
    """Right-aligned button row. Pass the buttons left to right."""

    footer = QFrame()
    footer.setObjectName("DialogFooter")

    layout = QHBoxLayout(footer)
    layout.setContentsMargins(26, 14, 26, 14)
    layout.setSpacing(10)
    layout.addStretch()

    for button in buttons:
        button.setMinimumHeight(38)
        button.setMinimumWidth(110)
        layout.addWidget(button)

    return footer