"""Exercise the real Mido RtMidi adapter and an unflushed live transport."""
import json
import threading

import mido
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication

from midi_input_diagnostics import MidiInputDiagnostics
from test_midi_learn_runtime_ui import app, editor, wait_for, target, cc


@pytest.fixture
def live_editor(editor):
    gui, win, ports = editor
    win.transport_worker.start()
    try:
        yield gui, win, ports
    finally:
        win.transport_worker.stop()


class NativeInput:
    """Only the OS/device boundary is replaced; Mido's adapter stays real."""
    instances = []
    api = None

    def __init__(self, *args, **kwargs):
        self.callback = None
        self.closed = False
        self.instances.append(self)

    def get_current_api(self):
        return self.api

    def get_ports(self):
        return ["Controller"]

    def open_port(self, index):
        assert index == 0

    def ignore_types(self, *args):
        self.ignored = args

    def cancel_callback(self):
        self.callback = None

    def set_callback(self, callback):
        self.callback = callback

    def close_port(self):
        self.closed = True

    def delete(self):
        self.closed = True

    def send_native_bytes(self, message):
        callback = self.callback
        assert callback is not None
        thread = threading.Thread(target=callback, args=((list(message), .0), None))
        thread.start()
        thread.join(timeout=1)
        assert not thread.is_alive()


@pytest.fixture
def native_adapter(live_editor, monkeypatch):
    import mido.backends.rtmidi as backend
    gui, win, ports = live_editor
    NativeInput.instances = []
    NativeInput.api = next(iter(backend._api_to_name))
    monkeypatch.setattr(backend.rtmidi, "MidiIn", NativeInput)
    adapter = mido.Backend("mido.backends.rtmidi")
    monkeypatch.setattr(gui.mido, "open_input", adapter.open_input)
    return gui, win


def test_real_adapter_byte_callback_reaches_live_model_without_manual_flush(native_adapter, app):
    _, win = native_adapter
    block = win.project.blocks[1]
    block.parameters["fill_density"] = .5
    assert win.connect_midi_input("Controller")
    assert type(win._midi_input_port).__module__ == "mido.backends.rtmidi"
    native = NativeInput.instances[-1]
    win._arm_midi_learn(target(block))
    native.send_native_bytes([0xB0, 74, 0])
    wait_for(app, lambda: len(win.project.midi_mappings) == 1)
    # Do not let a pending history snapshot flush on behalf of the worker.
    win.history_controller.commit_timer.stop()
    native.send_native_bytes([0xB0, 74, 127])
    wait_for(app, lambda: block.parameters["fill_density"] == 1.)
    snapshot = win.midi_learn_diagnostic_snapshot()
    assert snapshot["runtime"]["reader_alive"]
    assert snapshot["runtime"]["transport_worker_alive"]
    assert snapshot["midi_input"]["raw_messages"] == 2
    assert snapshot["midi_input"]["decoded_messages"] == 2
    assert snapshot["midi_input"]["gui_messages"] == 2
    assert snapshot["midi_input"]["stage"] == "applied"


def test_real_adapter_reports_unsupported_messages_instead_of_false_silence(native_adapter, app):
    _, win = native_adapter
    win.connect_midi_input("Controller")
    native = NativeInput.instances[-1]
    native.send_native_bytes([0xF8])  # Clock reaches Mido, but is not a Learn control.
    wait_for(app, lambda: win._midi_diagnostics.snapshot()["raw_messages"] == 1)
    snapshot = win.midi_learn_diagnostic_snapshot()["midi_input"]
    assert snapshot["last_raw"]["type"] == "clock"
    assert snapshot["decoded_messages"] == snapshot["gui_messages"] == 0


def test_sysex_payload_is_not_in_diagnostic_report(native_adapter, app):
    _, win = native_adapter
    win.connect_midi_input("Controller")
    NativeInput.instances[-1].send_native_bytes([0xF0, 0x7D, 17, 23, 99, 0xF7])
    wait_for(app, lambda: win._midi_diagnostics.snapshot()["raw_messages"] == 1)
    raw = json.loads(win.midi_learn_diagnostic_report())["midi_input"]["last_raw"]
    assert raw == {"type": "sysex", "data_length": 4}


def test_queue_stage_identifies_worker_not_applying_values(editor):
    _, win, _ = editor
    block = win.project.blocks[1]
    block.parameters["fill_density"] = .5
    win.connect_midi_input("Controller")
    win._arm_midi_learn(target(block))
    win._handle_midi_input("Controller", cc(0))
    win.history_controller.commit_timer.stop()
    win._handle_midi_input("Controller", cc(127))
    snapshot = win.midi_learn_diagnostic_snapshot()
    assert snapshot["midi_input"]["stage"] == "queued"
    assert not snapshot["runtime"]["transport_worker_alive"]
    assert snapshot["runtime"]["pending_commands"] > 0
    assert block.parameters["fill_density"] == .5


def test_pickup_and_unmatched_input_are_distinguishable(editor):
    _, win, _ = editor
    block = win.project.blocks[1]
    block.parameters["fill_density"] = .8
    win.connect_midi_input("Controller")
    win._arm_midi_learn(target(block))
    win._handle_midi_input("Controller", cc(0))
    win._handle_midi_input("Controller", cc(10))
    assert win.midi_learn_diagnostic_snapshot()["midi_input"]["stage"] == "pickup"
    win._handle_midi_input("Controller", cc(10, number=71))
    assert win.midi_learn_diagnostic_snapshot()["midi_input"]["stage"] == "unmatched"


def test_manager_remains_open_and_nonmodal_while_selecting_parameter(editor, app):
    gui, win, ports = editor
    win._open_midi_learn_dialog()
    dialog = win._midi_learn_dialog
    assert dialog.isVisible()
    assert not dialog.isModal()
    assert dialog.windowModality() == Qt.NonModal
    assert QApplication.activeModalWidget() is not dialog
    # Reopening focuses the same manager instead of adding a second receiver.
    win._open_midi_learn_dialog()
    assert win._midi_learn_dialog is dialog
    dialog.port_combo.setCurrentIndex(1)
    dialog.connect_button.click()
    win._arm_midi_learn(target(win.project.blocks[1]))
    ports[-1].feed(cc(0))
    wait_for(app, lambda: len(win.project.midi_mappings) == 1)
    assert dialog.isVisible()
    dialog.accept()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert win._midi_learn_dialog is None
    assert not win.findChildren(gui.MidiLearnDialog)


def test_report_identifies_running_build_and_copies_to_clipboard(editor):
    gui, win, _ = editor
    dialog = gui.MidiLearnDialog(win)
    dialog._copy_diagnostics()
    report = json.loads(QApplication.clipboard().text())
    assert report["midi_input"]["build"] == "midi-learn-diagnostics-2"
    assert report["runtime"]["gui_module"].endswith("auricle_gui.py")
    assert len(report["runtime"]["gui_sha256"]) == 64
    assert "environment" not in report["runtime"]


def test_diagnostic_observation_is_bounded_and_thread_safe():
    diagnostics = MidiInputDiagnostics("Controller")
    threads = [threading.Thread(target=lambda: [diagnostics.observe(cc(i % 128)) for i in range(200)])
               for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    snapshot = diagnostics.snapshot()
    assert snapshot["raw_messages"] == 800
    assert isinstance(snapshot["last_raw"], dict)
    assert len(json.dumps(snapshot)) < 1500
