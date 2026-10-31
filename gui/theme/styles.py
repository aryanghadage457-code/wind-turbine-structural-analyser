APP_STYLESHEET = """

/* ---------------- GLOBAL WINDOW ---------------- */

QWidget {
    background-color: #17191D;
    color: #F2F3F5;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QLabel {
    background-color: transparent;
    border: none;
}
QPushButton {
    background-color: #343941;
    color: white;
    border: 1px solid #414751;  
    border-radius: 5px;
    padding: 8px 14px;
}


/* ---------------- SIDEBAR ---------------- */

QFrame#Sidebar {
    background-color: #202329;
    border-right: 1px solid #414751;
}

QPushButton#NavButton {
    background-color: transparent;
    color: #A5ABB4;
    border: none;
    text-align: left;
    padding: 12px 16px;
    border-radius: 5px;
}

QPushButton#NavButton:hover {
    background-color: #343941;
    color: #FFFFFF;
}

QPushButton#ActiveNavButton {
    background-color: #343941;
    color: #00B8D9;
    border-left: 3px solid #0078D4;
    text-align: left;
    padding: 12px 16px;
}


/* ---------------- PANELS AND CARDS ---------------- */

QFrame#Panel {
    background-color: #292D34;
    border: 1px solid #414751;
    border-radius: 8px;
}

QFrame#ActionCard {
    background-color: #292D34;
    border: 1px solid #414751;
    border-radius: 8px;
}

QFrame#ActionCard:hover {
    border: 1px solid #0078D4;
}


/* ---------------- BUTTONS ---------------- */

QPushButton {
    background-color: #343941;
    color: #F2F3F5;
    border: 1px solid #414751;
    border-radius: 5px;
    padding: 8px 14px;
}

QPushButton:hover {
    background-color: #3A414B;
    border: 1px solid #0078D4;
}

QPushButton#PrimaryButton {
    background-color: #0078D4;
    color: white;
    border: none;
    font-weight: bold;
}

QPushButton#PrimaryButton:hover {
    background-color: #168BE5;
}


/* ---------------- INPUT FIELDS ---------------- */

QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox {
    background-color: #343941;
    color: #F2F3F5;
    border: 1px solid #414751;
    border-radius: 4px;
    padding: 7px;
}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {
    border: 1px solid #0078D4;
}


/* ---------------- TABLES ---------------- */

QTableWidget {
    background-color: #292D34;
    alternate-background-color: #252930;
    color: #F2F3F5;
    gridline-color: #414751;
    border: 1px solid #414751;
    border-radius: 5px;
}

QHeaderView::section {
    background-color: #343941;
    color: #A5ABB4;
    padding: 9px;
    border: none;
    font-weight: bold;
}

QTableWidget::item:selected {
    background-color: #005A9E;
}


/* ---------------- SCROLLBARS ---------------- */

QScrollBar:vertical {
    background: #202329;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #505761;
    min-height: 25px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #0078D4;
}


/* ---------------- LABELS ---------------- */

QLabel#PageTitle {
    font-size: 22pt;
    font-weight: bold;
    color: #F2F3F5;
}

QLabel#SectionTitle {
    font-size: 13pt;
    font-weight: bold;
    color: #F2F3F5;
}

QLabel#SecondaryText {
    color: #A5ABB4;
}


/* ---------------- DIALOGS ---------------- */

QMessageBox {
    background-color: #202329;
}

QToolTip {
    background-color: #292D34;
    color: #F2F3F5;
    border: 1px solid #0078D4;
}

"""