"""Regression tests for the defects fixed in v42."""
import json
import random

import generators as G
from auricle_core import (Block, MusicEngine, Mutator, Process, Project, Relation, Transport,
                          load_project, midi_note_for)


class CapturePort:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)


class DummyApp:
    def __init__(self, project):
        self.project = project
        self.engine = MusicEngine(project)

    def log_midi_message(self, *args):
        pass

    def set_message(self, *args):
        pass


def _seq(algorithm, length=16, seed=1, **params):
    p = Project(length=length, seed=seed)
    b = Block(1, 'x', 'MELODY', algorithm, 'SEQ', parameters=params)
    p.blocks = [b]
    e = MusicEngine(p)
    e.generate()
    return b, e, p


def test_markov_root_note_is_not_a_rest():
    b, _, _ = _seq('Markov', length=64)
    for r, pitch in zip(b.outputs['rhythm'], b.outputs['pitch']):
        if pitch == 0.0:
            assert r == 1.0
    assert all(r == 1.0 for r in b.outputs['rhythm'])


def test_markov_rest_and_stay_parameters_work_in_seq():
    rests, _, _ = _seq('Markov', length=64, markov_rest=1.0)
    assert not any(rests.outputs['rhythm'])
    stay, _, _ = _seq('Markov', length=32, markov_stay=1.0)
    assert len(set(stay.outputs['pitch'])) == 1


def test_rhythm_hit_value_does_not_leak_into_pitch():
    b, _, _ = _seq('Euclidean', pulses=4)
    assert all(v == 0.0 for v in b.outputs['pitch'])


def test_relations_do_not_accumulate():
    p = Project(length=8)
    a = Block(1, 'a', 'MELODY', 'Pattern', 'SEQ', parameters={'pattern': '1,1,1,1'})
    d = Block(2, 'd', 'MELODY', 'Scale Walker', 'SEQ')
    p.blocks = [a, d]
    p.relations = [Relation(1, 'pitch', 2, 'pitch', 'Modulate', 1.0)]
    e = MusicEngine(p)
    e.generate()
    first = list(d.outputs['pitch'])
    for _ in range(5):
        e.apply_relations()
    e.regenerate(a)
    assert d.outputs['pitch'] == first


def test_relation_from_live_source_keeps_destination_length():
    p = Project(length=16)
    s = Block(1, 's', 'MELODY', 'Markov', 'LIVE')
    d = Block(2, 'd', 'MELODY', 'Scale Walker', 'SEQ')
    p.blocks = [s, d]
    p.relations = [Relation(1, 'pitch', 2, 'pitch', 'Mix', 0.5)]
    e = MusicEngine(p)
    e.live_event(s)
    e.generate()
    assert len(d.outputs['pitch']) == 16


def test_parameter_modulation_does_not_alter_its_source():
    src = Block(1, 's', 'MELODY', 'Scale Walker', 'SEQ')
    dst = Block(2, 't', 'MELODY', 'Probability', 'SEQ')
    e = MusicEngine(Project(length=8, blocks=[src, dst]))
    e.generate()
    before = list(src.outputs['pitch'])
    src.processes = [Process('Parameter Modulation', 'pitch', 1.0,
                             {'destination_block': 2, 'destination_parameter': 'probability', 'min': 0.0, 'max': 1.0})]
    e.generate()
    assert src.outputs['pitch'] == before


def test_parameter_modulation_delay_is_exact():
    for delay in (1, 2, 3):
        s = Block(1, 's', 'MELODY', 'Pattern', 'SEQ', parameters={'pattern': '1,1,1,1'})
        t = Block(2, 't', 'MELODY', 'Probability', 'SEQ', parameters={'probability': 0.25})
        s.processes = [Process('Parameter Modulation', 'rhythm', 1.0, {
            'destination_block': 2, 'destination_parameter': 'probability',
            'source_min': 0, 'source_max': 1, 'min': 0, 'max': 1, 'delay': delay})]
        e = MusicEngine(Project(length=4, blocks=[s, t]))
        e.generate()
        e.collect_parameter_modulations(s, 0)
        ticks = 0
        while t.parameters['probability'] == 0.25 and ticks < 10:
            e.apply_pending_parameter_modulations()
            ticks += 1
        assert ticks == delay


def test_reset_live_clears_delayed_modulations():
    e = MusicEngine(Project())
    e.delayed_parameter_modulations.append((3, (1, 'fill_density'), 0.5))
    e.reset_live()
    assert e.delayed_parameter_modulations == []


def test_macro_is_idempotent_with_partial_amount():
    b = Block(1, 'x', 'MELODY', 'Euclidean')
    p = Project(blocks=[b], macros=[{'value': 1.0, 'routes': [
        {'block_id': 1, 'parameter': 'fill_density', 'min': 0.0, 'max': 0.0, 'amount': 0.5}]}])
    e = MusicEngine(p)
    values = []
    for _ in range(3):
        e.apply_macros()
        values.append(b.parameters['fill_density'])
    assert values == [0.5, 0.5, 0.5]


def test_seq_generation_is_reproducible_with_density():
    for algorithm, params in (('Cellular Automaton', {'ca_density': 0.5}), ('Thue-Morse', {'tm_density': 0.5})):
        outs = {tuple(_seq(algorithm, length=32, seed=5, **params)[0].outputs['rhythm']) for _ in range(5)}
        assert len(outs) == 1, algorithm


