"""MIDI Learn through real Qt controls, queued signals and a Mido input port."""
import os
import queue
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import mido
import pytest
from mido.ports import BaseInput
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtCore import QPoint
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication

from midi_learn import MidiLearnRuntime, normalize_mapping
from midi_learn_ui import MidiLearnDialog


class QueueInput(BaseInput):
    def _open(self, **kwargs):
        self.incoming = queue.Queue()
        self.read_error = False
        self.closed_by = None

    def _close(self):
        self.closed_by = threading.current_thread().name

    def _receive(self, block=True):
        if self.read_error:
            raise OSError("controller disconnected")
        try:
            return self.incoming.get_nowait()
        except queue.Empty:
            return None

    def feed(self, message):
        self.incoming.put(message)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(app, monkeypatch, tmp_path):
    import auricle_gui as gui
    monkeypatch.setenv("AURICLE_RECOVERY_DIR", str(tmp_path / "recovery"))
    monkeypatch.setattr(gui, "get_midi_input_names", lambda: (["Controller"], None))
    monkeypatch.setattr(gui, "get_midi_output_names", lambda: ([], None))
    ports = []

    def open_input(name, **kwargs):
        port = QueueInput(name)
        ports.append(port)
        return port

    monkeypatch.setattr(gui.mido, "open_input", open_input)
    win = gui.MainWindow()
    win.performance_timer.stop()
    win.transport_worker.stop()
    yield gui, win, ports
    win.disconnect_midi_input()
    win.history_controller.close()
    win.transport.flush_gui_commands(notify=False)
    win._dirty = False
    win.hide()
    win.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def wait_for(app, predicate, seconds=2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.002)
    assert predicate(), "Timed out waiting for queued MIDI input"


def target(block, key="fill_density", **kwargs):
    return {"kind": "block_parameter", "block_id": block.id, "parameter": key,
            "min": 0., "max": 1., "initial": .5, **kwargs}


def cc(value, number=74):
    return mido.Message("control_change", channel=0, control=number, value=value)


def choose_learn_action(gui, monkeypatch):
    class LearnMenu(gui.QMenu):
        def exec(self, *args):
            return self.actions()[0]
    monkeypatch.setattr(gui, "QMenu", LearnMenu)


def test_selecting_input_enables_connect_and_starts_reader(editor, app):
    _, win, ports = editor
    dialog = MidiLearnDialog(win)
    assert not dialog.connect_button.isEnabled()
    dialog.port_combo.setCurrentIndex(dialog.port_combo.findData("Controller"))
    assert dialog.connect_button.isEnabled()
    dialog.connect_button.click()
    assert win._midi_input_name == "Controller"
    ports[-1].feed(cc(64))
    wait_for(app, lambda: win._midi_input_event_count == 1)
    assert "CC 74" in dialog.input_activity.text()


def test_persistent_kit_does_not_accumulate_learn_connections(editor):
    gui, win, _ = editor
    knob = win.drum_kit_host.findChild(gui.Knob)
    for _ in range(3):
        win._refresh_inspector()
    assert knob.receivers("2midi_learn_requested(PyObject)") == 1
    assert knob.receivers("2midi_clear_requested(PyObject)") == 1


def test_reader_signal_learns_applies_and_persists_cc(editor, app, tmp_path):
    from auricle_persistence import load_project
    _, win, ports = editor
    block = win.project.blocks[1]
    block.parameters["fill_density"] = .5
    assert win.connect_midi_input("Controller")
    win._arm_midi_learn(target(block))
    ports[-1].feed(cc(0))
    wait_for(app, lambda: len(win.project.midi_mappings) == 1)
    ports[-1].feed(cc(127))
    wait_for(app, lambda: win._midi_input_event_count == 2)
    win.transport.flush_gui_commands()
    assert block.parameters["fill_density"] == 1.
    path = tmp_path / "learned.json"
    assert win._write_project(str(path))
    restored = load_project(str(path))
    assert restored.midi_input_port == "Controller"
    assert restored.midi_mappings[0]["target"]["block_id"] == block.id
    assert restored.midi_mappings[0]["source"]["number"] == 74


def test_note_learn_does_not_wait_for_unreachable_velocity_pickup(editor):
    _, win, _ = editor
    block = win.project.blocks[1]
    block.parameters["fill_density"] = .5
    win.connect_midi_input("Controller")
    win._arm_midi_learn(target(block))
    note = mido.Message("note_on", note=60, velocity=127)
    win._handle_midi_input("Controller", note)
    assert not win.project.midi_mappings[0]["pickup"]
    win._handle_midi_input("Controller", note)
    win.transport.flush_gui_commands()
    assert block.parameters["fill_density"] == 1.


