"""User-state history, real write provenance, and emitted harmonic MIDI."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from auricle_core import Block, Project, MusicEngine, Process, Mutator, Relation, save_project, load_project, midi_note_for
from auricle_persistence import project_from_dict
from project_history import ProjectHistory, RecoveryStore, document_state
from harmonic_plan import HarmonicRuntime, QUALITIES, preset
from performance_presets import presets_for
from test_coordinated_kit import setup_transport
from test_kit_preview_lifecycle import inspector


def test_history_coalesces_one_gesture_branches_and_tracks_saved_point():
    h = ProjectHistory({'value': 0}, limit=4)
    for n in range(1, 20): h.commit({'value': n}, group='drag1')
    assert h.index == 1
    h.mark_clean()
    h.commit({'value': 30}, group='drag2')
    assert h.dirty
    assert h.undo() == {'value': 19}
    assert not h.dirty
    assert h.undo() == {'value': 0}
    assert h.redo() == {'value': 19}
    h.commit({'value': 50})
    assert not h.can_redo
    for n in range(10): h.commit({'value': n})
    assert len(h.states) == 4


def test_checkpoint_atomic_failure_keeps_previous_and_bad_files_are_ignored(tmp_path, monkeypatch):
    store = RecoveryStore(tmp_path)
    state = document_state(Project(blocks=[Block(1, 'Lead', 'MELODY')]))
    store.write(state, '/saved/project.json')
    before = store.path.read_bytes()
    monkeypatch.setattr('project_history.os.replace', lambda *_: (_ for _ in ()).throw(OSError('disk failure')))
    with pytest.raises(OSError): store.write({**state, 'tempo': 140})
    assert store.path.read_bytes() == before
    assert not list(tmp_path.glob('*.tmp'))
    (tmp_path/'session-invalid.json').write_text('{broken')
    reader = RecoveryStore(tmp_path)
    assert len(reader.candidates()) == 1
    _, data = reader.candidates()[0]
    restored = project_from_dict(data['project'])
    assert restored.blocks[0].name == 'Lead'
    assert data['source_path'] == '/saved/project.json'
    store.clear()
    assert not reader.candidates()


def test_real_macro_modulation_technique_writes_leave_manual_snapshot_intact():
    block = Block(1, 'Lead', 'MELODY', 'Random Walk', 'LIVE', parameters={'fill_density': .8}, mutators=[])
    project = Project(blocks=[block], macros=[{'name': 'My density', 'value': .25, 'routes': [
        {'block_id': 1, 'parameter': 'fill_density', 'min': 0, 'max': 1}]}])
    engine = MusicEngine(project)
    engine.generate()
    baseline = document_state(project, engine)
    trace = engine.parameter_influence.describe(block, 'fill_density')
    assert trace['base'] == .8 and trace['current'] == .25
    assert trace['writes'][0]['source'] == 'Macro: My density'
    process = Process('Parameter Modulation', 'pitch', 1, {'destination_block': 1,
        'destination_parameter': 'fill_density', 'source_min': 0, 'source_max': 1, 'min': 0, 'max': 1})
    engine.queue_parameter_modulation(block, .6, process)
    assert block.parameters['fill_density'] == .25
    engine.apply_pending_parameter_modulations()
    assert block.parameters['fill_density'] == .6
    trace = engine.parameter_influence.describe(block, 'fill_density')
    assert trace['writes'][-1]['source'] == 'Parameter Modulation'
    assert trace['writes'][-1]['before'] == .25
    technique = presets_for(block.block_type, block.algorithm)[0]
    assert engine.performance.start(block, technique.id, beats=16)
    engine.performance.tick(True, beat_delta=4)
    assert document_state(project, engine) == baseline
    assert any(row['source'].startswith('Technique:') for item in engine.parameter_influence.entries.values()
               for row in item['rows'].values())
    engine.parameter_influence.manual(block, 'fill_density', .9)
    assert document_state(project, engine)['blocks'][0]['parameters']['fill_density'] == .9


def test_snapshot_has_no_outputs_or_phrase_playhead_but_keeps_relations_and_chains():
    block = Block(1, 'Lead', 'MELODY', mutators=[Mutator('Transpose', .2)], processes=[Process('Add', amount=.3)])
    project = Project(blocks=[block], relations=[Relation(1, 'pitch', 1, 'velocity', 'Follow', id=8)])
    engine = MusicEngine(project); engine.generate()
    data = document_state(project, engine)
    engine.clock.position_beats = 23
    engine.director.phrase.position_beats = 17
    engine.director.sync_project(project)
    block.outputs['pitch'] = [99]
    assert document_state(project, engine) == data
    restored = project_from_dict(data)
    assert restored.blocks[0].mutators[0].amount == .2
    assert restored.blocks[0].processes[0].amount == .3
    assert restored.relations[0].id == 8


@pytest.mark.parametrize('meter,bar_beats', [('4/4', 4), ('3/4', 3), ('7/8', 3.5), ('6/8', 3)])
def test_plan_boundaries_variable_durations_loop_and_hold(meter, bar_beats):
    plan = preset(); plan['meter'] = meter; plan['chords'][0]['bars'] = 2
    runtime = HarmonicRuntime(Project(harmonic_plan=plan))
    assert runtime.at(2*bar_beats - .01)['name'] == 'Am'
    assert runtime.at(2*bar_beats)['name'] == 'F'
    assert runtime.at(5*bar_beats)['name'] == 'Am'
    assert runtime.at(5*bar_beats)['cycle'] == 1
    plan['loop'] = False
    assert runtime.at(100)['name'] == 'G'
    assert runtime.at(100)['remaining'] is None


@pytest.mark.parametrize('quality', QUALITIES)
@pytest.mark.parametrize('role', ['CHORD', 'PAD'])
def test_voicing_stays_on_explicit_chord_even_outside_global_scale(quality, role):
    block = Block(1, role, role, parameters={'harmony_inversion': 1, 'harmony_spread': 14})
    project = Project(root_note=62, scale='Major', blocks=[block], harmonic_plan={
        'enabled': True, 'chords': [{'root': 8, 'quality': quality, 'bars': 1}]})
    engine = MusicEngine(project)
    event = engine.harmonize_event(block, {'pitch': 0, 'velocity': .8}, 0)
    notes = [midi_note_for(project, block, p) for p in event['pitches']]
    assert {n % 12 for n in notes} == {(8+i) % 12 for i in QUALITIES[quality][1]}
    assert all(0 <= n <= 127 for n in notes)
    assert len(set(notes)) == len(notes)


@pytest.mark.parametrize('role', ['BASS', 'MELODY'])
def test_anchor_and_cadence_follow_plan_and_zero_strength_is_free(role):
    block = Block(1, role, role, parameters={'harmonic_strength': .7})
    project = Project(blocks=[block], harmonic_plan=preset())
    engine = MusicEngine(project)
    for beat in (0, 3.5, 4, 7.5, 8, 11.5, 12, 15.5):
        event = engine.harmonize_event(block, {'pitch': 1, 'velocity': .8}, beat)
        chord = engine.harmonic_runtime.at(beat)
        note = midi_note_for(project, block, event['pitch'])
        assert note % 12 in chord['pitch_classes']
        if role == 'BASS': assert note % 12 == chord['root']
    block.parameters['harmonic_strength'] = 0
    assert engine.harmonize_event(block, {'pitch': 1}, 0)['pitch'] == 1
    block.parameters['harmonic_follow'] = False
    assert engine.harmonize_event(block, {'pitch': 1}, 0) == {'pitch': 1}


@pytest.mark.parametrize('mode', ['SEQ', 'LIVE'])
@pytest.mark.parametrize('role', ['CHORD', 'PAD', 'BASS', 'MELODY'])
def test_emitted_midi_changes_chord_in_both_modes_and_uses_context(monkeypatch, mode, role):
    block = Block(1, role, role, 'Pattern', mode, midi_port='capture', mutators=[], parameters={
        'pattern': '1', 'live_min_beats': .25, 'live_max_beats': .25,
        'fill_density': 1, 'event_probability': 1, 'harmonic_strength': 1})
    project = Project(blocks=[block], harmonic_plan=preset())
    engine = MusicEngine(project)
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    for i in range(65): tick(i*.125)
    onsets = [(t, msg) for t, msg in sent if msg.type == 'note_on']
    assert len(onsets) >= 10
    covered = set()
    for t, message in onsets:
        chord = engine.harmonic_runtime.at(t*2)
        covered.add(chord['name'])
        assert message.note % 12 in chord['pitch_classes']
    assert covered == {'Am', 'F', 'C', 'G'}
    assert engine.musical_context.values['harmonic_plan']['name'] == 'Am'
    transport.stop()


def test_plan_roundtrip_disabled_and_drums_are_unaffected(tmp_path):
    drum = Block(1, 'Drum', 'DRUM')
    project = Project(blocks=[drum], harmonic_plan=preset())
    path = tmp_path/'project.json'; save_project(project, str(path))
    loaded = load_project(str(path))
    assert loaded.harmonic_plan == project.harmonic_plan
    engine = MusicEngine(loaded)
    event = {'pitch': 4, 'velocity': .8}
    assert engine.harmonize_event(loaded.blocks[0], event, 4) == event
    loaded.harmonic_plan['enabled'] = False
    assert engine.harmonize_event(Block(2, 'Chord', 'CHORD'), event, 4) == event


def test_gui_undo_redo_complete_document_and_savepoint(inspector, tmp_path):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = inspector
    history = win.history_controller
    before = deepcopy(history.snapshot())
    win._set_param(melody, 'velocity_base', .32)
    QTest.qWait(30)
    assert history.history.can_undo
    history.move()
    assert history.snapshot() == before
    history.move(True)
    assert win.get_block(melody.id).parameters['velocity_base'] == .32
    win.selected_block_id = melody.id
    win.add_process(); QTest.qWait(40)
    assert len(win.get_block(melody.id).processes) == 1
    history.move()
    assert not win.get_block(melody.id).processes
    history.move(True)
    win.add_mutator(); QTest.qWait(40)
    assert len(win.get_block(melody.id).mutators) == 1
    history.move()
    assert not win.get_block(melody.id).mutators
    win.add_relation(); QTest.qWait(40)
    assert win.project.relations
    history.move()
    assert not win.project.relations
    assert win._write_project(str(tmp_path/'saved.json'))
    assert not win._dirty
    win._set_param(win.get_block(melody.id), 'velocity_base', .8); QTest.qWait(30)
    assert win._dirty
    history.move()
    assert not win._dirty
    assert not errors


def test_gui_one_drag_is_one_undo_and_value_click_opens_card(inspector):
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtTest import QTest
    from parameter_influence_ui import InfluenceDialog
    gui, win, drum, melody, errors = inspector
    win.selected_block_id = melody.id; win._refresh_inspector(); win.show(); QTest.qWait(40)
    knob = next(w for w in win.findChildren(gui.Knob) if getattr(w, '_auricle_parameter', None) == (melody.id, 'velocity_base'))
    history = win.history_controller
    history.flush(); old_index = history.history.index
    before = melody.parameters.get('velocity_base', .72)
    QTest.mousePress(knob, Qt.LeftButton, pos=QPoint(25, 25))
    for value in (.25, .35, .45): knob.setValue(value); QTest.qWait(8)
    QTest.mouseRelease(knob, Qt.LeftButton, pos=QPoint(25, 25)); QTest.qWait(40)
    assert history.history.index == old_index+1
    history.move()
    assert win.get_block(melody.id).parameters.get('velocity_base', .72) == before
    knob = next(w for w in win.findChildren(gui.Knob) if getattr(w, '_auricle_parameter', None) == (melody.id, 'velocity_base'))
    QTest.mouseClick(knob, Qt.LeftButton, pos=QPoint(25, 65)); QTest.qWait(20)
    cards = win.findChildren(InfluenceDialog)
    assert cards and cards[-1].isVisible()
    assert 'Effective:' in cards[-1].values.text()
    cards[-1].close()
    assert not errors


def test_gui_plan_edit_undo_and_playing_undo_preserves_position(inspector, monkeypatch):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = inspector
    panel = win.performance.harmonic_panel
    panel.change('enabled', True); QTest.qWait(30)
    panel.open_editor()
    editor = panel.editor
    editor.edit(0, 'bars', 2); QTest.qWait(30)
    assert win.project.harmonic_plan['chords'][0]['bars'] == 2
    win.history_controller.move()
    assert win.project.harmonic_plan['chords'][0]['bars'] == 1
    editor.add(); QTest.qWait(30)
    assert len(win.project.harmonic_plan['chords']) == 5
    monkeypatch.setattr(win.transport, 'refresh_ports', lambda: None)
    win.transport.start()
    win.engine.clock.position_beats = 12.25
    win.history_controller.move()
    assert win.transport.running
    assert win.engine.clock.position_beats == 12.25
    assert len(win.project.harmonic_plan['chords']) == 4
    win.transport.stop(); editor.close()
    assert not errors


def test_delete_undo_restores_routes_and_entire_drum_kit(inspector):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = inspector
    drum.drum_voices[0].name = 'Custom kick'
    drum.drum_voices[0].midi_channel_override = True
    drum.drum_voices[0].midi_channel = 4
    win.project.relations = [Relation(drum.id, 'rhythm', melody.id, 'rhythm', 'Follow', id=42)]
    win.project.macros[0]['routes'] = [{'block_id': drum.id, 'parameter': 'kit_density', 'min': .1, 'max': 1}]
    win.engine.generate(); win._mark_dirty(); QTest.qWait(30)
    before = deepcopy(win.history_controller.snapshot())
    win.delete_block_by_id(drum.id); QTest.qWait(40)
    assert win.get_block(drum.id) is None
    assert not win.project.relations
    win.history_controller.move()
    assert win.history_controller.snapshot() == before
    assert win.get_block(drum.id).drum_voices[0].name == 'Custom kick'
    assert win.get_block(drum.id).drum_voices[0].midi_channel == 4
    assert not errors


def test_recovery_ui_restores_unsaved_copy_without_overwriting_saved_file(inspector, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = inspector
    saved = tmp_path/'saved.json'
    win._write_project(str(saved)); original = saved.read_bytes()
    controller = win.history_controller
    controller.recovery = RecoveryStore(tmp_path/'recovery')
    win._set_param(melody, 'velocity_base', .24)
    QTest.qWait(30); controller.checkpoint()
    old = controller.recovery.path
    payload = json.loads(old.read_text()); payload['pid'] = 0
    old.write_text(json.dumps(payload))
    controller.recovery = RecoveryStore(tmp_path/'recovery')
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args, **kw: (args[3][0], True))
    monkeypatch.setattr(win, '_confirm_discard_changes', lambda: True)
    controller.offer_recovery()
    assert win.get_block(melody.id).parameters['velocity_base'] == .24
    assert win._dirty
    assert saved.read_bytes() == original
    assert not old.exists() and controller.recovery.path.exists()
    win._write_project(str(saved))
    assert not controller.recovery.path.exists()
    assert not errors


def test_auto_values_do_not_undo_with_a_later_manual_edit(inspector):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = inspector
    controller = win.history_controller
    initial = deepcopy(controller.snapshot())
    win.engine.set_parameter(melody, 'fill_density', .15, source='Parameter Modulation')
    win._rename_block(melody, 'Edited name'); QTest.qWait(30)
    saved = controller.snapshot()
    assert saved['blocks'][1]['parameters'].get('fill_density') == initial['blocks'][1]['parameters'].get('fill_density')
    controller.move()
    assert controller.snapshot() == initial
    assert not errors


def test_compact_header_controls_do_not_overlap(inspector):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = inspector
    win.resize(820, 700); win.show(); QTest.qWait(60)
    widgets = [win.brand_logo, win.play, win.stop, win.tempo, win.length, win.key, win.scale, win.theme_combo]
    for left, right in zip(widgets, widgets[1:]):
        assert left.geometry().right() < right.geometry().left()
    assert win.theme_combo.geometry().right() < win.width()
    assert not errors


def test_undo_ends_active_technique_without_card_restarting_it(inspector):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = inspector
    technique = presets_for(melody.block_type, melody.algorithm)[0]
    win.project.performance[str(melody.id)] = {'preset_id': technique.id, 'enabled': True,
                                              'amount': .6, 'beats': 8, 'shape': 'in'}
    win._mark_dirty(); QTest.qWait(20)
    win.engine.performance.start(melody, technique.id, beats=8)
    win._rename_block(melody, 'While technique is running'); QTest.qWait(20)
    win.history_controller.move()
    assert not win.engine.performance.active
    assert not win.project.performance[str(melody.id)]['enabled']
    assert win.project.performance[str(melody.id)]['amount'] == .6
    assert not win.performance.cards[melody.id].enable.isChecked()
    assert not errors


def test_saved_project_keeps_loaded_phrase_choice_and_targets_without_playhead(inspector, tmp_path):
    from performance_presets import phrases
    gui, win, drum, melody, errors = inspector
    phrase = phrases()[-1]
    project = Project(blocks=[deepcopy(drum), deepcopy(melody)], phrase_state={
        'phrase_id': phrase.id, 'intensity': .61, 'block_ids': [melody.id],
        'position_beats': 5, 'memory': {'total_beats': 24}})
    win._install_project(project, None, 'Phrase settings')
    assert win._write_project(str(tmp_path/'phrase.json'))
    saved = load_project(str(tmp_path/'phrase.json'))
    assert saved.performance['_phrase'] == {'phrase_id': phrase.id, 'amount': .61,
                                             'duration_beats': 24, 'block_ids': [melody.id]}
    assert not saved.phrase_state
    assert not errors
