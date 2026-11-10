"""Turbine configuration dialog, built from Member 1's parameters.py.

dialog.dimensions is a flat dict {field_name: value} using Member 1's 12
field names. main.py saves it unchanged into config/model_config.json.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDoubleSpinBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

import parameters as P


def _get(spec, name, default=None):
    if isinstance(spec, dict):
        return spec.get(name, default)
    return getattr(spec, name, default)


def _parameter_specs():
    """Return [(field_name, spec)] whatever shape P.PARAMETERS has."""
    raw = P.PARAMETERS
    specs = []
    if isinstance(raw, dict):
        for key, spec in raw.items():
            specs.append((key, spec))
    else:
        for spec in raw:
            key = (_get(spec, "name") or _get(spec, "key")
                   or _get(spec, "id") or _get(spec, "field"))
            specs.append((key, spec))
    return specs


class TurbineConfigDialog(QDialog):

    def __init__(self, parent=None, initial_values=None):
        super().__init__(parent)
        self.setWindowTitle("Turbine Configuration")
        self.setMinimumSize(580, 700)

        self.dimensions = {}
        self._inputs = {}

        self._build()
        if initial_values:
            self.set_values(initial_values)
        else:
            self._reset()

    # ------------------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header
        header = QFrame()
        header.setObjectName("DialogHeader")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(24, 18, 24, 18)
        title = QLabel("Turbine Dimensions")
        title.setObjectName("DialogTitle")
        subtitle = QLabel("Built-in turbine. Lengths in metres, angles in degrees.")
        subtitle.setObjectName("HintText")
        hl.addWidget(title)
        hl.addWidget(subtitle)
        root.addWidget(header)

        # scrolling form, one group box per parameter group
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 18, 24, 18)
        cl.setSpacing(14)

        defaults = P.default_values()
        forms = {}
        for key, spec in _parameter_specs():
            group = _get(spec, "group", "Parameters")
            if group not in forms:
                box = QGroupBox(str(group))
                forms[group] = QFormLayout(box)
                cl.addWidget(box)

            spin = QDoubleSpinBox()
            lo = _get(spec, "min")
            hi = _get(spec, "max")
            spin.setRange(-1e9 if lo is None else float(lo),
                          1e9 if hi is None else float(hi))
            spin.setDecimals(3)
            spin.setSingleStep(0.1)
            unit = _get(spec, "unit", "")
            if unit:
                spin.setSuffix(f" {unit}")
            help_text = _get(spec, "help", "")
            if help_text:
                spin.setToolTip(str(help_text))
            spin.setValue(float(defaults.get(key, _get(spec, "default", 0.0))))
            spin.valueChanged.connect(self._revalidate)

            forms[group].addRow(str(_get(spec, "label", key)) + ":", spin)
            self._inputs[key] = spin

        cl.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # messages
        msg = QFrame()
        ml = QVBoxLayout(msg)
        ml.setContentsMargins(24, 6, 24, 6)
        self.error_label = QLabel()
        self.error_label.setObjectName("ErrorText")
        self.error_label.setWordWrap(True)
        self.warning_label = QLabel()
        self.warning_label.setObjectName("HintText")
        self.warning_label.setWordWrap(True)
        ml.addWidget(self.error_label)
        ml.addWidget(self.warning_label)
        root.addWidget(msg)

        # footer
        footer = QFrame()
        footer.setObjectName("DialogFooter")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(24, 12, 24, 12)
        reset = QPushButton("Reset to Defaults")
        reset.setObjectName("GhostButton")
        reset.clicked.connect(self._reset)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.generate_button = QPushButton("Generate Geometry")
        self.generate_button.setObjectName("PrimaryButton")
        self.generate_button.setDefault(True)
        self.generate_button.clicked.connect(self._accept)
        fl.addWidget(reset)
        fl.addStretch()
        fl.addWidget(cancel)
        fl.addWidget(self.generate_button)
        root.addWidget(footer)

    # ------------------------------------------------------------------
    def _values(self):
        return {key: spin.value() for key, spin in self._inputs.items()}

    def _revalidate(self, *_):
        try:
            errors, warnings = P.validate(self._values())
        except Exception as exc:          # never crash the dialog
            errors, warnings = [f"Validation failed: {exc}"], []

        self.error_label.setText("\n".join(f"\u2022 {e}" for e in errors))
        self.error_label.setVisible(bool(errors))
        self.warning_label.setText("\n".join(f"Note: {w}" for w in warnings))
        self.warning_label.setVisible(bool(warnings))
        self.generate_button.setEnabled(not errors)

    def _reset(self):
        defaults = P.default_values()
        self.set_values(defaults)

    def set_values(self, values):
        """Pre-fill every input from a flat {field_name: value} dict (e.g.
        the project's saved dimensions). Unknown keys are ignored."""
        for key, spin in self._inputs.items():
            if key in values:
                spin.blockSignals(True)
                spin.setValue(float(values[key]))
                spin.blockSignals(False)
        self._revalidate()

    def _accept(self):
        values = self._values()
        try:
            errors, _ = P.validate(values)
            if errors:
                self._revalidate()
                return
            P.apply_to_config(values)     # raises ValueError if invalid
        except ValueError as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.dimensions = values
        self.accept()