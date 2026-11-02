"""Undo must restore the document without rebuilding unchanged widget trees."""
from copy import deepcopy

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from shiboken6 import isValid

from project_history import parameter_only_changes
from test_kit_preview_lifecycle import inspector


def select_voice(win, drum):
    win.selected_block_id = drum.id
    win.selected_drum_voice_id = drum.drum_voices[0].id
    win._refresh_all()
    win.show()
    QTest.qWait(80)


def bound_knob(gui, win, owner, key):
    return next(control for control in win.findChildren(gui.Knob)
                if getattr(control, '_auricle_parameter', None) == (owner, key))


@pytest.mark.parametrize('edit', ['voice', 'kit', 'macro'])
def test_parameter_undo_keeps_controls_and_their_model_bindings(inspector, monkeypatch, edit):
    gui, win, drum, melody, errors = inspector
    select_voice(win, drum)
    history = win.history_controller
    before = history.snapshot()
    page = win.inspector_scroll.widget()
    kit = win.drum_kit_layout.itemAt(0).widget()
    cards = dict(win.performance.cards)
    voice = drum.drum_voices[0]
    if edit == 'macro':
        control = win.global_macro_bar.sliders[0]
        control.setValue(81)
    else:
        owner, key = (voice.id, 'velocity_base') if edit == 'voice' else (drum.id, 'kit_density')
        control = bound_knob(gui, win, owner, key)
        control.setValue(.37)
    QTest.qWait(65)
    history.flush()
    after = history.snapshot()
    assert after != before

    def no_rebuild(*args, **kwargs):
        pytest.fail('A parameter Undo rebuilt the widget tree')
    monkeypatch.setattr(win, '_refresh_all', no_rebuild)
    monkeypatch.setattr(win, '_refresh_inspector', no_rebuild)
    for _ in range(3):
        history.move()
        QTest.qWait(15)
        assert history.snapshot() == before
        assert win.inspector_scroll.widget() is page
        assert win.drum_kit_layout.itemAt(0).widget() is kit
        assert win.performance.cards == cards
        assert win.get_entity(voice.id) is voice
        history.move(True)
        QTest.qWait(15)
        assert history.snapshot() == after
        assert isValid(control)
    # A pre-existing signal closure must still modify the current project.
    control.setValue(63 if edit == 'macro' else .63)
    QTest.qWait(50)
    history.flush()
    if edit == 'macro':
        assert win.project.macros[0]['value'] == .63
    else:
        assert win.get_entity(owner).parameters[key] == .63
    assert not errors


def test_parameter_undo_restores_absent_defaults_without_an_extra_edit(inspector):
    gui, win, drum, melody, errors = inspector
    select_voice(win, drum)
    drum.parameters.pop('kit_density', None)
    history = win.history_controller
    history.reset()
    knob = bound_knob(gui, win, drum.id, 'kit_density')
    knob.setValue(.23)
    QTest.qWait(60)
    history.move()
    assert 'kit_density' not in drum.parameters
    assert knob.value() == 1.0
    assert not win._dirty
    QTest.qWait(60)
    assert history.history.can_redo
    assert not history.pending
    history.move(True)
    assert drum.parameters['kit_density'] == .23
    assert knob.value() == .23
    assert not errors


def test_fast_undo_keeps_piano_freeze_control_in_sync(inspector):
    from PySide6.QtWidgets import QCheckBox
    gui, win, drum, melody, errors = inspector
    select_voice(win, drum)
    freeze = win.piano_roll.parentWidget().findChild(QCheckBox)
    freeze.setChecked(True)
    knob = bound_knob(gui, win, drum.id, 'kit_density')
    knob.setValue(.4)
    QTest.qWait(50)
    win.history_controller.move()
    assert isValid(freeze)
    assert not freeze.isChecked()
    assert win._piano_freeze is None
    assert not errors


