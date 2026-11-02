"""Interactions verified at the event/MIDI boundary, not just the preview."""
from copy import deepcopy
from statistics import mean

import pytest

from auricle_core import Block, Project, MusicEngine, Mutator, Process, Relation, midi_note_for, save_project, load_project, GENERATORS, BLOCK_TYPES
from performance_presets import presets_for_entity
from project_history import document_state
from test_coordinated_kit import kit, setup_transport
from test_kit_preview_lifecycle import inspector


def lead(bid=2, mode="SEQ", pattern="1"):
    return Block(bid, "Lead", "MELODY", "Pattern", mode, midi_port="capture", mutators=[], parameters={
        "pattern": pattern, "fill_density": 1, "event_probability": 1,
        "velocity_base": .6, "velocity_range": 0, "velocity_accent": 0,
        "gate": .8, "live_gate": .8, "role_duration": 1,
        "live_min_beats": .25, "live_max_beats": .25, "harmony_anchor": 0})


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("target", ["rhythm", "velocity", "duration"])
def test_delay_process_has_audible_history_in_every_mode(monkeypatch, mode, target):
    block = lead(mode=mode)
    block.processes = [Process("Delay", target, 1, {"delay": 1, "repeats": 1, "mode": "Replace", "decay": 1})]
    project = Project(length=8, blocks=[block])
    engine = MusicEngine(project)
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    for i in range(8):
        tick(i * .125)
    times = [t for t, message in sent if message.type == "note_on"]
    assert times == pytest.approx([i * .125 for i in range(1, 8)])
    transport.stop()


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("role", ["MELODY", "BASS", "CHORD", "PAD"])
def test_process_created_hits_get_real_dynamics_and_duration(monkeypatch, mode, role):
    block = lead(mode=mode, pattern="0"); block.block_type = role
    block.processes = [Process("Compare", "rhythm", 1, {"threshold": 0, "operator": ">=", "true_value": 1})]
    project = Project(length=4, blocks=[block])
    engine = MusicEngine(project)
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    for i in range(4): tick(i * .125)
    notes = [message for _, message in sent if message.type == "note_on"]
    assert notes and all(message.velocity > 1 for message in notes)
    assert all(d > 0 for r, d in zip(block.outputs["rhythm"], block.outputs["duration"]) if r)
    transport.stop()


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_process_zero_and_mutator_zero_remain_closed_after_later_rhythm_shaping(monkeypatch, mode):
    block = lead(mode=mode)
    block.mutators = [Mutator("Probability", 0, "timing")]
    block.processes = [Process("Clock Divide", "rhythm", 1, {"factor": 2})]
    engine = MusicEngine(Project(length=8, blocks=[block]))
    transport, _, sent, tick = setup_transport(monkeypatch, engine.project, engine)
    for i in range(8): tick(i * .125)
    assert not any(message.type == "note_on" for _, message in sent)
    transport.stop()


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("creator", ["mutator", "process"])
def test_zero_fill_density_remains_silent_when_another_stage_creates_hits(monkeypatch, mode, creator):
    block = lead(mode=mode, pattern="0")
    block.parameters["fill_density"] = 0
    if creator == "mutator":
        block.mutators = [Mutator("Invert", 1, "rhythm")]
    else:
        block.processes = [Process("Compare", "rhythm", 1, {"threshold": 0, "true_value": 1})]
    engine = MusicEngine(Project(length=8, blocks=[block]))
    transport, _, sent, tick = setup_transport(monkeypatch, engine.project, engine)
    for i in range(8): tick(i * .125)
    assert not any(message.type == "note_on" for _, message in sent)
    transport.stop()


@pytest.mark.parametrize("coordinated", [False, True])
@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_kit_technique_changes_actual_child_midi_dynamics(monkeypatch, coordinated, mode):
    project, drum, voices, engine = kit((mode,), bars=1)
    project.length = 16
    drum.parameters["kit_coordinated"] = coordinated
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    assert engine.performance.start(drum, "crescendo", beats=16)
    for i in range(64): tick(i * .125)
    onsets = [(t, message.velocity) for t, message in sent if message.type == "note_on"]
    early = [velocity for t, velocity in onsets if t < 2]
    late = [velocity for t, velocity in onsets if t >= 6]
    assert early and late and mean(late) > mean(early) + 5
    assert {message.note for _, message in sent if message.type == "note_on"} <= {voice.midi_note for voice in voices}
    transport.stop()


