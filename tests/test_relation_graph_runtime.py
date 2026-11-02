"""Relations must behave as a graph, not as a list of destructive edits."""
from copy import deepcopy
from itertools import permutations
from types import SimpleNamespace

import pytest

from auricle_core import Block, Project, MusicEngine, Relation, Process, Transport, ensure_drum_voices
from relation_runtime import RELATION_DESCRIPTIONS


def stream(rhythm, velocity=None, pitch=None):
    n = len(rhythm)
    return dict(rhythm=list(rhythm), velocity=list(velocity or [.7*r for r in rhythm]),
                pitch=list(pitch or [0]*n), duration=[.8*r for r in rhythm],
                density=list(rhythm), accent=[0]*n)


def rig(material, routes, modes=None):
    blocks = [Block(i, str(i), "MELODY", "Pattern", (modes or {}).get(i, "SEQ"), mutators=[])
              for i in material]
    engine = MusicEngine(Project(length=len(next(iter(material.values()))['rhythm']), seed=73,
                                 blocks=blocks, relations=routes))
    engine._base_outputs = deepcopy(material)
    for b in blocks: b.outputs = deepcopy(material[b.id])
    return engine, {b.id: b for b in blocks}


def test_chain_reordering_and_repeated_refresh_do_not_change_result():
    material = {1: stream([1,0,1,0]), 2: stream([0]*4), 3: stream([0]*4)}
    routes = [Relation(1,'rhythm',2,'rhythm','Copy',1), Relation(2,'rhythm',3,'rhythm','Copy',1)]
    for order in permutations(routes):
        e, blocks = rig(material, list(order))
        for _ in range(3):
            e.apply_relations()
            assert blocks[2].outputs['rhythm'] == blocks[3].outputs['rhythm'] == [1,0,1,0]
            assert all(blocks[3].outputs['velocity'][i] > 0 for i in (0,2))
            assert blocks[3].outputs['velocity'][1] == 0


def test_multiple_inputs_and_mixed_operations_have_commutative_fan_in():
    material = {1: stream([1]*16, [.2]*16), 2: stream([1]*16, [.8]*16), 3: stream([1]*16, [.1]*16)}
    routes = [Relation(1,'velocity',3,'velocity','Mix',.5,id=10),
              Relation(2,'velocity',3,'velocity','Mix',.5,id=11),
              Relation(1,'velocity',3,'velocity','Modulate',.5,id=12)]
    for order in permutations(routes):
        e, blocks = rig(material, list(order)); e.apply_relations()
        assert blocks[3].outputs['velocity'] == pytest.approx([.6]*16)


def test_legacy_zero_ids_and_probability_are_independent_of_row_order():
    material = {1: stream([1]*128, [.2]*128), 2: stream([1]*128, [.8]*128), 3: stream([1]*128, [.4]*128)}
    routes = [Relation(1,'velocity',3,'velocity','Copy',.5,probability=.6),
              Relation(2,'velocity',3,'velocity','Mix',.4,probability=.3)]
    e, blocks = rig(material, routes); e.apply_relations(); expected = deepcopy(blocks[3].outputs)
    e.project.relations.reverse(); e.project.blocks.reverse(); e.apply_relations()
    assert blocks[3].outputs == expected


@pytest.mark.parametrize('operation', RELATION_DESCRIPTIONS)
def test_zero_amount_and_zero_probability_are_true_bypass(operation):
    material = {1: stream([1,0,1,0], [.3]*4), 2: stream([0,1,1,0])}
    for amount, probability in ((0,1), (1,0)):
        for target in ('rhythm','velocity','pitch','duration'):
            e, blocks = rig(material, [Relation(1,target,2,target,operation,amount,probability=probability)])
            e.apply_relations(); assert blocks[2].outputs == material[2]


@pytest.mark.parametrize('operation', ['Copy','Mix','Modulate','Trigger'])
def test_rhythm_amount_gradually_adds_reproducible_binary_events(operation):
    material = {1: stream([1]*512), 2: stream([0]*512)}
    route = Relation(1,'rhythm',2,'rhythm',operation,0,id=5)
    e, blocks = rig(material, [route]); hit_sets = []
    for a in (0,.01,.25,.5,.75,1):
        route.amount = a; e.apply_relations()
        hits = {i for i,v in enumerate(blocks[2].outputs['rhythm']) if v}
        hit_sets.append(hits)
        assert set(blocks[2].outputs['rhythm']) <= {0,1}
        result = deepcopy(blocks[2].outputs); e.apply_relations(); assert blocks[2].outputs == result
    assert hit_sets[0] == set() and len(hit_sets[-1]) == 512
    assert all(a < b for a,b in zip(hit_sets, hit_sets[1:]))


