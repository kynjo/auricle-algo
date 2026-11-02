"""Exact musical sampling, shared policies and authored-state preservation."""
from copy import deepcopy
from itertools import permutations
import math

import pytest

from auricle_core import Block, Project, MusicEngine, ensure_drum_voices
from auricle_persistence import project_from_dict, save_project, load_project
from composition_planner import make_section, normalize_composition
from section_automation import (make_track, normalize_tracks, timing_for, parameter_specs, MAX_TRACKS)
from parameter_sources import SourceSnapshot, parameter_values, feedback_value
from parameter_influence import normalized_policy
from project_history import document_state
from test_coordinated_kit import setup_transport


def setup(mode='SEQ', meter='4/4', bars=2, algorithm='Pattern'):
    block = Block(1, 'Lead', 'MELODY', algorithm, mode, midi_port='capture',
                  parameters={'pattern': '1,2,3,4', 'gate': .8, 'pulses': 4,
                              'fill_density': 1., 'event_probability': 1., 'velocity_range': 0.,
                              'velocity_random': 0., 'velocity_base': .7, 'velocity_accent': 0.,
                              'live_min_beats': .25, 'live_max_beats': .25}, mutators=[])
    project = Project(tempo=120, length=16, blocks=[block])
    section = make_section('Verse', [block], bars=bars, neutral=True)
    project.composition = normalize_composition({'enabled': True, 'meter': meter, 'sections': [section]})
    engine = MusicEngine(project)
    engine.composition_runtime.playback_active = True
    return project, engine, block, project.composition['sections'][0]


def lane(engine, block, section, key='gate', value=.4, **changes):
    track = make_track(engine, block, key)
    track.update(value=value, **changes)
    section.setdefault('parameter_automation', []).append(track)
    return track


@pytest.mark.parametrize('order', list(permutations(('Macro: A', 'Technique: B', 'Parameter Modulation', 'Composition: C'))))
def test_four_source_priority_is_order_independent(order):
    project, engine, block, section = setup()
    targets = {'Macro: A': .2, 'Technique: B': .6, 'Parameter Modulation': .4, 'Composition: C': .3}
    for source in order: engine.set_parameter(block, 'gate', targets[source], source=source)
    assert block.parameters['gate'] == pytest.approx(.3)
    assert engine.parameter_influence.base_value(block, 'gate') == .8
    assert document_state(project, engine)['blocks'][0]['parameters']['gate'] == .8


@pytest.mark.parametrize('operation,operand,expected', [('set', .4, .4), ('add', .1, .9), ('multiply', .5, .4)])
def test_operations_do_not_accumulate_and_manual_base_is_live(operation, operand, expected):
    project, engine, block, section = setup()
    lane(engine, block, section, operation=operation, value=operand)
    for beat in [i / 20 for i in range(30)]: engine.section_automation.advance(beat)
    assert block.parameters['gate'] == pytest.approx(expected)
    engine.set_parameter(block, 'gate', .4)
    engine.section_automation.advance(2.)
    assert block.parameters['gate'] == pytest.approx(.4 if operation == 'set' else .5 if operation == 'add' else .2)
    engine.section_automation.reset()
    assert block.parameters['gate'] == .4


@pytest.mark.parametrize('policy,expected', [({'mode': 'manual'}, .8),
    ({'mode': 'blend'}, .6), ({'weights': {'Composition': .5}}, .6),
    ({'priority': ['Technique', 'Composition', 'Modulation', 'Macro']}, .7)])
def test_shared_policy_bypass_blend_and_partial_priority(policy, expected):
    project, engine, block, section = setup()
    if policy.get('priority'): engine.set_parameter(block, 'gate', .7, source='Technique: test')
    engine.parameter_influence.set_policy(block, 'gate', policy)
    lane(engine, block, section)
    engine.section_automation.advance(0)
    assert block.parameters['gate'] == pytest.approx(expected)
    mark = next(mark for mark in SourceSnapshot(engine).marks(block.id, 'gate') if mark.source == 'Composition')
    assert mark.active is (policy.get('mode') != 'manual' and not policy.get('priority'))