def test_live_container_performance_refreshes_seq_children_and_keeps_manual_state():
    project, drum, voices, engine = kit(("SEQ", "LIVE"), bars=1)
    drum.mode = "LIVE"
    engine.generate()
    baseline = document_state(project, engine)
    engine.performance.start(drum, "crescendo", beats=8)
    engine.performance.tick(True, beat_delta=1)
    first = deepcopy(voices[0].outputs)
    engine.performance.tick(True, beat_delta=5)
    assert voices[0].outputs["velocity"] != first["velocity"]
    assert document_state(project, engine) == baseline
    assert not any(p.family == "Algorithm" for p in presets_for_entity(drum))


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("part", ["rhythm", "velocity", "duration", "density"])
def test_relation_into_drum_bus_gates_real_voice_output(monkeypatch, mode, part):
    project, drum, voices, engine = kit((mode,), bars=1)
    source = lead(2, mode="SEQ", pattern="0")
    project.blocks.append(source)
    project.relations = [Relation(2, "rhythm", drum.id, part, "Copy", 1, id=1)]
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    for i in range(16): tick(i * .125)
    assert not any(message.type == "note_on" and message.note in {voice.midi_note for voice in voices} for _, message in sent)
    transport.stop()


@pytest.mark.parametrize("source_mode,target_mode", [("LIVE", "SEQ"), ("SEQ", "LIVE"), ("LIVE", "LIVE")])
def test_mixed_mode_relation_reads_the_current_attempt_independent_of_project_order(monkeypatch, source_mode, target_mode):
    target = lead(1, target_mode)
    source = lead(2, source_mode, "1,0")
    source.algorithm = "Euclidean"
    source.parameters.update(euclidean_steps=2, pulses=1)
    source.muted = True  # generator still drives the relation
    project = Project(length=8, blocks=[target, source], relations=[Relation(2, "rhythm", 1, "rhythm", "Follow", 1, id=2)])
    engine = MusicEngine(project)
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    for i in range(8): tick(i * .125)
    times = [t for t, message in sent if message.type == "note_on"]
    assert times == pytest.approx([0, .25, .5, .75])
    transport.stop()


def test_scoped_reset_preserves_other_rng_technique_and_feedback():
    first, second = lead(1, "LIVE"), lead(2, "LIVE")
    engine = MusicEngine(Project(blocks=[first, second]))
    engine.live_event(first); engine.live_event(second)
    engine.performance.start(second, "crescendo", beats=16)
    active = engine.performance.active[second.id]
    state = deepcopy(engine.live_state[second.id]); rng = engine.live_rng[second.id].getstate()
    engine.relation_runtime.history[second.id].append({"rhythm": [1]})
    engine.reset_live(first)
    assert engine.live_state[second.id] == state and engine.live_rng[second.id].getstate() == rng
    assert engine.performance.active[second.id] is active
    assert list(engine.relation_runtime.history[second.id]) == [{"rhythm": [1]}]


@pytest.mark.parametrize("entry", ["kit", "inspector", "card", "algorithm"])
def test_ui_mode_or_algorithm_edit_leaves_other_performance_running(inspector, entry):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = inspector
    melody.mode = "LIVE"
    win.engine.live_event(melody)
    win.engine.performance.start(melody, "crescendo", beats=32)
    active = win.engine.performance.active[melody.id]
    previous = deepcopy(win.engine.live_state[melody.id])
    if entry == "kit":
        panel = win.drum_kit_layout.itemAt(0).widget()
        panel._changed(drum.drum_voices[0], "mode", "LIVE")
    elif entry == "inspector":
        win._set_mode(drum.drum_voices[0], "LIVE")
    elif entry == "card":
        win._card_mode_changed(drum.id, "LIVE")
    else:
        win._set_algorithm(drum.drum_voices[0], "Random Walk")
    QTest.qWait(50)
    assert win.engine.performance.active[melody.id] is active
    assert win.engine.live_state[melody.id] == previous
    if entry == "card": assert all(voice.mode == "LIVE" for voice in drum.drum_voices)
    assert not errors