@pytest.mark.parametrize('operation,expected', [
    ('Copy',[1,0,1,0]), ('Mix',[1,1,1,0]), ('Follow',[0,0,1,0]),
    ('Quantize To',[1,0,1,0]), ('Modulate',[1,1,1,0]), ('Trigger',[1,0,1,0]),
])
def test_rhythm_operation_contracts(operation, expected):
    e, blocks = rig({1:stream([1,0,1,0]), 2:stream([0,1,1,0])},
                    [Relation(1,'rhythm',2,'rhythm',operation,1)])
    e.apply_relations(); assert blocks[2].outputs['rhythm'] == expected


def test_quantize_to_uses_source_palette_not_rounded_source_at_same_index():
    e, blocks = rig({1:stream([1]*4,[.2,.8,.2,.8]),2:stream([1]*4,[.7,.1,.6,.3])},
                    [Relation(1,'velocity',2,'velocity','Quantize To',1)])
    e.apply_relations(); assert blocks[2].outputs['velocity'] == [.8,.2,.8,.2]


@pytest.mark.parametrize('mode',['SEQ','LIVE'])
def test_feedback_pitch_quantization_respects_the_source_base_note(mode):
    material={1:stream([1]*4,pitch=[0]*4),2:stream([1]*4,pitch=[2]*4)}
    e,blocks=rig(material,[Relation(1,'pitch',2,'pitch','Quantize To',1),
                          Relation(2,'pitch',1,'pitch','Modulate',.1)],{1:mode,2:mode})
    blocks[1].midi_note=65  # source offset zero is F, not destination C
    e.relation_runtime.begin_tick(); e.apply_relations()
    assert blocks[2].outputs['pitch'] == [5]*4


def test_copy_selects_values_mix_interpolates_and_follow_tracks_envelope():
    material = {1:stream([1]*128,[.2]*128),2:stream([1]*128,[.8]*128)}
    results = {}
    for op in ('Copy','Mix','Follow'):
        e, blocks = rig(material,[Relation(1,'velocity',2,'velocity',op,.5)])
        e.apply_relations(); results[op] = blocks[2].outputs['velocity']
    assert set(results['Copy']) == {.2,.8}
    assert results['Mix'] == pytest.approx([.5]*128)
    assert results['Follow'] == pytest.approx([.48]*128)


def test_ranges_and_derived_accents_are_valid_before_downstream_reads():
    e, blocks = rig({1:stream([1]*4,[1]*4),2:stream([1]*4,[.9]*4),3:stream([1]*4,[0]*4)}, [
        Relation(2,'accent',3,'velocity','Copy',1), Relation(1,'velocity',2,'velocity','Modulate',1)])
    e.apply_relations()
    assert blocks[2].outputs['velocity'] == [1]*4
    assert blocks[2].outputs['accent'] == blocks[3].outputs['velocity'] == [1]*4


def test_stream_cycles_avoid_block_level_false_positives_and_duplicates():
    material={1:stream([1]*4),2:stream([0]*4)}
    e,_=rig(material,[Relation(1,'rhythm',2,'rhythm','Copy',1),Relation(2,'velocity',1,'velocity','Copy',1)])
    assert e.relation_cycles() == []
    e.project.relations[1].destination_part='rhythm'
    # rhythm->velocity is a real internal dependency, so this is feedback.
    assert e.relation_cycles() == [[1,2,1]]
    e.project.relations.reverse(); assert e.relation_cycles() == [[1,2,1]]


def test_seq_feedback_is_causal_and_idempotent():
    material={1:stream([1,0,0,0]),2:stream([0]*4)}
    routes=[Relation(1,'rhythm',2,'rhythm','Mix',1),Relation(2,'rhythm',1,'rhythm','Mix',1)]
    e,blocks=rig(material,routes)
    for _ in range(3):
        e.apply_relations()
        assert blocks[1].outputs['rhythm'] == [1,0,1,0]
        assert blocks[2].outputs['rhythm'] == [0,1,0,1]
        e.project.relations.reverse()


