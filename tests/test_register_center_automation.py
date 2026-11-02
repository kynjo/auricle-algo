"""Automatic register motion must preserve key/chord pitch classes and bases."""
from copy import deepcopy

import pytest

from auricle_core import Block, Project, MusicEngine, Relation, Transport, midi_note_for
from auricle_catalogs import ROLE_PROFILES
from auricle_persistence import load_project, save_project
from composition_planner import make_section, normalize_composition
from generators import scale_intervals
from harmonic_plan import preset
from music_director import PerformanceState
from parameter_sources import SourceSnapshot, feedback_value
from project_history import document_state
from test_coordinated_kit import setup_transport


def setup(mode="SEQ", role="MELODY", scale="Major", root=69):
    block = Block(1, role, role, "Pattern", mode, midi_note=60, midi_port="capture", parameters={
        "pattern": "1,2,4,5,7,9,11", "role_center": ROLE_PROFILES[role]["register_anchor"],
        "role_width": 24., "role_duration": 1., "fill_density": 1., "event_probability": 1.,
        "pattern_probability": 1., "velocity_base": .7, "velocity_range": 0., "velocity_accent": 0.,
        "gate": .8, "live_gate": .8, "live_min_beats": .25, "live_max_beats": .25,
        "harmony_anchor": 0., "harmonic_strength": 1., "transpose": 0.,
    }, mutators=[])
    section = make_section("Verse", bars=64, neutral=True)
    project = Project(tempo=120, length=16, root_note=root, scale=scale, blocks=[block], composition={
        "enabled": True, "meter": "4/4", "loop": True, "end_action": "hold", "sections": [section]})
    engine = MusicEngine(project)
    engine.generate()
    return engine, block, section


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("role", ["BASS", "MELODY", "CHORD", "PAD"])
@pytest.mark.parametrize("scale", ["Major", "Minor", "Dorian"])
def test_section_center_sweep_keeps_actual_midi_in_non_c_key(monkeypatch, mode, role, scale):
    engine, block, _ = setup(mode, role, scale)
    transport, now, sent, tick = setup_transport(monkeypatch, engine.project, engine, playback_mode="composition")
    section = engine.project.composition["sections"][0]
    source = deepcopy(block.outputs)
    for i, center in enumerate(range(-24, 25, 2)):
        section["blocks"][str(block.id)] = {"register_center": center}
        tick(i * .125)
    notes = [m.note for _, m in sent if m.type == "note_on"]
    assert notes and len(set(notes)) > 3
    allowed = {(engine.project.root_note + step) % 12 for step in scale_intervals(scale)}
    assert all(note % 12 in allowed for note in notes)
    assert block.parameters["transpose"] == 0.
    if mode == "SEQ":
        assert block.outputs == source  # section edits do not regenerate source material


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("role", ["BASS", "MELODY", "CHORD", "PAD"])
def test_harmonic_plan_and_register_sweep_retain_explicit_chord_tones(monkeypatch, mode, role):
    engine, block, _ = setup(mode, role, "Major", root=60)
    engine.project.harmonic_plan = preset("Dm7 – G7 – Cmaj7")
    transport, now, sent, tick = setup_transport(monkeypatch, engine.project, engine, playback_mode="composition")
    section = engine.project.composition["sections"][0]
    section["macros"]["tension"] = .5
    for i in range(96):
        section["blocks"]["1"] = {"register_center": -12 + (i // 16) * 4}
        tick(i * .125)
    for time, message in sent:
        if message.type == "note_on":
            chord = engine.harmonic_runtime.at(time * 2)
            assert message.note % 12 in chord["pitch_classes"]
    if role in ("CHORD", "PAD"):
        for time in sorted({time for time, m in sent if m.type == "note_on"}):
            pcs = {m.note % 12 for when, m in sent if when == time and m.type == "note_on"}
            assert pcs == set(engine.harmonic_runtime.at(time * 2)["pitch_classes"])


@pytest.mark.parametrize("role", ["BASS", "MELODY", "CHORD", "PAD"])
@pytest.mark.parametrize("technique,direction", [("register_rise", 1), ("register_fall", -1)])
def test_perform_center_gestures_are_relative_stable_and_restore_authored_values(role, technique, direction):
    engine, block, _ = setup(role=role)
    block.parameters["role_center"] = -12.
    before = deepcopy(block.parameters)
    assert engine.performance.start(block, technique, beats=8)
    engine.performance.tick(True, beat_delta=0)
    assert block.parameters["role_center"] == -12.
    engine.performance.tick(True, beat_delta=4)
    expected = -12. + direction * (6. if role == "MELODY" else 3.)
    if direction < 0:
        expected = -12. + direction * (18. if role == "MELODY" else 9.)
    assert block.parameters["role_center"] == expected
    for _ in range(6):
        engine.performance.tick(True, beat_delta=0)
    assert block.parameters["role_center"] == expected  # no moving-base drift
    assert block.parameters["transpose"] == 0.
    snap = SourceSnapshot(engine)
    assert any(mark.source == "Perform" and mark.active for mark in snap.marks(block.id, "role_center"))
    assert not snap.marks(block.id, "transpose")
    engine.performance.stop(block.id)
    assert block.parameters == before


def test_missing_authored_center_uses_role_default_and_is_removed_after_stop():
    engine, block, _ = setup(role="BASS")
    block.parameters.pop("role_center")
    engine.performance.start(block, "register_rise", beats=8)
    engine.performance.tick(True, beat_delta=0)
    assert block.parameters["role_center"] == -24.
    engine.performance.stop(block.id)
    assert "role_center" not in block.parameters


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("role", ["BASS", "MELODY", "CHORD", "PAD"])
@pytest.mark.parametrize("technique", ["register_rise", "register_fall"])
def test_perform_center_motion_keeps_actual_midi_on_the_harmonic_plan(monkeypatch, mode, role, technique):
    engine, block, _ = setup(mode, role)
    engine.project.harmonic_plan = preset("Am – F – C – G")
    transport, now, sent, tick = setup_transport(monkeypatch, engine.project, engine, playback_mode="composition")
    assert engine.performance.start(block, technique, beats=16)
    for i in range(64):
        tick(i * .125)
    notes = [(time, message.note) for time, message in sent if message.type == "note_on"]
    assert notes
    assert all(note % 12 in engine.harmonic_runtime.at(time * 2)["pitch_classes"] for time, note in notes)
    assert block.parameters["transpose"] == 0.


def test_section_perform_and_director_centers_combine_without_rewriting_manual_values():
    engine, block, section = setup()
    block.parameters["role_center"] = -12.
    section["blocks"]["1"] = {"register_center": 12.}
    engine.performance.start(block, "register_rise", beats=8)
    engine.performance.tick(True, beat_delta=4)  # -12 + 6 = -6
    engine.director.phrase.running = True
    engine.director._last_state = PerformanceState(register_shift=2.)
    expected = -6. + 12. + engine.director.role_state(block.block_type, engine.director._last_state).register_shift
    before = document_state(engine.project, engine)
    rng = {key: value.getstate() for key, value in engine.live_rng.items()}
    snapshot = SourceSnapshot(engine)
    marks = snapshot.marks(block.id, "role_center")
    value = feedback_value(snapshot, block.id, "role_center", marks)
    assert {mark.source for mark in marks} == {"Perform", "Composition"}
    assert value.manual == -12.
    assert value.effective == pytest.approx(expected)
    assert document_state(engine.project, engine) == before
    assert rng == {key: value.getstate() for key, value in engine.live_rng.items()}


@pytest.mark.parametrize("role", ["BASS", "MELODY", "CHORD", "PAD"])
def test_narrow_register_and_midi_edges_never_create_a_new_pitch_class(role):
    engine, block, section = setup(role=role)
    block.parameters["role_width"] = 6.
    for base in (0, 60, 127):
        block.midi_note = base
        for center in (-48., -11.4, .6, 36.):
            block.parameters["role_center"] = center
            for pitch in (0., 2., 4., 5., 7., 9., 11.):
                placed = engine._role_pitch(block, pitch)
                assert placed % 12 == pitch % 12
                absolute = base + engine.project.root_note % 12 + placed
                assert 0 <= absolute <= 127


def test_cached_seq_uses_the_scheduled_section_center_before_harmony(monkeypatch):
    engine, block, first = setup(role="CHORD")
    first["bars"] = 1
    second = make_section("Drop", bars=1, neutral=True)
    first["blocks"]["1"] = {"register_center": -12.}
    second["blocks"]["1"] = {"register_center": 12.}
    engine.project.composition["sections"].append(second)
    engine.project.harmonic_plan = preset("C – Am – F – G")
    transport, now, sent, tick = setup_transport(monkeypatch, engine.project, engine, playback_mode="composition")
    before = deepcopy(block.outputs)
    for i in range(32):
        tick(i * .125)
    early = [m.note for time, m in sent if time == 0. and m.type == "note_on"]
    late = [m.note for time, m in sent if time == 2. and m.type == "note_on"]
    assert early and late and min(late) > max(early)
    assert block.outputs == before
    assert {note % 12 for note in early} == {0, 4, 7}
    assert {note % 12 for note in late} == {9, 0, 4}


def test_section_center_is_persisted_and_old_chromatic_field_is_not_a_destination(tmp_path):
    engine, block, section = setup()
    section["blocks"]["1"] = {"register_center": 12., "transpose": 7}
    path = str(tmp_path / "register.json")
    save_project(engine.project, path)
    restored = load_project(path)
    settings = restored.composition["sections"][0]["blocks"]["1"]
    assert settings["register_center"] == 12.
    assert "transpose" not in settings
    assert restored.blocks[0].parameters["transpose"] == 0.


def test_section_center_does_not_enter_source_cache_and_neutral_section_restores_source_register():
    engine, block, section = setup()
    clean = deepcopy(block.outputs)
    section["blocks"]["1"] = {"register_center": 24.}
    engine.generate()
    assert block.outputs == clean
    note = clean["pitch"][0]
    raised = engine.place_register_event(block, {"pitch": note, "velocity": .7}, 0)
    assert raised["pitch"] > note
    section["blocks"]["1"]["register_center"] = 0.
    restored = engine.place_register_event(block, {"pitch": note, "velocity": .7}, 0)
    assert restored["pitch"] == note


def test_relation_transpose_feedback_excludes_automatic_register_placement():
    from types import SimpleNamespace
    engine, block, section = setup()
    source = Block(2, "Source", "MELODY", "Pattern", parameters={"pattern": "2"}, mutators=[])
    engine.project.blocks.append(source)
    engine.project.relations = [Relation(source.id, "pitch", block.id, "pitch", "Copy", 1.)]
    engine.generate()
    clean = engine._base_outputs[block.id]["pitch"][0]
    routed = block.outputs["pitch"][0]
    section["blocks"]["1"] = {"register_center": 24.}
    transport = Transport(SimpleNamespace(engine=engine, project=engine.project,
                                          record_generated_event=lambda *args: None))
    event = transport._dispatch_event(block, {"pitch": routed, "velocity": .7, "duration": .8}, None, .125, 0)
    assert event["pitch"] > routed
    snapshot = SourceSnapshot(engine)
    marks = snapshot.marks(block.id, "transpose")
    assert {mark.source for mark in marks} == {"Relations"}
    feedback = feedback_value(snapshot, block.id, "transpose", marks)
    assert feedback.effective == pytest.approx(routed - clean)
