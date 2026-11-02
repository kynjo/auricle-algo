"""Committed MIDI edits must update Qt controls without a polling frame."""
import threading

import pytest
from PySide6.QtCore import QThread
from PySide6.QtTest import QTest

from midi_learn import normalize_mapping
from test_midi_learn_runtime_ui import app, editor, wait_for, target, cc
from test_midi_learn_native_path import live_editor, native_adapter, NativeInput


def select_knob(gui, win, owner, key):
    drum = win.project.blocks[0]
    if owner == "voice":
        block = drum.drum_voices[0]
        win.selected_block_id, win.selected_drum_voice_id = drum.id, block.id
    else:
        block = drum if owner == "kit" else win.project.blocks[1]
        win.selected_block_id, win.selected_drum_voice_id = block.id, None
    win._refresh_inspector()
    knob = next(k for k in win.inspector_page.findChildren(gui.Knob)
                if getattr(k, "_auricle_parameter", None) == (block.id, key))
    return block, knob


@pytest.mark.parametrize("owner,key", [
    ("kit", "kit_humanize"), ("kit", "kit_complexity"),
    ("bass", "walk_step"), ("bass", "fill_density"), ("voice", "pulses"),
])
def test_native_midi_updates_needle_and_readout_without_polling_or_rebuild(
        native_adapter, app, owner, key):
    gui, win = native_adapter
    block, knob = select_knob(gui, win, owner, key)
    page = win.inspector_page
    scroll = win.inspector_scroll.verticalScrollBar()
    position = scroll.value()
    changes, threads = [], []
    knob.changed.connect(changes.append)
    original = knob.set_runtime_value

    def feedback(manual, effective):
        threads.append(QThread.currentThread())
        original(manual, effective)

    knob.set_runtime_value = feedback
    assert not win.performance_timer.isActive()
    assert win.connect_midi_input("Controller")
    native = NativeInput.instances[-1]
    win._arm_midi_learn(target(block, key, min=knob.lo, max=knob.hi,
                               integer=knob.integer, initial=knob.value()))
    native.send_native_bytes([0xB0, 74, 0])
    wait_for(app, lambda: len(win.project.midi_mappings) == 1)
    # History's save path must not flush commands for the test.
    win.history_controller.commit_timer.stop()
    for raw in (127, 32, 0):
        value = knob.lo + (knob.hi - knob.lo) * raw / 127
        expected = round(value) if knob.integer else value
        native.send_native_bytes([0xB0, 74, raw])
        wait_for(app, lambda: block.parameters.get(key) == pytest.approx(expected))
        wait_for(app, lambda: knob.value() == pytest.approx(expected)
                 and knob.displayValue() == pytest.approx(expected))
        assert knob.value_label.text() == knob._formatted()
    assert not changes
    assert threads and all(thread == win.thread() for thread in threads)
    assert win.inspector_page is page
    assert scroll.value() == position
    assert not win.transport.gui_command_errors
    assert not win.transport_worker.error_count


def test_committed_feedback_preserves_effective_composition_value(live_editor, app):
    gui, win, ports = live_editor
    block, knob = select_knob(gui, win, "bass", "fill_density")
    win.project.composition["enabled"] = True
    section = win.project.composition["sections"][0]
    section["macros"]["density"] = .3
    section["blocks"][str(block.id)] = {"density": .5}
    win.project.midi_mappings = [normalize_mapping({
        "source": {"type": "cc", "number": 74}, "target": target(block),
        "pickup": False,
    })]
    changes = []
    knob.changed.connect(changes.append)
    win.connect_midi_input("Controller")
    ports[-1].feed(cc(127))
    wait_for(app, lambda: block.parameters["fill_density"] == 1.)
    wait_for(app, lambda: knob.value() == 1. and knob.displayValue() == pytest.approx(.35))
    assert not changes
    assert win.project.composition["enabled"]


