"""Qt editors for per-block MIDI expression and global MIDI clock sync."""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QGroupBox, QDialog, QDialogButtonBox,
)

from help_tooltips import bind_help, bind_attributes, bind_table

from midi_expression import normalize_expression, normalize_midi_sync, MAX_CC_LANES
from composition_curve_ui import MacroCurveEditor


def _points_text(points):
    return ", ".join(f"{float(x):g}:{float(y):g}" for x, y in points)


def _parse_points(text, fallback):
    result = []
    for chunk in str(text or "").split(","):
        parts = chunk.strip().split(":")
        if len(parts) != 2:
            continue
        try:
            result.append([float(parts[0]), float(parts[1])])
        except (TypeError, ValueError, OverflowError):
            continue
    return result or deepcopy(fallback)


class MidiExpressionEditor(QWidget):
    """Compact but complete editor for CC lanes, Pitch Bend and Aftertouch."""
    changed = Signal(dict)

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self._config = normalize_expression(config)
        self._loading = False
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(6)

        cc_group = QGroupBox("CC AUTOMATION")
        cc_layout = QVBoxLayout(cc_group)
        cc_layout.setContentsMargins(6, 6, 6, 6)
        cc_layout.setSpacing(4)
        cc_hint = QLabel("Multiple controller lanes (one lane per CC number). Points use normalized time:value pairs, e.g. 0:0.15, 0.5:0.8, 1:0.3.")
        cc_hint.setWordWrap(True)
        cc_hint.setObjectName("muted")
        cc_layout.addWidget(cc_hint)
        self.cc_table = QTableWidget(0, 9)
        self.cc_table.setHorizontalHeaderLabels(["On", "CC", "Min", "Max", "Curve", "Period (beats)", "Rate (beats)", "Timebase", "Points"])
        self.cc_table.verticalHeader().setVisible(False)
        self.cc_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cc_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.cc_table.setMinimumHeight(92)
        self.cc_table.setMaximumHeight(180)
        self.cc_table.horizontalHeader().setStretchLastSection(True)
        self.cc_table.setToolTip("CC values are sampled on the shared Musical Clock. Period controls the curve cycle; Rate controls the maximum update frequency.")
        self.cc_table.itemChanged.connect(self._cc_item_changed)
        self.cc_table.currentCellChanged.connect(self._cc_selection_changed)
        cc_layout.addWidget(self.cc_table)
        self.cc_curve = MacroCurveEditor("#6eafea", self)
        self.cc_curve.setAccessibleName("CC automation curve")
        self.cc_curve.curveChanged.connect(self._cc_curve_changed)
        cc_layout.addWidget(self.cc_curve)
        cc_buttons = QHBoxLayout()
        self.add_cc_button = QPushButton("+ CC lane")
        self.remove_cc_button = QPushButton("Remove selected")
        self.add_cc_button.clicked.connect(self._add_cc_lane)
        self.remove_cc_button.clicked.connect(self._remove_cc_lane)
        cc_buttons.addWidget(self.add_cc_button)
        cc_buttons.addWidget(self.remove_cc_button)
        cc_buttons.addStretch(1)
        cc_layout.addLayout(cc_buttons)
        root.addWidget(cc_group)

        bend_group = QGroupBox("PITCH BEND")
        bend = QGridLayout(bend_group)
        bend.setContentsMargins(6, 6, 6, 6)
        self.bend_enabled = QCheckBox("Enable")
        self.bend_range = QSpinBox(); self.bend_range.setRange(1, 24); self.bend_range.setSuffix(" semitones")
        self.bend_shape = QComboBox(); self.bend_shape.addItems(["Linear", "Smooth", "Step"])
        self.bend_period = QDoubleSpinBox(); self._setup_beat_spin(self.bend_period, 4.0)
        self.bend_rate = QDoubleSpinBox(); self._setup_beat_spin(self.bend_rate, .25, .0625, 16.0)
        self.bend_timebase = QComboBox(); self.bend_timebase.addItem("Loop", "loop"); self.bend_timebase.addItem("Section", "section")
        self.bend_points = QLineEdit(); self.bend_points.setPlaceholderText("0:0.5, 1:0.5")
        self.bend_points.setToolTip("Normalized curve: 0 = maximum down, 0.5 = center, 1 = maximum up.")
        bend.addWidget(self.bend_enabled, 0, 0)
        bend.addWidget(QLabel("Range"), 0, 1); bend.addWidget(self.bend_range, 0, 2)
        bend.addWidget(QLabel("Shape"), 0, 3); bend.addWidget(self.bend_shape, 0, 4)
        bend.addWidget(QLabel("Period"), 1, 0); bend.addWidget(self.bend_period, 1, 1)
        bend.addWidget(QLabel("Rate"), 1, 2); bend.addWidget(self.bend_rate, 1, 3)
        bend.addWidget(self.bend_timebase, 1, 4)
        bend.addWidget(QLabel("Points"), 2, 0); bend.addWidget(self.bend_points, 2, 1, 1, 4)
        self.bend_curve = MacroCurveEditor("#ed8b62", self)
        self.bend_curve.setAccessibleName("Pitch Bend automation curve")
        self.bend_curve.curveChanged.connect(self._bend_curve_changed)
        bend.addWidget(self.bend_curve, 3, 0, 1, 5)
        root.addWidget(bend_group)

        after_group = QGroupBox("AFTERTOUCH")
        after = QGridLayout(after_group)
        after.setContentsMargins(6, 6, 6, 6)
        self.after_enabled = QCheckBox("Enable")
        self.after_mode = QComboBox(); self.after_mode.addItem("Channel", "channel"); self.after_mode.addItem("Polyphonic", "polyphonic")
        self.after_sensitivity = QDoubleSpinBox(); self.after_sensitivity.setRange(0.0, 2.0); self.after_sensitivity.setDecimals(2); self.after_sensitivity.setSingleStep(.05); self.after_sensitivity.setValue(1.0); self.after_sensitivity.setFixedWidth(82)
        self.after_sensitivity.setToolTip("Pressure gain: 0 = silent, 1 = normal, 2 = twice the curve level (clamped to MIDI 127).")
        self.after_shape = QComboBox(); self.after_shape.addItems(["Linear", "Smooth", "Step"])
        self.after_period = QDoubleSpinBox(); self._setup_beat_spin(self.after_period, 4.0)
        self.after_rate = QDoubleSpinBox(); self._setup_beat_spin(self.after_rate, .25, .0625, 16.0)
        self.after_timebase = QComboBox(); self.after_timebase.addItem("Loop", "loop"); self.after_timebase.addItem("Section", "section")
        self.after_points = QLineEdit(); self.after_points.setPlaceholderText("0:0, 1:1")
        self.after_points.setToolTip("Normalized pressure curve: 0 = no pressure, 1 = maximum pressure.")
        after.addWidget(self.after_enabled, 0, 0)
        after.addWidget(QLabel("Mode"), 0, 1); after.addWidget(self.after_mode, 0, 2)
        after.addWidget(QLabel("Shape"), 0, 3); after.addWidget(self.after_shape, 0, 4)
        after.addWidget(QLabel("Sensitivity"), 0, 5); after.addWidget(self.after_sensitivity, 0, 6)
        after.addWidget(QLabel("Period"), 1, 0); after.addWidget(self.after_period, 1, 1)
        after.addWidget(QLabel("Rate"), 1, 2); after.addWidget(self.after_rate, 1, 3)
        after.addWidget(self.after_timebase, 1, 4)
        after.addWidget(QLabel("Points"), 2, 0); after.addWidget(self.after_points, 2, 1, 1, 4)
        self.after_curve = MacroCurveEditor("#55c57e", self)
        self.after_curve.setAccessibleName("Aftertouch automation curve")
        self.after_curve.curveChanged.connect(self._after_curve_changed)
        after.addWidget(self.after_curve, 3, 0, 1, 5)
        root.addWidget(after_group)

        warning = QLabel("Channel-wide CC, Pitch Bend and Channel Aftertouch affect every instrument sharing this MIDI port/channel. Use separate channels for independent control. Polyphonic Aftertouch targets currently held notes. CC 6, 38, 100 and 101 are reserved for Pitch Bend range (RPN) setup when Pitch Bend is enabled.")
        warning.setWordWrap(True)
        warning.setObjectName("muted")
        root.addWidget(warning)
        self._bind_signals()
        self.set_config(self._config)
        bind_table(self.cc_table, ("enabled", "cc", "min", "max", "shape", "period", "rate", "timebase", "points"), "midi_expression")
        bind_help(self.cc_table, "cc_table", "midi_expression")
        bind_help(self.cc_curve, "points", "midi_expression")
        for prefix in ("bend", "after"):
            for suffix in ("enabled", "shape", "period", "rate", "timebase", "points", "curve"):
                key = f"{prefix}_points" if suffix in ("points", "curve") else suffix
                bind_help(getattr(self, f"{prefix}_{suffix}"), key, "midi_expression")
        bind_attributes(self, "midi_expression", ("bend_range", "after_mode", "after_sensitivity"))

    @staticmethod
    def _setup_beat_spin(spin, value, low=.0625, high=1024.0):
        spin.setRange(low, high)
        spin.setDecimals(4)
        spin.setSingleStep(.25)
        spin.setValue(value)
        spin.setFixedWidth(96)

    def _bind_signals(self):
        for widget in (self.bend_enabled, self.bend_range, self.bend_shape, self.bend_period,
                       self.bend_rate, self.bend_timebase, self.after_enabled, self.after_mode,
                       self.after_sensitivity, self.after_shape, self.after_period, self.after_rate, self.after_timebase):
            if isinstance(widget, QCheckBox):
                widget.toggled.connect(self._continuous_changed)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._continuous_changed)
            else:
                widget.valueChanged.connect(self._continuous_changed)
        for widget in (self.bend_points, self.after_points):
            widget.editingFinished.connect(self._continuous_changed)

    def _row(self, lane):
        values = [
            QTableWidgetItem(""), QTableWidgetItem(str(lane["controller"])),
            QTableWidgetItem(str(lane["min"])), QTableWidgetItem(str(lane["max"])),
            QTableWidgetItem(lane["shape"].title()), QTableWidgetItem(f'{lane["period_beats"]:g}'),
            QTableWidgetItem(f'{lane["rate_beats"]:g}'),
            QTableWidgetItem("Section" if lane.get("timebase") == "section" else "Loop"),
            QTableWidgetItem(_points_text(lane["points"])),
        ]
        values[0].setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
        values[0].setCheckState(Qt.Checked if lane["enabled"] else Qt.Unchecked)
        values[1].setData(Qt.UserRole, str(lane.get("id") or ""))
        for item in values[1:]:
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
        for item, key in zip(values, ("enabled", "cc", "min", "max", "shape", "period", "rate", "timebase", "points")):
            bind_help(item, key, "midi_expression")
        return values

    def _cc_selection_changed(self, row, _column, _previous_row, _previous_column):
        if self._loading or row < 0 or row >= self.cc_table.rowCount():
            return
        lanes = self._read_cc_rows()
        if row >= len(lanes):
            return
        lane = lanes[row]
        self.cc_curve.set_curve({"enabled": True, "shape": lane["shape"], "points": lane["points"]})
        self.cc_curve.setEnabled(True)

    def _cc_curve_changed(self, curve):
        row = self.cc_table.currentRow()
        if row < 0:
            return
        item = self.cc_table.item(row, 8)
        if item is not None:
            self._loading = True
            self.cc_table.blockSignals(True)
            item.setText(_points_text(curve["points"]))
            self.cc_table.blockSignals(False)
            self._loading = False
            self._emit_changed()

    def _bend_curve_changed(self, curve):
        self._loading = True
        self.bend_points.setText(_points_text(curve["points"]))
        self._loading = False
        self._emit_changed()

    def _after_curve_changed(self, curve):
        self._loading = True
        self.after_points.setText(_points_text(curve["points"]))
        self._loading = False
        self._emit_changed()

    def _read_cc_rows(self):
        lanes = []
        for row in range(self.cc_table.rowCount()):
            def cell(col, default):
                item = self.cc_table.item(row, col)
                return item.text() if item is not None else str(default)
            enabled_item = self.cc_table.item(row, 0)
            try:
                controller = int(cell(1, 74)); low = int(cell(2, 0)); high = int(cell(3, 127))
                period = float(cell(5, 4)); rate = float(cell(6, .25))
            except (ValueError, TypeError, OverflowError):
                continue
            controller_item = self.cc_table.item(row, 1)
            lane_id = controller_item.data(Qt.UserRole) if controller_item is not None else None
            lanes.append({
                "id": str(lane_id or f"cc-{controller}-{row + 1}"),
                "enabled": enabled_item is not None and enabled_item.checkState() == Qt.Checked,
                "controller": controller, "min": low, "max": high,
                "shape": cell(4, "Smooth").lower(), "period_beats": period,
                "rate_beats": rate, "timebase": "section" if cell(7, "Loop").lower().startswith("section") else "loop",
                "points": _parse_points(cell(8, ""), [[0, 0], [1, 1]]),
            })
        return lanes

    def _collect(self):
        bend = {
            "enabled": self.bend_enabled.isChecked(),
            "range_semitones": self.bend_range.value(),
            "shape": self.bend_shape.currentText().lower(),
            "period_beats": self.bend_period.value(), "rate_beats": self.bend_rate.value(),
            "timebase": self.bend_timebase.currentData(),
            "points": _parse_points(self.bend_points.text(), [[0, .5], [1, .5]]),
        }
        after = {
            "enabled": self.after_enabled.isChecked(), "mode": self.after_mode.currentData(),
            "sensitivity": self.after_sensitivity.value(),
            "shape": self.after_shape.currentText().lower(),
            "period_beats": self.after_period.value(), "rate_beats": self.after_rate.value(),
            "timebase": self.after_timebase.currentData(),
            "points": _parse_points(self.after_points.text(), [[0, 0], [1, 0]]),
        }
        return normalize_expression({"cc_lanes": self._read_cc_rows(), "pitch_bend": bend, "aftertouch": after})

    def _emit_changed(self):
        if self._loading:
            return
        self._config = self._collect()
        self.changed.emit(deepcopy(self._config))

    def _cc_item_changed(self, item):
        if item is not None and item.row() == self.cc_table.currentRow() and item.column() in (4, 8):
            lanes = self._read_cc_rows()
            if item.row() < len(lanes):
                lane = lanes[item.row()]
                self.cc_curve.set_curve({"enabled": True, "shape": lane["shape"], "points": lane["points"]})
        self._emit_changed()

    def _continuous_changed(self, *_):
        if self._loading:
            return
        if hasattr(self, "bend_curve"):
            bend_points = _parse_points(self.bend_points.text(), [[0, .5], [1, .5]])
            after_points = _parse_points(self.after_points.text(), [[0, 0], [1, 0]])
            self.bend_curve.set_curve({"enabled": True, "shape": self.bend_shape.currentText().lower(), "points": bend_points})
            self.after_curve.set_curve({"enabled": True, "shape": self.after_shape.currentText().lower(), "points": after_points})
            self.bend_curve.setEnabled(self.bend_enabled.isChecked())
            self.after_curve.setEnabled(self.after_enabled.isChecked())
            self.bend_period.setEnabled(self.bend_timebase.currentData() == "loop")
            self.after_period.setEnabled(self.after_timebase.currentData() == "loop")
        self._emit_changed()

    def _add_cc_lane(self):
        if self.cc_table.rowCount() >= MAX_CC_LANES:
            return
        self._loading = True
        row = self.cc_table.rowCount()
        self.cc_table.insertRow(row)
        used = {lane["controller"] for lane in self._read_cc_rows()}
        preferred = (74, 1, 7, 10, 11, 71, 91, 93, 73, 72, 75, 76, 77, 78, 79, 80)
        controller = next((number for number in preferred if number not in used), None)
        if controller is None:
            return
        lane = {"id": f"cc-{controller}-{row + 1}", "controller": controller,
                "min": 0, "max": 127, "enabled": True,
                "shape": "smooth", "period_beats": 4.0, "rate_beats": .25,
                "points": [[0, .15], [1, .85]]}
        for col, item in enumerate(self._row(lane)):
            self.cc_table.setItem(row, col, item)
        self._loading = False
        self.cc_table.setCurrentCell(row, 0)
        self._emit_changed()

    def _remove_cc_lane(self):
        row = self.cc_table.currentRow()
        if row < 0:
            return
        self._loading = True
        self.cc_table.removeRow(row)
        self._loading = False
        if self.cc_table.rowCount():
            self.cc_table.setCurrentCell(min(row, self.cc_table.rowCount() - 1), 0)
        else:
            self.cc_curve.setEnabled(False)
            self.cc_curve.set_curve({"enabled": True, "shape": "smooth", "points": [[0, 0], [1, 1]]})
        self._emit_changed()

    def set_config(self, config):
        self._loading = True
        self._config = normalize_expression(config)
        self.cc_table.blockSignals(True)
        self.cc_table.setRowCount(0)
        for lane in self._config["cc_lanes"]:
            row = self.cc_table.rowCount()
            self.cc_table.insertRow(row)
            for col, item in enumerate(self._row(lane)):
                self.cc_table.setItem(row, col, item)
        self.cc_table.blockSignals(False)
        if self._config["cc_lanes"]:
            self.cc_table.setCurrentCell(0, 0)
            first_lane = self._config["cc_lanes"][0]
            self.cc_curve.set_curve({"enabled": True, "shape": first_lane["shape"], "points": first_lane["points"]})
            self.cc_curve.setEnabled(True)
        else:
            self.cc_curve.set_curve({"enabled": True, "shape": "smooth", "points": [[0, 0], [1, 1]]})
            self.cc_curve.setEnabled(False)
        bend = self._config["pitch_bend"]
        self.bend_curve.set_curve({"enabled": True, "shape": bend["shape"], "points": bend["points"]})
        self.bend_curve.setEnabled(bend["enabled"])
        self.bend_enabled.setChecked(bend["enabled"]); self.bend_range.setValue(bend["range_semitones"])
        self.bend_shape.setCurrentText(bend["shape"].title()); self.bend_period.setValue(bend["period_beats"])
        self.bend_rate.setValue(bend["rate_beats"]); self.bend_timebase.setCurrentIndex(self.bend_timebase.findData(bend["timebase"]))
        self.bend_points.setText(_points_text(bend["points"]))
        self.bend_period.setEnabled(bend["timebase"] == "loop")
        after = self._config["aftertouch"]
        self.after_curve.set_curve({"enabled": True, "shape": after["shape"], "points": after["points"]})
        self.after_curve.setEnabled(after["enabled"])
        self.after_enabled.setChecked(after["enabled"]); self.after_mode.setCurrentIndex(self.after_mode.findData(after["mode"]))
        self.after_sensitivity.setValue(after["sensitivity"])
        self.after_shape.setCurrentText(after["shape"].title()); self.after_period.setValue(after["period_beats"])
        self.after_rate.setValue(after["rate_beats"]); self.after_timebase.setCurrentIndex(self.after_timebase.findData(after["timebase"]))
        self.after_points.setText(_points_text(after["points"]))
        self.after_period.setEnabled(after["timebase"] == "loop")
        self._loading = False

    def config(self):
        return deepcopy(self._config)

    def apply_theme(self, theme):
        for curve in (self.cc_curve, self.bend_curve, self.after_curve):
            curve.theme = theme
            curve.update()