def test_playing_parameter_undo_preserves_beat_and_does_not_scan_midi_ports(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    select_voice(win, drum)
    monkeypatch.setattr(win.transport, 'refresh_ports', lambda: None)
    win.transport.start()
    voice = drum.drum_voices[0]
    knob = bound_knob(gui, win, voice.id, 'velocity_base')
    knob.setValue(.29)
    QTest.qWait(40)
    win.engine.clock.position_beats = 12.25
    calls = []
    monkeypatch.setattr(win.transport, 'refresh_ports', lambda: calls.append('scan'))
    win.history_controller.move()
    assert win.transport.running
    assert win.engine.clock.position_beats == 12.25
    assert not calls
    assert isValid(knob)
    win.transport.stop()
    assert not errors


def test_routing_undo_refreshes_ports_during_playback(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    monkeypatch.setattr(win.transport, 'refresh_ports', lambda: None)
    win.transport.start()
    melody.midi_port = 'different device'
    win._mark_dirty()
    win.history_controller.flush()
    calls = []
    monkeypatch.setattr(win.transport, 'refresh_ports', lambda: calls.append('scan'))
    win.history_controller.move()
    assert win.get_block(melody.id).midi_port == ''
    assert calls == ['scan']
    win.transport.stop()
    assert not errors


def test_structural_undo_rebuilds_once_and_cancels_old_queued_refresh(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    select_voice(win, drum)
    selected = (win.selected_block_id, win.selected_drum_voice_id)
    before = win.history_controller.snapshot()
    calls = []
    refresh = win._refresh_inspector
    def counted(*args, **kwargs):
        calls.append((win.selected_block_id, win.selected_drum_voice_id))
        return refresh(*args, **kwargs)
    monkeypatch.setattr(win, '_refresh_inspector', counted)
    win.add_process()  # Intentionally do not let its queued refresh run first.
    win.history_controller.move()
    QTest.qWait(60)
    assert calls == [selected]
    assert (win.selected_block_id, win.selected_drum_voice_id) == selected
    assert win.history_controller.snapshot() == before
    win.history_controller.move(True)
    assert len(win._selected_inspector_entity().processes) == 1
    assert not errors


def test_undo_cancels_pending_mode_edit_before_it_overwrites_the_result(inspector):
    gui, win, drum, melody, errors = inspector
    select_voice(win, drum)
    voice = drum.drum_voices[0]
    before = win.history_controller.snapshot()
    bound_knob(gui, win, voice.id, 'velocity_base').setValue(.31)
    QTest.qWait(50)
    win._set_mode(voice, 'LIVE')  # The ComboBox callback defers this mutation.
    win.history_controller.move()
    QTest.qWait(60)
    assert win.history_controller.snapshot() == before
    assert win.history_controller.history.can_redo
    assert not errors


def test_fast_undo_stops_active_technique_without_restarting_it(inspector):
    gui, win, drum, melody, errors = inspector
    win.selected_block_id = melody.id
    win._refresh_all(); win.show(); QTest.qWait(50)
    card = win.performance.cards[melody.id]
    card.enable.click()
    assert win.engine.performance.active
    win.history_controller.flush()  # Starting a technique is a separate gesture.
    knob = bound_knob(gui, win, melody.id, 'velocity_base')
    knob.setValue(.31)
    QTest.qWait(40)
    win.history_controller.move()
    assert win.performance.cards[melody.id] is card
    assert not win.engine.performance.active
    assert not card.enable.isChecked()
    QTest.qWait(40)
    assert not win.engine.performance.active
    assert not errors


@pytest.mark.parametrize('kind', ['pattern', 'algorithm', 'chain', 'routing', 'macro_route'])
def test_parameter_fast_path_rejects_changes_requiring_new_controls(kind):
    before = {'blocks': [{'id': 1, 'algorithm': 'Pattern', 'parameters': {'pattern': '1,0'},
                          'processes': [], 'midi_port': ''}],
              'macros': [{'name': 'Energy', 'value': .5, 'routes': []}]}
    after = deepcopy(before)
    if kind == 'pattern': after['blocks'][0]['parameters']['pattern'] = '1,1'
    if kind == 'algorithm': after['blocks'][0]['algorithm'] = 'Random Walk'
    if kind == 'chain': after['blocks'][0]['processes'].append({'type': 'Delay'})
    if kind == 'routing': after['blocks'][0]['midi_port'] = 'another port'
    if kind == 'macro_route': after['macros'][0]['routes'].append({'block_id': 1})
    assert parameter_only_changes(before, after) is None