def test_previously_dead_parameters_have_an_effect():
    assert sum(_seq('Thue-Morse', tm_density=0.0)[0].outputs['rhythm']) == 0
    assert (_seq('Scale Walker', length=32, seed=3, scale_leap=0.0)[0].outputs['pitch']
            != _seq('Scale Walker', length=32, seed=3, scale_leap=1.0)[0].outputs['pitch'])
    low = _seq('Probability', length=32, seed=3, probability=1.0, probability_velocity_floor=0.0)[0]
    high = _seq('Probability', length=32, seed=3, probability=1.0, probability_velocity_floor=1.0)[0]
    assert low.outputs['velocity'] != high.outputs['velocity']
    assert all(v == 1.0 for v, r in zip(high.outputs['velocity'], high.outputs['rhythm']) if r)


def test_legacy_event_density_is_applied_once():
    kept = 0
    for seed in range(200):
        b, _, _ = _seq('Euclidean', seed=seed, pulses=16, euclidean_steps=16, event_density=0.5)
        kept += sum(b.outputs['rhythm'])
    assert 0.44 < kept / (16 * 200) < 0.56


def test_rhythm_mutator_does_not_create_ghost_notes():
    p = Project(length=8)
    b = Block(1, 'd', 'DRUM', 'Euclidean', 'SEQ', parameters={'pulses': 2, 'euclidean_steps': 8})
    b.mutators.append(Mutator('Rotate', 0.25, 'rhythm'))
    p.blocks = [b]
    MusicEngine(p).generate()
    for r, v, d in zip(b.outputs['rhythm'], b.outputs['velocity'], b.outputs['duration']):
        if r:
            assert v > 0.5 and d > 0


def test_fibonacci_live_stays_in_scale():
    p = Project(length=16)
    b = Block(1, 'x', 'MELODY', 'Fibonacci', 'LIVE')
    p.blocks = [b]
    e = MusicEngine(p)
    major = {0, 2, 4, 5, 7, 9, 11}
    pitches = {round(e.live_event(b)['pitch']) % 12 for _ in range(32)}
    assert pitches <= major


def test_live_rhythm_starts_on_step_zero():
    p = Project(length=16)
    b = Block(1, 'x', 'DRUM', 'Bresenham', 'LIVE', parameters={'bres_pulses': 4})
    p.blocks = [b]
    assert MusicEngine(p).live_event(b) is not None  # step 0 is always a Bresenham hit


def test_key_transposes_sent_notes():
    for root in (60, 62, 67):
        project = Project(root_note=root)
        block = Block(1, 'm', 'MELODY', 'Arpeggiator', 'SEQ')
        drum = Block(2, 'd', 'DRUM', 'Euclidean', 'SEQ', midi_note=36)
        project.blocks = [block, drum]
        assert midi_note_for(project, block, 0.0) == 60 + root % 12
        assert midi_note_for(project, drum, 5.0) == 36


def test_seq_transport_uses_duration_stream_and_current_tempo():
    project = Project(tempo=120)
    block = Block(1, 'b', 'BASS', 'Euclidean', 'SEQ', midi_port='p', parameters={'pulses': 16})
    project.blocks = [block]
    app = DummyApp(project)
    transport = Transport(app)
    app.engine.generate()
    block.outputs['duration'] = [1.0] * project.length
    port = CapturePort()
    transport._seq_event(block, 0.0, port)
    due = transport.active_notes[-1][0]
    assert abs(transport.seq_interval - 0.125) < 1e-9
    project.tempo = 60
    assert abs(transport.seq_interval - 0.25) < 1e-9
    assert due > 0


def test_quantizer_keeps_low_register_and_pitch_class_roots():
    assert G.quantize_to_scale(41, 60, "Dorian") == 41  # F two octaves below is in C Dorian
    assert G.quantize_to_scale(-10, 2, "Major") == -10  # D major, root given as pitch class


def test_bresenham_does_not_double_hit_at_loop_seam():
    assert G.bresenham(16, 4) == [1.0 if i % 4 == 0 else 0.0 for i in range(16)]


def test_text_parameters_never_crash_generation():
    for algorithm, params in (('Arpeggiator', {'arp_pattern': '0,x,4,'}),
                              ('Weighted Scale', {'scale_weights': 'a,b'}),
                              ('L-System', {'ls_mapping': '1,?'}),
                              ('Pattern', {'pattern': 'oops'})):
        b, _, _ = _seq(algorithm, **params)
        assert len(b.outputs['pitch']) == 16


def test_load_project_ignores_unknown_fields(tmp_path):
    data = {'blocks': [{'id': 1, 'name': 'x', 'block_type': 'BASS', 'future_field': 1,
                        'mutators': [{'name': 'Reverse', 'amount': 0.5, 'target': 'pitch', 'extra': True}],
                        'processes': [{'type': 'Delay', 'extra': 1}]}],
            'relations': [{'source_block': 1, 'source_part': 'pitch', 'destination_block': 1,
                           'destination_part': 'pitch', 'algorithm': 'Mix', 'extra': 0}]}
    path = tmp_path / 'p.json'
    path.write_text(json.dumps(data))
    project = load_project(str(path))
    assert project.blocks[0].processes[0].type == 'Delay'
    assert project.relations[0].algorithm == 'Mix'


def test_generators_do_not_use_global_random():
    random.seed(1)
    a = G.cellular_automaton(32, density=0.5, rng=random.Random(9))
    random.seed(2)
    b = G.cellular_automaton(32, density=0.5, rng=random.Random(9))
    assert a == b