def test_pickup_can_be_changed_in_mapping_manager(editor):
    _, win, _ = editor
    win.project.midi_mappings = [normalize_mapping({
        "target": target(win.project.blocks[1]), "source": {"type": "cc", "number": 74},
    })]
    dialog = MidiLearnDialog(win)
    pickup = dialog.table.item(0, 4)
    assert pickup.flags() & Qt.ItemIsUserCheckable
    pickup.setCheckState(Qt.Unchecked)
    assert not win.project.midi_mappings[0]["pickup"]


@pytest.mark.parametrize("curve,center", [("exp", .25), ("smooth", .15625)])
def test_pickup_compares_shaped_input_to_authored_value(curve, center):
    mapping = normalize_mapping({"id": "curved", "source": {"type": "cc", "number": 74},
                                 "target": {"kind": "global_macro", "macro_index": 0},
                                 "curve": curve, "pickup": True})
    runtime = MidiLearnRuntime()
    event = {"type": "cc", "channel": 0, "number": 74, "value": 0.}
    runtime.prime("curved", 0.)
    event["value"] = .3 if curve == "exp" else .15
    assert runtime.value_for(mapping, "Controller", event, center) is None
    event["value"] = .55 if curve == "exp" else .3
    assert runtime.value_for(mapping, "Controller", event, center) is not None


def test_reader_error_clears_connected_state_and_allows_reconnect(editor, app):
    _, win, ports = editor
    assert win.connect_midi_input("Controller")
    ports[-1].read_error = True
    wait_for(app, lambda: not win._midi_input_name)
    assert "disconnected" in win.statusBar().currentMessage()
    assert win.connect_midi_input("Controller")
    assert len(ports) == 2
    ports[-1].feed(cc(64))
    wait_for(app, lambda: win._midi_input_event_count == 1)


def test_stale_queued_input_from_reopened_port_cannot_learn(editor, app):
    _, win, ports = editor
    assert win.connect_midi_input("Controller")
    ports[-1].feed(cc(0, number=7))
    deadline = time.monotonic() + 2
    while not ports[-1].incoming.empty() and time.monotonic() < deadline:
        time.sleep(.002)  # Deliberately leave the Qt delivery queued.
    assert ports[-1].incoming.empty()
    win.disconnect_midi_input()
    assert win.connect_midi_input("Controller")
    win._arm_midi_learn(target(win.project.blocks[1]))
    app.processEvents()
    assert win.project.midi_mappings == []
    ports[-1].feed(cc(0, number=74))
    wait_for(app, lambda: len(win.project.midi_mappings) == 1)
    assert win.project.midi_mappings[0]["source"]["number"] == 74


def test_pickup_uses_manual_base_instead_of_automatic_effective_value(editor):
    _, win, _ = editor
    block = win.project.blocks[1]
    block.parameters["fill_density"] = .2
    win.engine.parameter_influence.write(block, "fill_density", .8, "Macro:test")
    win.project.midi_mappings = [normalize_mapping({
        "id": "base", "target": target(block), "source": {"type": "cc", "number": 74},
    })]
    win._midi_learn_runtime.prime("base", 0.)
    win._handle_midi_input("Controller", cc(40))
    win.transport.flush_gui_commands()
    assert win.engine.parameter_influence.base_value(block, "fill_density") == pytest.approx(40 / 127)


def test_reenabling_mapping_requires_new_pickup(editor):
    _, win, _ = editor
    block = win.project.blocks[1]
    block.parameters["fill_density"] = .5
    mapping = normalize_mapping({"id": "toggle", "target": target(block),
                                 "source": {"type": "cc", "number": 74}})
    win.project.midi_mappings = [mapping]
    win._midi_learn_runtime.prime("toggle", 0.)
    win._handle_midi_input("Controller", cc(127))
    win.transport.flush_gui_commands()
    win.set_midi_mapping_enabled("toggle", False)
    win.set_midi_mapping_enabled("toggle", True)
    win._handle_midi_input("Controller", cc(0))
    win.transport.flush_gui_commands()
    assert block.parameters["fill_density"] == 1.


def test_deleted_learn_target_does_not_create_dead_mapping(editor):
    _, win, _ = editor
    win.connect_midi_input("Controller")
    block = win.project.blocks[1]
    win._arm_midi_learn(target(block))
    win.project.blocks.remove(block)
    win._handle_midi_input("Controller", cc(64))
    assert not win.project.midi_mappings
    assert win._midi_learn_target is None


def test_knob_context_menu_reaches_learn_with_history_filter_installed(editor, monkeypatch):
    gui, win, _ = editor
    win.connect_midi_input("Controller")
    knob = win.drum_kit_host.findChild(gui.Knob)
    choose_learn_action(gui, monkeypatch)
    QApplication.sendEvent(knob, QContextMenuEvent(
        QContextMenuEvent.Mouse, QPoint(10, 10), knob.mapToGlobal(QPoint(10, 10))))
    assert win._midi_learn_target["parameter"] == knob._auricle_parameter[1]
    assert win._midi_learn_target["block_id"] == knob._auricle_parameter[0]