def test_integrated_project_roundtrip_keeps_chains_relations_macros_and_manual_values(tmp_path):
    project, drum, voices, engine = kit(("SEQ", "LIVE"), bars=1)
    melody = lead()
    melody.mutators = [Mutator("Mirror", 1, "pitch")]
    melody.processes = [Process("Delay", "velocity", .5, {"delay": 2, "decay": .8})]
    project.blocks.append(melody)
    project.relations = [Relation(drum.id, "rhythm", melody.id, "rhythm", "Follow", .7, id=5)]
    project.macros = [{"name": "Gate", "value": .4, "routes": [{"block_id": melody.id, "parameter": "gate", "min": .2, "max": 1}]}]
    # UI creation and loading both apply role defaults. Normalize this
    # programmatic fixture before comparing the saved document.
    from auricle_persistence import project_from_dict
    project = project_from_dict(document_state(project))
    engine = MusicEngine(project)
    melody = project.blocks[-1]
    engine.generate()
    payload = document_state(project, engine)
    path = tmp_path / "combined.json"
    save_project(project_from_dict(payload), str(path))
    restored = load_project(str(path))
    restored_engine = MusicEngine(restored); restored_engine.generate()
    assert document_state(restored, restored_engine) == payload
    assert restored.blocks[-1].outputs == melody.outputs


@pytest.mark.parametrize("algorithm", GENERATORS)
@pytest.mark.parametrize("role", BLOCK_TYPES)
@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_generator_mutator_process_relation_macro_matrix(monkeypatch, algorithm, role, mode):
    block = lead(1, mode)
    block.algorithm, block.block_type = algorithm, role
    block.mutators = [Mutator("Rotate", .25, "rhythm"), Mutator("Scale", .6, "velocity")]
    block.processes = [Process("Delay", "velocity", .3, {"delay": 2, "mix": .3, "decay": .7})]
    source = lead(2, "SEQ", "1,0,1,0")
    source.muted = True
    project = Project(length=16, blocks=[block, source], relations=[
        Relation(2, "velocity", 1, "velocity", "Mix", .3, id=7)], macros=[
        {"name": "Gate", "value": .7, "routes": [{"block_id": 1, "parameter": "gate", "min": .2, "max": 1}]}])
    engine = MusicEngine(project)
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    for i in range(32): tick(i * .125)
    notes = [message for _, message in sent if message.type == "note_on"]
    assert notes
    assert all(0 <= message.note <= 127 and 1 <= message.velocity <= 127 for message in notes)
    assert all(0 <= message.channel < 16 for message in notes)
    transport.stop()
    assert not transport.active_notes


def test_combined_ensemble_phrase_harmony_dialogue_macros_and_tempo(monkeypatch):
    from harmonic_plan import preset
    project, drum, voices, engine = kit(("SEQ", "LIVE"), bars=1)
    project.length = 16
    for bid, (role, mode) in enumerate((("BASS", "LIVE"), ("MELODY", "SEQ"), ("CHORD", "SEQ"), ("PAD", "LIVE")), 2):
        block = lead(bid, mode, "1,2,0,5")
        block.block_type = role
        block.parameters["harmonic_strength"] = 1
        block.mutators = [Mutator("Mirror", 1, "pitch"), Mutator("Scale", .6, "velocity")]
        block.processes = [Process("Delay", "velocity", .2, {"delay": 1, "mix": .2})]
        project.blocks.append(block)
    project.harmonic_plan = preset()
    project.relations = [Relation(1, "rhythm", 2, "rhythm", "Follow", .7, id=1),
                         Relation(4, "pitch", 3, "pitch", "Follow", .5, id=2),
                         Relation(3, "rhythm", 5, "rhythm", "Dialogue", 1, id=3,
                                  parameters={"call_bars": 1, "response_bars": 1})]
    project.macros = [{"name": "Kit", "value": .85, "routes": [
        {"block_id": 1, "parameter": "kit_density", "min": .6, "max": 1}]}]
    engine = MusicEngine(project)
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    engine.performance.start_phrase(project, "opening_bloom", duration_beats=16)
    heard = []
    transport.app.record_generated_event = lambda block, event: heard.append((block.id, engine.clock.position_beats, deepcopy(event)))
    for i in range(128):
        if i == 32: transport.set_tempo(90)
        if i == 64: transport.set_block_muted(3, True)
        if i == 80: transport.set_block_muted(3, False)
        tick(i * .125)
    assert len(heard) > 20
    assert any(owner < 0 for owner, _, _ in heard)
    assert any(owner == 3 for owner, _, _ in heard)
    assert any(owner == 4 for owner, _, _ in heard)
    assert all(message.type != "note_on" or (0 <= message.note <= 127 and 1 <= message.velocity <= 127) for _, message in sent)
    for owner, beat, event in heard:
        if owner == 4:
            chord = engine.harmonic_runtime.at(beat)
            block = engine.find_block(owner)
            assert all(midi_note_for(project, block, pitch) % 12 in chord["pitch_classes"] for pitch in event["pitches"])
    transport.stop()
    assert not transport.active_notes