class MidiSyncDialog(QDialog):
    """Global, project-persistent MIDI clock and transport-message settings."""
    def __init__(self, config=None, ports=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("MIDI Clock Sync")
        self.setMinimumWidth(420)
        self._config = normalize_midi_sync(config)
        layout = QVBoxLayout(self)
        info = QLabel("Auricle is the MIDI Clock master. Clock is sent at 24 pulses per quarter note to each selected output port, once per physical port.")
        info.setWordWrap(True); info.setObjectName("muted"); layout.addWidget(info)
        self.clock_enabled = QCheckBox("Send MIDI Clock (24 PPQN)")
        self.clock_enabled.setChecked(self._config["clock_out"])
        layout.addWidget(self.clock_enabled)
        self.transport_enabled = QCheckBox("Send Start / Stop / Continue")
        self.transport_enabled.setChecked(self._config["transport_messages"])
        layout.addWidget(self.transport_enabled)
        self.spp_enabled = QCheckBox("Send Song Position Pointer on seek")
        self.spp_enabled.setChecked(self._config["song_position_pointer"])
        layout.addWidget(self.spp_enabled)
        row = QHBoxLayout(); row.addWidget(QLabel("Clock output"))
        self.port_combo = QComboBox(); self.port_combo.addItem("All active block outputs", "*")
        for name in ports:
            self.port_combo.addItem(str(name), str(name))
        index = self.port_combo.findData(self._config["clock_port"])
        if index < 0 and self._config["clock_port"] != "*":
            self.port_combo.addItem(f'{self._config["clock_port"]} (unavailable)', self._config["clock_port"])
            index = self.port_combo.count() - 1
        self.port_combo.setCurrentIndex(max(0, index))
        row.addWidget(self.port_combo, 1); layout.addLayout(row)
        note = QLabel("Song Position Pointer uses MIDI sixteenth-note units. A selected dedicated output is opened even when no block is routed to it.")
        note.setWordWrap(True); note.setObjectName("muted"); layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        bind_attributes(self, "midi_sync", {"clock_enabled": "enabled", "transport_enabled": "transport", "spp_enabled": "spp", "port_combo": "port"})

    def config(self):
        return normalize_midi_sync({
            "clock_out": self.clock_enabled.isChecked(),
            "transport_messages": self.transport_enabled.isChecked(),
            "song_position_pointer": self.spp_enabled.isChecked(),
            "clock_port": self.port_combo.currentData() or "*",
        })


__all__ = ["MidiExpressionEditor", "MidiSyncDialog"]