def test_live_feedback_uses_one_frozen_frame_for_all_calls_in_tick():
    material={1:stream([1]),2:stream([0])}
    routes=[Relation(1,'rhythm',2,'rhythm','Copy',1),Relation(2,'rhythm',1,'rhythm','Copy',1)]
    e,blocks=rig(material,routes,{1:'LIVE',2:'LIVE'})
    e.relation_runtime.begin_tick()
    e.relation_runtime.advance_source(blocks[1])
    for _ in range(3):
        e.apply_relations()
        assert blocks[1].outputs['rhythm'] == [0]
        assert blocks[2].outputs['rhythm'] == [1]
        e.project.relations.reverse()
    e.relation_runtime.end_tick()
    e.relation_runtime.begin_tick(); e.apply_relations()
    assert blocks[1].outputs['rhythm'] == [1] and blocks[2].outputs['rhythm'] == [0]
    # Applying/refreshing during idle ticks is not another musical step.
    for _ in range(3):
        e.relation_runtime.end_tick(); e.relation_runtime.begin_tick(); e.apply_relations()
        assert blocks[1].outputs['rhythm'] == [1] and blocks[2].outputs['rhythm'] == [0]


def test_live_delay_reads_previous_published_attempt_including_rest():
    source=Block(1,'Source','MELODY','Pattern','LIVE',mutators=[],parameters={'pattern':'1,0'})
    target=Block(2,'Target','MELODY','Pattern','LIVE',mutators=[],parameters={'pattern':'1'})
    e=MusicEngine(Project(blocks=[source,target],relations=[Relation(1,'rhythm',2,'rhythm','Copy',1,delay=1)]))
    accepted=[]
    for _ in range(4):
        e.relation_runtime.begin_tick()
        e.live_event(source); accepted.append(e.live_event(target) is not None)
    assert accepted == [False,True,False,True]


def test_delayed_source_is_not_rewritten_by_an_intervening_graph_refresh():
    source=Block(1,'Source','MELODY','Pattern','LIVE',mutators=[],parameters={'pattern':'1,0'})
    target=Block(2,'Target','MELODY','Pattern','LIVE',mutators=[],parameters={'pattern':'1'})
    e=MusicEngine(Project(blocks=[source,target],relations=[Relation(1,'rhythm',2,'rhythm','Copy',1,delay=1)]))
    assert e.live_event(source) is not None
    source.outputs=stream([0])  # later graph/preview state isn't a new attempt
    assert e.live_event(source) is None
    assert e.live_event(target) is not None  # delayed source was the published hit


def test_discarded_live_event_never_queues_parameter_modulation():
    source=Block(1,'Source','MELODY','Pattern','LIVE',mutators=[],parameters={'pattern':'1','fill_density':0})
    target=Block(2,'Target','MELODY',mutators=[])
    source.processes=[Process('Parameter Modulation','rhythm',1,{'destination_block':2,
        'destination_parameter':'fill_density','source_min':0,'source_max':1,'min':0,'max':1})]
    e=MusicEngine(Project(blocks=[source,target]))
    assert e.live_event(source) is None
    assert not e.pending_parameter_modulations and not e.delayed_parameter_modulations
    assert source.outputs['rhythm'] == [0]
    source.parameters['fill_density']=1
    assert e.live_event(source) is not None
    assert any(key[:2] == (2, 'fill_density') and value == 1 for key, value in e.pending_parameter_modulations.items())


def test_live_drum_bus_delay_advances_once_for_a_group_of_voices():
    drum=Block(1,'Kit','DRUM',mode='LIVE')
    voices=ensure_drum_voices(drum)[:2]; drum.drum_voices=voices
    for voice in voices:
        voice.algorithm='Pattern'; voice.parameters.update(pattern='1,0',fill_density=1)
    target=Block(2,'Target','MELODY','Pattern','LIVE',mutators=[],parameters={'pattern':'1'})
    e=MusicEngine(Project(blocks=[drum,target],relations=[Relation(1,'rhythm',2,'rhythm','Copy',1,delay=1)]))
    e.generate(); heard=[]
    for _ in range(4):
        e.relation_runtime.begin_tick()
        for voice in voices:
            e.live_event(voice); e._aggregate_drum_outputs(drum)
        heard.append(e.live_event(target) is not None)
        e.relation_runtime.end_tick()
    assert heard == [False,True,False,True]


def test_zero_velocity_route_does_not_emit_a_velocity_one_ghost_note():
    source=Block(1,'Source','MELODY','Pattern','SEQ',mutators=[])
    target=Block(2,'Target','MELODY','Pattern','LIVE',mutators=[],parameters={'pattern':'1'})
    e=MusicEngine(Project(blocks=[source,target],relations=[Relation(1,'velocity',2,'velocity','Copy',1)]))
    source.outputs=stream([1],[0]); e._base_outputs[1]=deepcopy(source.outputs)
    assert e.live_event(target) is None
    sent=[]
    t=Transport(SimpleNamespace(project=e.project,engine=e))
    port=SimpleNamespace(send=sent.append)
    assert t._dispatch_event(target,{'pitch':0,'velocity':0},port,.1) is None
    assert not sent
