"""Shared panel frame: a header (title + optional subtitle) above a body.

    panel = Panel("Outline")
    panel.body.addWidget(some_widget)

Styling: SidePanel / PanelHeader / PanelTitle / PanelSubtitle in styles.py.
"""
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


class Panel(QFrame):

    def __init__(self, title, subtitle="", parent=None):
        super().__init__(parent)
        self.setObjectName("SidePanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("PanelHeader")
        header.setFixedHeight(36)
        row = QHBoxLayout(header)
        row.setContentsMargins(12, 0, 12, 0)

        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("PanelTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("PanelSubtitle")

        row.addWidget(self.title_label)
        row.addStretch()
        row.addWidget(self.subtitle_label)
        root.addWidget(header)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        root.addLayout(self.body, 1)

    def set_subtitle(self, text):
        self.subtitle_label.setText(text)