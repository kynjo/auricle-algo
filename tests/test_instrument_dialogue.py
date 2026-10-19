"""Behavior, emitted MIDI and inline editing for instrument conversations."""
from copy import deepcopy

import pytest

from auricle_core import Block, Project, Relation, MusicEngine, ensure_drum_voices, save_project, load_project
from auricle_relations import duplicate_relation
from instrument_dialogue import DialogueRuntime, settings, phase_at, METERS
from harmonic_plan import preset
from project_history import document_state
from test_coordinated_kit import setup_transport
from test_kit_preview_lifecycle import inspector


def make_pair(mode_a='SEQ', mode_b='LIVE', role_a='MELODY', role_b='BASS', **config):
    parameters = {'pattern': '1,3,5,3', 'fill_density': 1, 'event_probability': 1,
                  'live_min_beats': .25, 'live_max_beats': .25, 'groove_follow': 0,
                  'harmony_anchor': 0, 'harmonic_strength': 0, 'gate': 1.5, 'live_gate': 1.5}
    a = Block(1, 'Question', role_a, 'Pattern', mode_a, 1, 'capture', 60,
              deepcopy(parameters), mutators=[])
    b = Block(2, 'Answer', role_b, 'Pattern', mode_b, 2, 'capture', 60,
              deepcopy(parameters), mutators=[])
    for block in (a, b):
        if block.block_type == 'DRUM':
            block.parameters['kit_coordinated'] = True
            block.drum_voices = ensure_drum_voices(block)[:2]
            for voice in block.drum_voices:
                voice.parameters.update(pattern='1', fill_density=1, event_probability=1)
    relation = Relation(1, 'pitch', 2, 'pitch', 'Dialogue', 1, id=1, parameters=config)
    project = Project(blocks=[a, b], relations=[relation])
    return project, a, b, relation, MusicEngine(project)


@pytest.mark.parametrize('meter', METERS)
def test_musical_phase_with_unequal_turns_gaps_and_loop(meter):
    relation = Relation(1, 'pitch', 2, 'pitch', 'Dialogue', parameters={
        'meter': meter, 'call_bars': 2, 'response_bars': 1, 'gap_beats': .5})
    config = settings(relation)
    n, d = map(int, meter.split('/')); bar = n*4/d
    assert phase_at(config, 0)['phase'] == 'Call'
    assert phase_at(config, 2*bar)['phase'] == 'Pause'
    assert phase_at(config, 2*bar+.5)['phase'] == 'Response'
    assert phase_at(config, 3*bar+.5)['phase'] == 'Pause'
    assert phase_at(config, 3*bar+1)['cycle'] == 1
    assert phase_at(config, 3*bar+1)['phase'] == 'Call'


@pytest.mark.parametrize('mode_a,mode_b', [('SEQ', 'SEQ'), ('LIVE', 'LIVE'), ('SEQ', 'LIVE'), ('LIVE', 'SEQ')])
@pytest.mark.parametrize('role_a,role_b', [('MELODY', 'BASS'), ('CHORD', 'PAD'), ('DRUM', 'MELODY')])
def test_midi_turns_gaps_modes_and_drum_owner(monkeypatch, mode_a, mode_b, role_a, role_b):
    project, a, b, relation, engine = make_pair(mode_a, mode_b, role_a, role_b, gap_beats=.5)
    # Reordering the project cannot change which instrument owns each turn.
    project.blocks.reverse()
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    accepted = []
    transport.app.record_generated_event = lambda block, event: accepted.append((now[0]-100, block, event))
    for i in range(145):
        tick(i*.0625)
    onsets = [(t, message) for t, message in sent if message.type == 'note_on']
    assert {m.channel for _, m in onsets} == {0, 1}
    for t, message in onsets:
        phase = phase_at(settings(relation), t*2)
        assert phase['phase'] == ('Call' if message.channel == 0 else 'Response')
    for t, block, event in accepted:
        phase = phase_at(settings(relation), t*2)
        owner = getattr(block, 'parent_id', block.id)
        assert phase['phase'] == ('Call' if owner == a.id else 'Response')
    # Long gates must release at turn boundaries, including under a Drum owner.
    active = {}
    for t, message in sent:
        key = (message.channel, message.note)
        if message.type == 'note_on':
            active[key] = t
        elif message.type == 'note_off' and key in active:
            start = active.pop(key)
            phase = phase_at(settings(relation), start*2)
            assert t <= start+phase['remaining']/2+.063
    transport.stop()