def test_legacy_policy_order_is_preserved_below_composition():
    policy = normalized_policy({'priority': ['Macro', 'Technique', 'Modulation']})
    assert policy['priority'] == ['Composition', 'Macro', 'Technique', 'Modulation']
    assert policy['weights']['Composition'] == 1.


@pytest.mark.parametrize('meter,bar', [('4/4', 4.), ('6/8', 3.), ('7/8', 3.5)])
@pytest.mark.parametrize('timing', ['continuous', 'step', 'beat', 'bar', 'cycle', 'section'])
def test_curves_sample_musical_time_with_meter_and_hold(timing, meter, bar):
    project, engine, block, section = setup(mode='LIVE', meter=meter)
    track = lane(engine, block, section, timing=timing, mode='curve', low=.2, high=1.,
                 curve={'enabled': True, 'shape': 'linear', 'points': [[0, 0], [1, 1]]})
    beat = bar + .37
    engine.section_automation.advance(beat)
    quantum = {'step': .25, 'beat': 1., 'bar': bar, 'cycle': 4.}.get(timing)
    sampled = 0. if timing == 'section' else math.floor((beat + 1e-9) / quantum) * quantum if quantum else beat
    assert block.parameters['gate'] == pytest.approx(.2 + .8 * sampled / (2 * bar))
    assert engine.section_automation.statuses[track['id']]['sample_beat'] == pytest.approx(sampled)
    project.tempo = 71
    engine.section_automation.advance(beat)
    assert block.parameters['gate'] == pytest.approx(.2 + .8 * sampled / (2 * bar))


def test_edit_of_held_lane_waits_for_next_boundary_and_seek_reconstructs():
    project, engine, block, section = setup()
    track = lane(engine, block, section, timing='bar', value=.2)
    engine.section_automation.advance(0)
    track['value'] = .9
    engine.section_automation.advance(1.1)
    assert block.parameters['gate'] == pytest.approx(.2)
    assert engine.section_automation.statuses[track['id']]['state'] == 'waiting for boundary'
    engine.section_automation.advance(3.99)
    assert block.parameters['gate'] == pytest.approx(.2)
    engine.section_automation.advance(4.)
    assert block.parameters['gate'] == pytest.approx(.9)
    track['value'] = .3
    engine.section_automation.advance(4.2)
    assert block.parameters['gate'] == pytest.approx(.9)
    engine.section_automation.reset()
    engine.section_automation.advance(4.2, force=True)
    assert block.parameters['gate'] == pytest.approx(.3)


def test_source_cycle_is_captured_from_manual_length_not_automated_length():
    project, engine, block, section = setup(bars=4)
    track = lane(engine, block, section, key='structure_length', mode='curve', low=8, high=16,
                 curve={'enabled': True, 'shape': 'linear', 'points': [[0, 0], [1, 1]]})
    engine.section_automation.advance(0)
    assert block.parameters['structure_length'] == 8
    engine.section_automation.advance(2.)
    assert block.parameters['structure_length'] == 8
    engine.section_automation.advance(4.)
    assert block.parameters['structure_length'] == 10
    assert engine.section_automation.states[track['id']]['cycle'] == 4.


def test_algorithm_snapshot_enables_matching_lanes_and_restores_authored_attributes():
    project, engine, block, section = setup()
    lane(engine, block, section, key='@algorithm', value='Random Walk')
    lane(engine, block, section, key='walk_step', value=7)
    engine.section_automation.advance(0)
    assert block.algorithm == 'Random Walk' and block.parameters['walk_step'] == 7
    state = document_state(project, engine)
    assert state['blocks'][0]['algorithm'] == 'Pattern'
    assert 'walk_step' not in state['blocks'][0]['parameters']
    engine.parameter_influence.manual(block, '@algorithm', 'Markov')
    assert block.algorithm == 'Random Walk'
    engine.section_automation.reset()
    assert block.algorithm == 'Markov' and 'walk_step' not in block.parameters


