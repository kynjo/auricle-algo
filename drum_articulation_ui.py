"""One compact, timer-free Drum Voice articulation row."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from drum_articulation import ARTICULATION_PARAMETERS, articulation_values


class DrumArticulationPanel(QWidget):
    def __init__(self, host, voice, knob_class, range_class, label_factory, parent=None):
        super().__init__(parent)
        self.setObjectName("drumArticulationPanel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(8)
        self.knobs = []
        values = articulation_values(voice.parameters)
        labels = {"drum_ratchet_probability": "Chance", "drum_ratchet_count": "Count",
                  "drum_ratchet_spread": "Spread", "drum_ratchet_decay": "Decay",
                  "drum_flam_probability": "Chance", "drum_flam_spacing": "Gap · beats",
                  "drum_flam_velocity": "Grace vel"}
        for title, keys in (("RATCHET", tuple(ARTICULATION_PARAMETERS)[:4]),
                            ("FLAM", tuple(ARTICULATION_PARAMETERS)[4:])):
            group = QWidget()
            column = QVBoxLayout(group); column.setContentsMargins(2, 0, 2, 0); column.setSpacing(2)
            heading = QLabel(title); heading.setObjectName("knobLabel")
            column.addWidget(heading)
            row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(3)
            for key in keys:
                default, low, high = ARTICULATION_PARAMETERS[key]
                knob = (knob_class(values[key], default=default) if (low, high) == (0., 1.)
                        else range_class(low, high, values[key], integer=isinstance(default, int), default=default))
                knob.bind_parameter(voice.id, key)
                knob.setObjectName(key); knob.setAccessibleName(title + " " + labels[key])
                knob.changed.connect(lambda value, k=key: host._set_param(
                    voice, k, int(round(value)) if k == "drum_ratchet_count" else float(value)))
                cell = QWidget(); cell.setFixedWidth(70)
                stack = QVBoxLayout(cell); stack.setContentsMargins(0, 0, 0, 0); stack.setSpacing(0)
                caption = label_factory(labels[key], knob); caption.setAlignment(Qt.AlignCenter)
                caption.setObjectName("knobLabel")
                stack.addWidget(caption); stack.addWidget(knob, 0, Qt.AlignCenter)
                row.addWidget(cell); self.knobs.append(knob)
            column.addLayout(row)
            layout.addWidget(group, 0, Qt.AlignTop)
        layout.addStretch(1)