@pytest.mark.parametrize('reply,expected', [('Echo', [0, 4, 7]), ('Contrast', [0, -4, -7]), ('Own phrase', [0, 0, 0])])
def test_response_contour_and_accents_use_this_cycles_call(reply, expected):
    project, a, b, relation, engine = make_pair(reply=reply, follow=1)
    runtime = engine.dialogue_runtime
    for beat, pitch, velocity in ((0, 12, .5), (1, 16, .8), (2, 19, .65)):
        runtime.apply(a, {'pitch': pitch, 'velocity': velocity}, beat)
    answers = [runtime.apply(b, {'pitch': 0, 'velocity': .7}, beat) for beat in (4, 5, 6)]
    assert [event['pitch'] for event in answers] == expected
    assert all(.01 <= event['velocity'] <= 1 for event in answers)
    if reply == 'Echo':
        assert answers[1]['velocity'] > answers[0]['velocity']
    elif reply == 'Contrast':
        assert answers[1]['velocity'] < answers[0]['velocity']
    # No call in the next cycle: fall back to the answer's own phrase.
    assert runtime.apply(b, {'pitch': 3, 'velocity': .7}, 12)['pitch'] == 3
    assert not next(iter(runtime.memory.values()))['samples']


def test_response_follows_current_harmony_and_its_own_register():
    project, a, b, relation, engine = make_pair(reply='Contrast', follow=1)
    project.harmonic_plan = preset()
    b.parameters.update(harmonic_strength=1, role_center=-24, role_width=24)
    for i, pitch in enumerate((0, 4, 7, 11)):
        engine.dialogue_event(a, {'pitch': pitch, 'velocity': .8}, i)
    for i in range(4):
        event = engine.dialogue_event(b, {'pitch': -24, 'velocity': .8}, 4+i)
        note = 60+event['pitch']
        assert 24 <= note <= 48
        assert note % 12 in engine.harmonic_runtime.at(4+i)['pitch_classes']


def test_depth_probability_disabled_and_zero_follow_are_real_bypasses():
    project, a, b, relation, engine = make_pair(follow=0)
    runtime = engine.dialogue_runtime
    event = {'pitch': 3, 'velocity': .8}
    assert runtime.apply(a, event, 4) is None
    relation.amount = .5
    assert runtime.apply(a, event, 4)['velocity'] == .4
    relation.amount = 0
    assert runtime.apply(a, event, 4) == event
    relation.amount = 1; relation.probability = 0
    assert runtime.apply(a, event, 4) == event
    relation.probability = 1; relation.enabled = False
    assert runtime.apply(a, event, 4) == event
    relation.enabled = True
    runtime.apply(a, {'pitch': 12, 'velocity': .4}, 0)
    runtime.apply(a, {'pitch': 19, 'velocity': .9}, 2)
    result = runtime.apply(b, event, 6)
    assert result['pitch'] == event['pitch'] and result['velocity'] == event['velocity']
    relation.probability = .5
    choices = [runtime.status(relation, n*8)['active'] for n in range(20)]
    assert any(choices) and not all(choices)
    assert choices == [runtime.status(relation, n*8+7.9)['active'] for n in range(20)]


def test_missing_self_conflicting_routes_and_reactivation_do_not_silence_blocks():
    project, a, b, relation, engine = make_pair()
    runtime = engine.dialogue_runtime
    c = Block(3, 'Third', 'MELODY'); project.blocks.append(c)
    conflict = Relation(2, 'pitch', 3, 'pitch', 'Dialogue', 1, id=2)
    project.relations.append(conflict)
    assert 'already used' in runtime.status(conflict, 0)['reason']
    assert runtime.can_play(c, 0)
    relation.enabled = False
    assert runtime.status(conflict, 0)['active']
    conflict.destination_block = 99
    assert 'Missing' in runtime.status(conflict, 0)['reason']
    conflict.destination_block = 2
    assert 'different' in runtime.status(conflict, 0)['reason']
    assert runtime.can_play(b, 4)


def test_loop_memory_is_bounded_and_reset_and_config_edits_clear_it():
    project, a, b, relation, engine = make_pair()
    runtime = engine.dialogue_runtime
    for cycle in range(80):
        for step in range(16):
            runtime.apply(a, {'pitch': step, 'velocity': .8}, cycle*8+step*.25)
        runtime.apply(b, {'pitch': 0, 'velocity': .8}, cycle*8+4)
    memory = next(iter(runtime.memory.values()))
    assert len(memory['samples']) == 16 and len(runtime.memory) == 1
    relation.parameters['reply'] = 'Contrast'
    runtime.status(relation, 0)
    assert not runtime.memory
    runtime.apply(a, {'pitch': 0}, 0)
    runtime.reset()
    assert not runtime.memory


def test_dialogue_keeps_cached_relations_role_routes_and_persistence(tmp_path):
    project, a, b, relation, engine = make_pair(role_a='CHORD', role_b='MELODY')
    engine.generate()
    assert not engine._has_explicit_role_route(a, b, 'pitch', 'pitch')
    assert not engine.relation_cycles()
    before = deepcopy(b.outputs)
    engine.apply_relations()
    assert b.outputs == before
    relation.parameters.update(call_bars=2, gap_beats=.25, reply='Contrast', follow=.4)
    duplicate = duplicate_relation(project, 0)
    duplicate.parameters['follow'] = .9
    assert relation.parameters['follow'] == .4
    path = tmp_path/'dialogue.json'; save_project(project, str(path))
    loaded = load_project(str(path))
    assert loaded.relations[0].parameters == relation.parameters
    assert loaded.relations[1].parameters == duplicate.parameters