def test_midi_feedback_preserves_automatic_parameter_layer(live_editor, app):
    gui, win, ports = live_editor
    block, knob = select_knob(gui, win, "bass", "gate")
    win.engine.parameter_influence.write(block, "gate", .25, "Technique:test")
    win.project.midi_mappings = [normalize_mapping({
        "source": {"type": "cc", "number": 74}, "target": target(block, "gate"),
        "pickup": False,
    })]
    win.connect_midi_input("Controller")
    ports[-1].feed(cc(127))
    wait_for(app, lambda: win.engine.parameter_influence.entries[(block.id, "gate")]["base"] == (True, 1.))
    wait_for(app, lambda: knob.value() == 1. and knob.displayValue() == .25)
    assert block.parameters["gate"] == .25


def test_rapid_midi_return_to_original_value_keeps_last_position(editor, app):
    gui, win, _ = editor
    block, knob = select_knob(gui, win, "kit", "kit_humanize")
    block.parameters["kit_humanize"] = 0.
    win.project.midi_mappings = [normalize_mapping({
        "source": {"type": "cc", "number": 74},
        "target": target(block, "kit_humanize", initial=0.), "pickup": False,
    })]
    page = win.inspector_page
    changes, applied = [], []
    knob.changed.connect(changes.append)
    win._transport_command_applied_signal.connect(applied.append)
    # Receive a burst before the next transport tick, ending at the starting value.
    for raw in (127, 96, 64, 32, 0):
        win._handle_midi_input("Controller", cc(raw))
    assert len(win.transport.gui_command_queue) == 1
    win.transport_worker.start()
    try:
        wait_for(app, lambda: any(p.get("parameter_entity") is block for p in applied))
        assert block.parameters["kit_humanize"] == 0.
        assert knob.value() == knob.displayValue() == 0.
        assert not changes
        assert win.inspector_page is page
    finally:
        win.transport_worker.stop()


def test_stale_commit_cannot_move_same_id_in_replacement_project(editor, app):
    from auricle_core import Block, Project
    gui, win, _ = editor
    block, _ = select_knob(gui, win, "bass", "gate")
    delivered = []
    win._transport_command_applied_signal.connect(delivered.append)
    win._set_param(block, "gate", 1.)
    worker = threading.Thread(target=win.transport.flush_gui_commands)
    worker.start()
    worker.join(2)
    assert not worker.is_alive()
    # Keep the old notification queued while replacing its entity with the same ID.
    replacement = Block(block.id, "Replacement", "BASS", parameters={"gate": .2})
    win._install_project(Project(blocks=[replacement]), None, "Replacement")
    knob = next(k for k in win.inspector_page.findChildren(gui.Knob)
                if getattr(k, "_auricle_parameter", None) == (replacement.id, "gate"))
    app.processEvents()
    assert delivered
    # Replaying the old notification after replacement must be harmless too.
    win._handle_transport_command_applied(delivered[0])
    assert knob.value() == knob.displayValue() == .2


def test_runtime_feedback_still_respects_active_mouse_drag(live_editor, app):
    from PySide6.QtCore import Qt, QPoint
    gui, win, ports = live_editor
    block, knob = select_knob(gui, win, "kit", "kit_humanize")
    win.show()
    app.processEvents()
    win.project.midi_mappings = [normalize_mapping({
        "source": {"type": "cc", "number": 74}, "target": target(block, "kit_humanize"),
        "pickup": False,
    })]
    before = knob.value()
    applied = []
    win._transport_command_applied_signal.connect(applied.append)
    win.connect_midi_input("Controller")
    QTest.mousePress(knob, Qt.LeftButton, pos=QPoint(25, 25))
    try:
        ports[-1].feed(cc(127))
        wait_for(app, lambda: any(p.get("parameter_entity") is block for p in applied))
        assert block.parameters["kit_humanize"] == 1.
        assert knob.value() == before
    finally:
        QTest.mouseRelease(knob, Qt.LeftButton, pos=QPoint(25, 25))
    # Once the mouse is released the normal feedback heartbeat catches up.
    win._update_parameter_sources(force=True)
    assert knob.value() == 1.