def test_global_macro_context_menu_learns_and_updates_slider(editor, app, monkeypatch):
    gui, win, _ = editor
    win.connect_midi_input("Controller")
    choose_learn_action(gui, monkeypatch)
    win.global_macro_bar.sliders[0].customContextMenuRequested.emit(QPoint(10, 10))
    win._handle_midi_input("Controller", cc(0))
    win._handle_midi_input("Controller", cc(127))
    win.transport.flush_gui_commands()
    app.processEvents()
    assert win.project.macros[0]["value"] == 1.
    assert win.global_macro_bar.sliders[0].value() == 100


def test_integer_drum_voice_target_is_applied_through_reader(editor, app):
    _, win, ports = editor
    voice = win.project.blocks[0].drum_voices[0]
    win.connect_midi_input("Controller")
    win._arm_midi_learn(target(voice, "pulses", min=1, max=16, integer=True))
    ports[-1].feed(cc(0))
    wait_for(app, lambda: len(win.project.midi_mappings) == 1)
    ports[-1].feed(cc(127))
    wait_for(app, lambda: win._midi_input_event_count == 2)
    win.transport.flush_gui_commands()
    assert voice.parameters["pulses"] == 16
    assert type(voice.parameters["pulses"]) is int


def test_disconnect_closes_port_on_reader_thread(editor):
    _, win, ports = editor
    win.connect_midi_input("Controller")
    win.disconnect_midi_input()
    assert ports[-1].closed
    assert ports[-1].closed_by == "Auricle-MIDI-IN"


def test_dead_reader_is_not_reported_as_already_connected(editor):
    _, win, ports = editor
    win.connect_midi_input("Controller")
    ports[-1].read_error = True
    win._midi_input_thread.join(timeout=2)
    # Reconnect before the queued failure reaches Qt.
    assert not win._midi_input_thread.is_alive()
    assert win.connect_midi_input("Controller")
    assert len(ports) == 2


def test_project_replacement_discards_previous_input_session(editor, app):
    from auricle_model import Project, Block
    _, win, ports = editor
    win.connect_midi_input("Controller")
    ports[-1].feed(cc(0, number=7))
    deadline = time.monotonic() + 2
    while not ports[-1].incoming.empty() and time.monotonic() < deadline:
        time.sleep(.002)
    assert ports[-1].incoming.empty()
    project = Project(blocks=[Block(1, "New bass", "BASS")], midi_input_port="Controller")
    win._install_project(project, None, "Replacement")
    win._arm_midi_learn(target(project.blocks[0]))
    app.processEvents()
    assert not project.midi_mappings
    assert len(ports) == 2


def test_cancel_learn_keeps_existing_mappings(editor):
    _, win, _ = editor
    win.connect_midi_input("Controller")
    win._arm_midi_learn(target(win.project.blocks[1]))
    win._cancel_midi_learn()
    win._handle_midi_input("Controller", cc(64))
    assert not win.project.midi_mappings
    assert win.midi_learn_button.text() == "MIDI IN ✓"


def test_dialog_refresh_is_deferred_during_checkbox_edit(editor, app):
    _, win, _ = editor
    win.project.midi_mappings = [normalize_mapping({"id": "table", "target": target(win.project.blocks[1])})]
    dialog = MidiLearnDialog(win)
    win._midi_learn_dialog = dialog
    item = dialog.table.item(0, 4)
    item.setCheckState(Qt.Unchecked)
    assert dialog.table.item(0, 4) is item
    app.processEvents()
    assert dialog.table.item(0, 4).checkState() == Qt.Unchecked
    win._midi_learn_dialog = None


def test_high_rate_cc_burst_keeps_latest_authored_value(editor, app):
    _, win, ports = editor
    block = win.project.blocks[1]
    win.connect_midi_input("Controller")
    win.project.midi_mappings = [normalize_mapping({
        "source": {"type": "cc", "number": 74}, "target": target(block), "pickup": False,
    })]
    for value in range(128):
        ports[-1].feed(cc(value))
    wait_for(app, lambda: win._midi_input_event_count == 128)
    win.transport.flush_gui_commands()
    assert block.parameters["fill_density"] == 1.


def test_closed_input_port_is_reported(editor, app):
    _, win, ports = editor
    win.connect_midi_input("Controller")
    ports[-1].close()
    wait_for(app, lambda: not win._midi_input_name)
    assert "closed" in win.statusBar().currentMessage()


def test_reader_checks_stop_inside_pending_batch():
    from midi_input_reader import read_input_loop
    stop = threading.Event()

    class BusyPort:
        def iter_pending(self):
            yield cc(1)
            assert stop.is_set()
            yield cc(2)

    events = []

    def receive(event):
        events.append(event)
        stop.set()

    read_input_loop(BusyPort(), receive, stop)
    assert len(events) == 1