def test_unavailable_generator_lane_is_visible_and_does_not_write():
    project, engine, block, section = setup()
    track = lane(engine, block, section, key='walk_step', value=7)
    engine.section_automation.advance(0)
    assert 'walk_step' not in block.parameters
    assert engine.section_automation.statuses[track['id']]['state'] == 'unavailable for generator'


def test_integer_bool_and_text_rules_and_restore():
    project, engine, block, section = setup(algorithm='Euclidean')
    track = lane(engine, block, section, key='pulses', value=4.8, timing='continuous')
    spec = parameter_specs(engine, block)['pulses']
    assert timing_for(track, spec, block) == 'step'
    engine.section_automation.advance(0)
    assert block.parameters['pulses'] == 5 and isinstance(block.parameters['pulses'], int)
    section['parameter_automation'] = []
    lane(engine, block, section, key='@algorithm', value='Pattern')
    lane(engine, block, section, key='pattern', value='1,0,0,0,1')
    lane(engine, block, section, key='pattern_reverse', value=True)
    engine.section_automation.advance(4., force=True)
    assert block.algorithm == 'Pattern' and block.parameters['pattern'] == '1,0,0,0,1'
    assert block.parameters['pattern_reverse'] is True
    engine.section_automation.reset()
    assert block.algorithm == 'Euclidean' and block.parameters['pattern'] == '1,2,3,4'
    assert 'pattern_reverse' not in block.parameters and block.parameters['pulses'] == 4


def test_assigned_outline_active_green_and_bypass_sources_are_read_only():
    project, engine, block, section = setup()
    lane(engine, block, section, key='gate', value=.4)
    before = deepcopy(block.parameters)
    snapshot = SourceSnapshot(engine)
    assert not next(mark for mark in snapshot.marks(block.id, 'gate') if mark.source == 'Composition').active
    assert block.parameters == before
    engine.section_automation.advance(0)
    snapshot = SourceSnapshot(engine)
    marks = snapshot.marks(block.id, 'gate')
    assert next(mark for mark in marks if mark.source == 'Composition').active
    assert parameter_values(engine, block.id, 'gate') == (.8, .4)
    engine.parameter_influence.set_policy(block, 'gate', {'mode': 'manual'})
    assert not next(mark for mark in SourceSnapshot(engine).marks(block.id, 'gate') if mark.source == 'Composition').active


def test_voice_id_is_distinct_from_kit_and_deleted_targets_leave_no_layer():
    project, engine, block, section = setup()
    drum = Block(2, 'Kit', 'DRUM'); ensure_drum_voices(drum); project.blocks.append(drum)
    voice = drum.drum_voices[0]; original = deepcopy(voice.parameters)
    lane(engine, voice, section, key='gate', value=.3)
    engine.section_automation.advance(0)
    assert voice.parameters['gate'] == .3 and drum.parameters.get('gate') != .3
    project.blocks.remove(drum)
    engine.section_automation.advance(.5)
    assert not any(owner == voice.id for owner, _key in engine.parameter_influence.entries)


@pytest.mark.parametrize('active', [None, False])
def test_enabled_form_cannot_change_parameters_while_stopped_or_blocks(active):
    project, engine, block, section = setup()
    lane(engine, block, section)
    engine.composition_runtime.playback_active = active
    engine.section_automation.advance(4.)
    assert block.parameters['gate'] == .8
    assert not engine.parameter_influence.entries


