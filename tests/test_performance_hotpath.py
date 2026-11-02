from copy import deepcopy

from auricle_engine import MusicEngine
from auricle_model import Block, Project, Relation
import relation_runtime
import voice_leading


def _stream(rhythm, pitch=None):
    n = len(rhythm)
    return {
        "rhythm": list(rhythm),
        "pitch": list(pitch if pitch is not None else [0.0] * n),
        "velocity": [0.7 if hit else 0.0 for hit in rhythm],
        "duration": [0.8 if hit else 0.0 for hit in rhythm],
        "density": list(rhythm),
        "accent": [0.0] * n,
    }


def test_relation_execution_plan_is_reused_and_invalidated_on_route_edit(monkeypatch):
    source = Block(1, "Source", "PAD", "Pattern", "SEQ", mutators=[])
    target = Block(2, "Target", "PAD", "Pattern", "SEQ", mutators=[])
    route = Relation(1, "rhythm", 2, "rhythm", "Copy", 1.0, id=1)
    engine = MusicEngine(Project(blocks=[source, target], relations=[route]))
    engine._base_outputs = {1: _stream([1, 0]), 2: _stream([0, 0])}
    source.outputs = deepcopy(engine._base_outputs[1])
    target.outputs = deepcopy(engine._base_outputs[2])

    original = relation_runtime.components
    calls = []
    def counted(graph):
        calls.append(1)
        return original(graph)
    monkeypatch.setattr(relation_runtime, "components", counted)

    engine.apply_relations()
    engine.apply_relations()
    assert len(calls) == 1
    route.destination_part = "velocity"
    engine.apply_relations()
    assert len(calls) == 2


def test_relation_runtime_reuses_committed_feedback_snapshot_between_idle_ticks():
    source = Block(1, "Source", "PAD", "Pattern", "LIVE", mutators=[])
    target = Block(2, "Target", "PAD", "Pattern", "LIVE", mutators=[])
    engine = MusicEngine(Project(blocks=[source, target], relations=[
        Relation(1, "rhythm", 2, "rhythm", "Copy", 1.0, id=1)
    ]))
    source.outputs = _stream([1, 0])
    target.outputs = _stream([0, 0])
    runtime = engine.relation_runtime
    runtime.begin_tick()
    runtime.end_tick()
    committed = runtime._committed
    runtime.begin_tick()
    assert runtime.feedback is committed
    runtime.end_tick()
    assert runtime._committed is committed


def test_live_source_event_does_not_recompute_full_relation_graph():
    source = Block(1, "Source", "PAD", "Pattern", "LIVE", parameters={"pattern": "1,0"}, mutators=[])
    target = Block(2, "Target", "PAD", "Pattern", "LIVE", parameters={"pattern": "1"}, mutators=[])
    engine = MusicEngine(Project(blocks=[source, target], relations=[
        Relation(1, "rhythm", 2, "rhythm", "Copy", 1.0, id=1)
    ]))
    calls = []
    original = engine.apply_relations
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    engine.apply_relations = counted

    assert engine.live_event(source) is not None
    assert calls == []
    assert engine.live_event(target) is not None
    assert len(calls) == 1


def test_chord_voicing_cache_reuses_result_and_invalidates_for_parameter_change(monkeypatch):
    chord = Block(1, "Chord", "CHORD", "Pattern", "SEQ", midi_note=60,
                  parameters={"harmony_size": 3, "harmony_spread": 7}, mutators=[])
    engine = MusicEngine(Project(blocks=[chord]))
    original = voice_leading.VoiceLeading.resolve_chord
    calls = []
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(voice_leading.VoiceLeading, "resolve_chord", staticmethod(counted))

    first = engine._chord_pitches(chord, 0.0)
    second = engine._chord_pitches(chord, 0.0)
    assert first == second
    assert len(calls) == 1
    chord.parameters["harmony_size"] = 4
    third = engine._chord_pitches(chord, 0.0)
    assert len(third) == 4
    assert len(calls) == 2


def test_transport_order_cache_is_rebuilt_only_when_scheduler_topology_changes(monkeypatch):
    from auricle_transport import Transport

    source = Block(1, "Source", "PAD", "Pattern", "SEQ", mutators=[])
    target = Block(2, "Target", "PAD", "Pattern", "LIVE", mutators=[])
    engine = MusicEngine(Project(blocks=[source, target], relations=[
        Relation(1, "rhythm", 2, "rhythm", "Copy", 1.0, id=1)
    ]))
    class App:
        project = engine.project
        def __init__(self): self.engine = engine
        def set_message(self, _message): pass
    transport = Transport(App())
    original = engine.role_relation_source
    calls = []
    def counted(block):
        calls.append(block.id)
        return original(block)
    monkeypatch.setattr(engine, "role_relation_source", counted)

    first = transport._ordered_tick_blocks()
    first_calls = len(calls)
    second = transport._ordered_tick_blocks()
    assert [block.id for block in first] == [block.id for block in second]
    assert len(calls) == first_calls

    target.mode = "SEQ"
    transport._ordered_tick_blocks()
    assert len(calls) > first_calls