def test_mute_no_port_and_mode_changes_preserve_phase_without_recording_muted_call(monkeypatch):
    project, a, b, relation, engine = make_pair()
    a.muted = True
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    for i in range(17): tick(i*.125)
    assert not engine.dialogue_runtime.memory or not next(iter(engine.dialogue_runtime.memory.values()))['samples']
    assert not any(m.type == 'note_on' and m.channel == 0 for _, m in sent)
    a.muted = False
    a.mode, b.mode = 'LIVE', 'SEQ'
    # Call resumes only next cycle, even after changing generator mode.
    for i in range(17, 33): tick(i*.125)
    assert any(m.type == 'note_on' and m.channel == 1 for _, m in sent)
    transport.stop(); sent.clear()
    transport.outputs.clear()
    transport.start()
    for i in range(33, 42): tick(i*.125)
    assert engine.dialogue_runtime.memory  # generation/capture also works without a MIDI port
    transport.stop()


@pytest.mark.parametrize('mode', ['SEQ', 'LIVE'])
def test_motif_scheduler_and_tempo_change_keep_turn_boundaries(monkeypatch, mode):
    from dataclasses import asdict
    from motif_engine import Motif
    project, a, b, relation, engine = make_pair(mode, mode, reply='Own phrase')
    motif = Motif('theme', 'Question/answer', notes=[0, 4, 7, 4], rhythm=[1, 0, 1, 1],
                  velocity=[.8]*4, step_beats=.5)
    project.motifs[motif.id] = asdict(motif)
    for block in (a, b):
        block.parameters['motif_id'] = motif.id
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    for i in range(9): tick(i*.125)
    assert engine.clock.position_beats == 2
    transport.set_tempo(60)
    assert engine.clock.position_beats == 2
    for i in range(9, 57): tick(i*.125)
    onsets = [(t, msg.channel) for t, msg in sent if msg.type == 'note_on']
    assert {ch for _, ch in onsets} == {0, 1}
    for t, channel in onsets:
        beat = t*2 if t <= 1 else 2+t-1
        phase = phase_at(settings(relation), beat)
        assert phase['phase'] == ('Call' if channel == 0 else 'Response')
    transport.stop()


def test_inline_dialogue_controls_history_copy_remove_and_narrow_layout(inspector, tmp_path):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = inspector
    win.tabs.setCurrentWidget(win.relation_graph)
    win.resize(820, 700); win.show(); QTest.qWait(30)
    win.relation_graph.dialogue_button.click(); QTest.qWait(40)
    row = win.relation_graph.rows[-1]
    relation = row.relation
    assert relation.algorithm == 'Dialogue' and relation.amount == 1
    assert row.dialogue.isVisible() and not row.fields['Output'].isVisible()
    assert not row.source.itemIcon(0).isNull() and not row.dest.itemIcon(0).isNull()
    controls = row.dialogue.controls
    controls['call_bars'].setValue(2); QTest.qWait(30)
    controls['gap_beats'].plus.click(); QTest.qWait(30)
    assert relation.parameters['gap_beats'] == .25
    controls['reply'].setCurrentText('Contrast'); QTest.qWait(30)
    assert relation.parameters['reply'] == 'Contrast'
    win.history_controller.move(); QTest.qWait(30)
    assert settings(win.project.relations[-1])['reply'] == 'Echo'
    win.history_controller.move(True); QTest.qWait(30)
    row = win.relation_graph.rows[-1]
    assert row.dialogue.controls['reply'].currentText() == 'Contrast'
    assert row.dialogue.width() <= win.relation_graph.scroll.viewport().width()
    row.duplicate.click(); QTest.qWait(40)
    assert len(win.project.relations) == 2
    win.relation_graph.update_runtime()
    assert 'already used' in win.relation_graph.rows[-1].dialogue.status.text()
    win.relation_graph.rows[-1].remove.click(); QTest.qWait(40)
    assert len(win.project.relations) == 1
    path = tmp_path/'dialogue_ui.json'
    assert win._write_project(str(path))
    assert settings(load_project(str(path)).relations[0])['call_bars'] == 2
    snapshot = document_state(win.project, win.engine)
    win.engine.clock.position_beats = 9
    win.relation_graph.update_runtime()
    assert document_state(win.project, win.engine) == snapshot
    for card in win.performance.findChildren(gui.PerformanceBlockCard):
        card.update_diagnostics(win.project, win.engine)
        assert 'Dialogue' in card.diagnostics.text()
    row = win.relation_graph.rows[0]
    row.algorithm.setCurrentText('Copy')
    assert not row.dialogue.isVisible() and row.fields['Output'].isVisible()
    assert not errors