@pytest.mark.parametrize('mode', ['SEQ', 'LIVE'])
def test_transport_stop_seek_tempo_loop_and_note_lifetimes(monkeypatch, mode):
    project, engine, block, section = setup(mode=mode, bars=1)
    lane(engine, block, section, mode='curve', low=.2, high=.8,
         curve={'enabled': True, 'shape': 'linear', 'points': [[0, 0], [1, 1]]})
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine, playback_mode='composition')
    for i in range(70): tick(i / 50)
    transport.seek(2.)
    assert block.parameters['gate'] == pytest.approx(.5)
    transport.set_tempo(90)
    for i in range(71, 150): tick(i / 50)
    transport.stop()
    assert block.parameters['gate'] == .8
    assert not transport.active_notes
    by_key = {}
    for _time, message in sent:
        if message.type in ('note_on', 'note_off'):
            by_key.setdefault((message.channel, message.note), []).append(message.type)
    assert by_key and all(events[-1] == 'note_off' for events in by_key.values())


def test_curve_and_assignments_roundtrip_without_runtime_values(tmp_path):
    project, engine, block, section = setup()
    lane(engine, block, section)
    engine.section_automation.advance(0)
    path = tmp_path / 'automation.json'
    save_project(project_from_dict(document_state(project, engine)), str(path))
    restored = load_project(str(path))
    assert restored.blocks[0].parameters['gate'] == .8
    assert restored.composition['sections'][0]['parameter_automation'] == section['parameter_automation']


def test_malformed_tracks_are_bounded_and_finite_and_ids_unique():
    source = [{'id': 'same', 'entity_id': -101, 'parameter': 'gate', 'value': float('nan'), 'weight': float('inf')},
              {'id': 'same', 'entity_id': 1, 'parameter': 'gate', 'low': -float('inf'), 'curve': {}},
              {'entity_id': True, 'parameter': 'gate'}, {'entity_id': 1, 'parameter': '@bad'}]
    normalized = normalize_tracks(source)
    assert len(normalized) == 2 and len({track['id'] for track in normalized}) == 2
    assert all(math.isfinite(track['low']) and math.isfinite(track['high']) for track in normalized)
    assert len(normalize_tracks(source * 1000)) <= MAX_TRACKS


def test_section_change_and_loop_clear_previous_layers_and_generation_is_batched(monkeypatch):
    project, engine, block, section = setup(bars=1)
    second = make_section('Break', [block], bars=1, neutral=True)
    project.composition['sections'].append(second)
    lane(engine, block, section)
    calls = []
    monkeypatch.setattr(engine, 'generate', lambda: calls.append(1))
    for beat in (0., .01, .02, .05, .10, .2): engine.section_automation.advance(beat)
    assert len(calls) == 1
    engine.section_automation.advance(4.)
    assert block.parameters['gate'] == .8
    engine.section_automation.advance(8.)
    assert block.parameters['gate'] == .4


def test_hold_endpoint_allows_edits_when_no_later_cycle_boundary_exists():
    project, engine, block, section = setup(meter='6/8', bars=2)
    project.composition.update(loop=False, end_action='hold')
    track = lane(engine, block, section, value=.2, timing='cycle')
    engine.section_automation.advance(0.)
    engine.section_automation.advance(10.)
    track['value'] = .7
    engine.section_automation.advance(11.)
    assert block.parameters['gate'] == pytest.approx(.7)


def test_default_form_and_new_sections_have_stable_roundtrip():
    from composition_planner import default_composition
    for config in (default_composition(), {'sections': [make_section()]}):
        normalized = normalize_composition(config)
        assert normalized == normalize_composition(deepcopy(normalized))
        assert normalized['sections'][0]['parameter_automation'] == []


def test_known_ranges_and_defaults_match_controls_without_stored_keys():
    project, engine, block, section = setup()
    project.length = 24; project.root_note = 57
    specs = parameter_specs(engine, block)
    assert (specs['gate'].low, specs['gate'].high) == (.05, 1.5)
    assert specs['velocity_base'].low == 0 and specs['velocity_base'].high == 1
    assert make_track(engine, block, 'scale_root')['value'] == 57
    assert make_track(engine, block, 'structure_length')['value'] == 24
    assert specs['relation_chord_source'].choices == (-1,)
