"""A musical view length must never depend on event density or pattern size."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest

from test_midi_learn_runtime_ui import app, editor


@pytest.fixture
def preferences(monkeypatch, tmp_path):
    import auricle_gui as gui
    settings = QSettings(str(tmp_path / "views.ini"), QSettings.IniFormat)
    monkeypatch.setattr(gui, "QSettings", lambda *_args: settings)
    return settings


@pytest.fixture
def view_editor(preferences, editor):
    return editor


@pytest.mark.parametrize("steps", [1, 16, 64, 4096])
def test_sparse_live_history_never_widens_window(app, monkeypatch, steps):
    import auricle_gui as gui
    monkeypatch.setattr(gui.time, "monotonic", lambda: 100.)
    roll = gui.PianoRollWidget()
    roll.set_view_steps(steps)
    span = steps * .125
    block = SimpleNamespace(name="Sparse", block_type="MELODY", midi_note=60, outputs={})
    history = [(100. - span - .01, 60, .8), (100. - span, 61, .8),
               (99.99, 62, .8), (100., 63, .8), (100.01, 64, .8)]
    roll.set_data(block, history, pattern_seconds=1000., seq_interval=.125, running=True)
    assert roll.view_seconds == span
    assert [event[1] for event in roll._history_events()] == [61, 62, 63]
    roll.resize(600, 190)
    assert not roll.grab().isNull()
    assert roll.view_seconds == span


def test_stop_and_freeze_keep_anchor_and_scale_across_widget_rebuild(app, monkeypatch):
    import auricle_gui as gui
    clock = [100.]
    monkeypatch.setattr(gui.time, "monotonic", lambda: clock[0])
    block = SimpleNamespace(name="Notes", block_type="MELODY", midi_note=60, outputs={})
    roll = gui.PianoRollWidget()
    roll.set_view_steps(16)
    history = [(90., 60, .8), (99., 61, .8)]
    roll.set_data(block, history, seq_interval=.125, running=True)
    roll.set_frozen(True)
    snapshot = roll.snapshot()
    clock[0] = 200.
    roll.set_data(block, [], seq_interval=.5, running=False)
    assert roll._display_time() == 100.
    assert roll.view_seconds == 2.
    assert roll._history_events() == [(99., 61, .8)]
    restored = gui.PianoRollWidget()
    restored.set_data(block, [], seq_interval=.5)
    restored.set_frozen(True, snapshot)
    restored.set_view_steps(128)
    assert restored.view_seconds == 16.
    assert restored._display_time() == 100.
    assert restored._history_events() == history
    restored.set_view_steps(4)
    assert restored._history_events() == []


def test_length_edits_preserve_pattern_and_widgets_and_survive_block_switch(view_editor, preferences):
    gui, win, _ = view_editor
    project = deepcopy(win.project)
    page, roll = win.inspector_page, win.piano_roll
    control = win.piano_roll_length
    control.editor.setText("64")
    control.editor.editingFinished.emit()
    assert win._piano_length_steps == roll.view_steps == 64
    assert win.project == project
    assert win.inspector_page is page and win.piano_roll is roll
    assert preferences.value("piano_roll/length_steps", type=int) == 64
    assert control.editor.toolTip() == control.toolTip()
    win.selected_block_id = win.project.blocks[1].id
    win._refresh_inspector()
    assert win.piano_roll_length.value() == win.piano_roll.view_steps == 64
    win.project.length = 256
    win.project.tempo = 60
    win._update_piano_roll()
    assert win.piano_roll.view_steps == 64 and win.piano_roll.view_seconds == 16.
    preferences.sync()
    disk = QSettings(preferences.fileName(), QSettings.IniFormat)
    assert disk.value("piano_roll/length_steps", type=int) == 64


def test_saved_length_is_loaded_when_new_window_starts(view_editor, preferences):
    gui, win, _ = view_editor
    preferences.setValue("piano_roll/length_steps", 96)
    other = gui.MainWindow()
    try:
        assert other.piano_roll_length.value() == other.piano_roll.view_steps == 96
    finally:
        other._dirty = False
        other.close()
        other.deleteLater()


def test_voice_selection_monitors_only_selected_voice_and_kit_combines_voices(view_editor):
    gui, win, _ = view_editor
    drum = win.project.blocks[0]
    first, second = drum.drum_voices[:2]
    win._midi_events = {first.id: [(100., first.midi_note, .8)],
                        second.id: [(100., second.midi_note, .7)]}
    win.selected_drum_voice_id = first.id
    win._refresh_inspector()
    win._update_piano_roll()
    assert win.piano_roll.block is first
    assert win.piano_roll.history == win._midi_events[first.id]
    win.selected_drum_voice_id = None
    win._refresh_inspector()
    assert win.piano_roll.block is drum
    assert len(win.piano_roll.history) == 2


@pytest.mark.parametrize("steps,clamped", [(0, 1), (9999, 4096)])
def test_length_limits_are_enforced_by_the_actual_control(view_editor, steps, clamped):
    _, win, _ = view_editor
    win.piano_roll_length.setValue(steps)
    assert win.piano_roll.view_steps == clamped
