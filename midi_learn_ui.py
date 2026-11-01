"""MIDI input selection and learned-mapping manager dialog."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QComboBox, QTableWidget, QTableWidgetItem,
                               QAbstractItemView, QApplication, QPlainTextEdit)
from help_tooltips import bind_help, bind_attributes

from midi_input_diagnostics import BUILD, format_diagnostics


class MidiLearnDialog(QDialog):
    def __init__(self, host, parent=None):
        super().__init__(parent or host)
        self.host = host
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh_mappings)
        self.setWindowTitle("MIDI Learn & Control Mapping")
        self.setMinimumSize(650, 390)
        root = QVBoxLayout(self)
        info = QLabel(
            "Connect a MIDI input, then right-click a numeric parameter in Block Inspector and choose MIDI Learn. "
            "You can keep this window open while choosing the parameter. "
            "Move a hardware control to assign it. Pickup waits until the control crosses the authored value."
        )
        info.setWordWrap(True)
        info.setObjectName("muted")
        root.addWidget(info)

        row = QHBoxLayout()
        row.addWidget(QLabel("MIDI Input"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(300)
        row.addWidget(self.port_combo, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_ports)
        row.addWidget(self.refresh_button)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._connect)
        row.addWidget(self.connect_button)
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self._disconnect)
        row.addWidget(self.disconnect_button)
        self.port_combo.currentIndexChanged.connect(self._refresh_status)
        root.addLayout(row)

        self.status = QLabel()
        self.status.setObjectName("muted")
        root.addWidget(self.status)
        self.input_activity = QLabel("Waiting for MIDI input…")
        self.input_activity.setObjectName("muted")
        root.addWidget(self.input_activity)
        self.diagnostic_summary = QLabel(BUILD + "\nInput reader not connected")
        self.diagnostic_summary.setWordWrap(True)
        self.diagnostic_summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.diagnostic_summary)
        diagnostic_actions = QHBoxLayout()
        self.diagnostic_button = QPushButton("Diagnostics")
        self.diagnostic_button.setCheckable(True)
        self.copy_diagnostic_button = QPushButton("Copy diagnostics")
        self.copy_diagnostic_button.clicked.connect(self._copy_diagnostics)
        diagnostic_actions.addWidget(self.diagnostic_button)
        diagnostic_actions.addWidget(self.copy_diagnostic_button)
        diagnostic_actions.addStretch(1)
        root.addLayout(diagnostic_actions)
        self.diagnostic_output = QPlainTextEdit()
        self.diagnostic_output.setReadOnly(True)
        self.diagnostic_output.setMaximumHeight(180)
        self.diagnostic_output.hide()
        root.addWidget(self.diagnostic_output)
        self.diagnostic_button.toggled.connect(self.diagnostic_output.setVisible)
        self.diagnostic_button.toggled.connect(self._update_diagnostics)
        self._diagnostic_timer = QTimer(self)
        self._diagnostic_timer.setInterval(500)
        self._diagnostic_timer.timeout.connect(self._update_diagnostics)
        self._diagnostic_timer.start()
        signal = getattr(self.host, "_midi_input_event_signal", None)
        if signal is not None:
            signal.connect(self._on_input_event)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Input", "Message", "Channel", "Target", "Pickup", "Enabled"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._enabled_changed)
        root.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.remove_button = QPushButton("Remove selected")
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button = QPushButton("Clear all")
        self.clear_button.clicked.connect(self._clear_all)
        self.cancel_learn_button = QPushButton("Cancel Learn")
        self.cancel_learn_button.clicked.connect(self.host._cancel_midi_learn)
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.clear_button)
        buttons.addWidget(self.cancel_learn_button)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)
        self.refresh_ports()
        self.refresh_mappings()
        bind_attributes(self, "midi_learn", {"port_combo": "input", "remove_button": "remove", "clear_button": "remove", "cancel_learn_button": "cancel"})

    def _update_diagnostics(self):
        snapshot = self.host.midi_learn_diagnostic_snapshot()
        state, runtime = snapshot["midi_input"], snapshot["runtime"]
        if state["error"]:
            stage = "Error: " + state["error"]
        elif not runtime["reader_alive"]:
            stage = "Input reader not connected"
        elif not state["raw_messages"]:
            stage = "Port open; no incoming messages"
        elif not state["decoded_messages"]:
            stage = "Messages received; last type is not a Learn control"
        elif not state["gui_messages"]:
            stage = "Decoded messages waiting for GUI delivery"
        else:
            stage = {"armed": "Waiting for a control to learn",
                     "learned": "Mapping created; move the control again",
                     "pickup": "Waiting for Pickup; sweep the control or uncheck Pickup",
                     "queued": "Value queued; waiting for model update",
                     "applied": "Authored parameter updated",
                     "unmatched": "Input received; no enabled mapping matches this port/channel/control",
                     "unchanged": "Mapped value already equals the authored value"}.get(state["stage"], state["stage"])
            if state["stage"] == "queued" and not runtime["pending_commands"]:
                stage = "Queue drained; requested value differs from the current authored value (see diagnostics)"
        self.diagnostic_summary.setText(
            f"{BUILD} · Received {state['raw_messages']} · Supported {state['decoded_messages']} "
            f"· GUI {state['gui_messages']}\n{stage}")
        if self.diagnostic_output.isVisible():
            self.diagnostic_output.setPlainText(format_diagnostics(state, runtime))

    def _copy_diagnostics(self):
        QApplication.clipboard().setText(self.host.midi_learn_diagnostic_report())
        self.copy_diagnostic_button.setText("Copied")
        QTimer.singleShot(1500, self, lambda: self.copy_diagnostic_button.setText("Copy diagnostics"))

    def refresh_ports(self):
        current = (self.port_combo.currentData() or self.host.project.midi_input_port
                   or self.host._midi_input_name or "")
        names, error = self.host.get_midi_input_names()
        self.port_combo.clear()
        self.port_combo.addItem("Select MIDI input…", "")
        for name in names:
            self.port_combo.addItem(name, name)
        if current and self.port_combo.findData(current) < 0:
            self.port_combo.addItem(f"{current} (unavailable)", current)
        index = self.port_combo.findData(current)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)
        if error:
            self.status.setText(f"MIDI input backend: {error}")
        else:
            self._refresh_status()

    def _on_input_event(self, event):
        if not isinstance(event, dict):
            return
        kind = str(event.get("type", "MIDI")).upper()
        number = event.get("number")
        channel = event.get("channel")
        value = float(event.get("value", 0.0))
        details = kind + (f" {number}" if number is not None else "")
        details += f" · CH {int(channel) + 1 if channel is not None else 'OMNI'} · {value:.3f}"
        if event.get("port"):
            details = f"{event['port']} · " + details
        self.input_activity.setText("Last input: " + details)

    def _refresh_status(self):
        active = self.host._midi_input_name
        armed = getattr(self.host, "_midi_learn_target", None)
        if active:
            text = f"Connected: {active}"
        else:
            text = "No MIDI input connected"
            error = getattr(self.host, "_midi_input_error", "")
            if error:
                text += " · " + error
        if armed:
            text += " · LEARN ARMED — move one control on your MIDI device"
        self.status.setText(text)
        self.connect_button.setEnabled(bool(self.port_combo.currentData()))
        self.disconnect_button.setEnabled(bool(active))
        self.cancel_learn_button.setEnabled(bool(armed))

    def _connect(self):
        name = self.port_combo.currentData()
        if name and self.host.connect_midi_input(name):
            self.host.project.midi_input_port = str(name)
            self.host._mark_dirty()
        self._refresh_status()

    def _disconnect(self):
        self.host.disconnect_midi_input()
        self.host.project.midi_input_port = ""
        self.host._mark_dirty()
        self._refresh_status()

    def refresh_mappings(self):
        mappings = list(self.host.project.midi_mappings or [])
        previous = self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(mappings))
            for row, mapping in enumerate(mappings):
                source = mapping.get("source", {})
                target = mapping.get("target", {})
                kind = source.get("type", "cc").upper()
                number = source.get("number")
                message = kind + (f" {number}" if number is not None else "")
                channel = "Omni" if source.get("channel") is None else str(int(source["channel"]) + 1)
                if target.get("kind") == "global_macro":
                    target_text = f"Global Macro {int(target.get('macro_index', 0)) + 1}"
                else:
                    block = self.host.get_entity(target.get("block_id"))
                    name = block.name if block is not None else f"Block {target.get('block_id')}"
                    target_text = f"{name} · {target.get('parameter')}"
                values = [source.get("port", "Any input") or "Any input", message, channel, target_text]
                for col, value in enumerate(values):
                    self.table.setItem(row, col, QTableWidgetItem(str(value)))
                self.table.item(row, 0).setData(Qt.UserRole, mapping.get("id"))
                for col, key, text in ((4, "pickup", "Pickup"), (5, "enabled", "Enabled")):
                    item = QTableWidgetItem(text)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                    item.setCheckState(Qt.Checked if mapping.get(key, True) else Qt.Unchecked)
                    self.table.setItem(row, col, item)
                    bind_help(item, key, "midi_learn")
        finally:
            self.table.blockSignals(previous)
        self.table.resizeColumnsToContents()
        self._refresh_status()

    def queue_refresh(self):
        # Do not replace a native table item inside its itemChanged event.
        self._refresh_timer.start(0)

    def _enabled_changed(self, item):
        if item.column() not in (4, 5):
            return
        first = self.table.item(item.row(), 0)
        if first is not None:
            setter = (self.host.set_midi_mapping_pickup if item.column() == 4
                      else self.host.set_midi_mapping_enabled)
            setter(first.data(Qt.UserRole), item.checkState() == Qt.Checked)

    def _remove_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is not None:
            self.host.remove_midi_mapping(item.data(Qt.UserRole))
            self.refresh_mappings()

    def _clear_all(self):
        self.host.clear_midi_mappings()
        self.refresh_mappings()


__all__ = ["MidiLearnDialog"]
