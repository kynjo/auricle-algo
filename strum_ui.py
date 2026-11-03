"""Compact Strum controls; choices use the existing source-feedback heartbeat."""
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from help_tooltips import bind_help
from strum import STRUM_PARAMETERS, STRUM_DIRECTIONS, STRUM_GATES, strum_values


class StrumChoice(QComboBox):
    def set_runtime_choice(self, manual, effective):
        index = self.findData(effective)
        if index >= 0 and index != self.currentIndex():
            with QSignalBlocker(self):
                self.setCurrentIndex(index)


class StrumPanel(QWidget):
    def __init__(self, host, block, knob_class, range_class, label_factory, parent=None):
        super().__init__(parent)
        self.setObjectName("strumPanel")
        values = strum_values(block.parameters)
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(8)
        self.knobs = []
        labels = {"strum_probability": "Chance", "strum_spacing": "Gap · beats",
                  "strum_dynamics": "Dynamics", "strum_humanize": "Humanize"}
        for key, (default, low, high) in STRUM_PARAMETERS.items():
            knob = (knob_class(values[key], default=default) if (low, high) == (0., 1.)
                    else range_class(low, high, values[key], default=default))
            knob.bind_parameter(block.id, key); knob.setObjectName(key)
            knob.setAccessibleName("Strum " + labels[key])
            knob.changed.connect(lambda value, k=key: host._set_param(block, k, float(value)))
            cell = QWidget(); cell.setFixedWidth(70)
            column = QVBoxLayout(cell); column.setContentsMargins(0, 0, 0, 0); column.setSpacing(0)
            title = label_factory(labels[key], knob); title.setAlignment(Qt.AlignCenter)
            title.setObjectName("knobLabel")
            column.addWidget(title); column.addWidget(knob, 0, Qt.AlignCenter)
            layout.addWidget(cell, 0, Qt.AlignTop); self.knobs.append(knob)
        choices = QWidget(); grid = QGridLayout(choices)
        grid.setContentsMargins(2, 3, 0, 0); grid.setHorizontalSpacing(6); grid.setVerticalSpacing(5)
        self.choices = {}
        for row, (key, label, options) in enumerate((
                ("strum_direction", "Direction", STRUM_DIRECTIONS),
                ("strum_gate_mode", "Gate", STRUM_GATES))):
            combo = StrumChoice(); combo.setObjectName(key); combo.setFixedWidth(148)
            for title, value in options:
                combo.addItem(title, value)
            combo.setCurrentIndex(combo.findData(values[key]))
            combo._auricle_parameter = (block.id, key)
            bind_help(combo, key)
            host._attach_automation_context(combo, block.id, key)
            combo.currentIndexChanged.connect(lambda _index, k=key, c=combo:
                                               host._set_param(block, k, c.currentData()))
            grid.addWidget(label_factory(label, combo), row, 0)
            grid.addWidget(combo, row, 1); self.choices[key] = combo
        note = QLabel("Chance 0 = bypass\nAuto fit to event length")
        note.setObjectName("muted")
        grid.addWidget(note, 2, 0, 1, 2)
        layout.addWidget(choices, 0, Qt.AlignTop); layout.addStretch(1)
