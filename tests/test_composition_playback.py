"""Captured MIDI and clock boundaries for Composition playback controls."""
from copy import deepcopy

import pytest

from auricle_core import Block, MusicEngine, Project
from auricle_persistence import save_project, load_project
from composition_planner import make_section, normalize_composition
from project_history import document_state
from test_coordinated_kit import kit, setup_transport


def composition(project, ending="stop", meter="4/4", bars=1):
    first = make_section("Verse", bars=bars, neutral=True)
    first["transition_bars"] = 0
    project.composition = normalize_composition({"enabled": True, "meter": meter,
        "loop": ending == "loop", "end_action": ending if ending != "loop" else "hold", "sections": [first]})
    return first


def free(mode="SEQ"):
    block = Block(2, "Lead", "MELODY", "Pattern", mode, midi_port="capture", parameters={
        "pattern": "1,2,3", "pattern_probability": 1, "fill_density": 1,
        "event_probability": 1, "velocity_base": .6, "velocity_range": 0,
        "velocity_accent": 0, "velocity_random": 0, "gate": 1.5, "live_gate": 1.5,
        "live_min_beats": .25, "live_max_beats": .25, "role_duration": 1,
        "harmony_anchor": 0,
    }, mutators=[])
    project = Project(tempo=120, length=3, blocks=[block])
    composition(project)
    return project, block, MusicEngine(project)


@pytest.mark.parametrize("ending", ["loop", "stop", "hold"])
def test_end_action_normalizes_and_roundtrips(tmp_path, ending):
    project, block, engine = free()
    composition(project, ending)
    assert engine.composition_runtime.ending() == ending
    path = str(tmp_path / "ending.json")
    save_project(project, path)
    restored = load_project(path)
    assert restored.composition == project.composition
    assert MusicEngine(restored).composition_runtime.ending() == ending
    legacy = deepcopy(project.composition)
    legacy.pop("end_action", None)
    assert normalize_composition(legacy)["end_action"] == "hold"


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("meter,beats", [("4/4", 4), ("6/8", 3), ("7/8", 3.5)])
def test_stop_at_end_emits_no_notes_past_boundary_and_releases_owned_notes(monkeypatch, mode, meter, beats):
    project, block, engine = free(mode)
    composition(project, "stop", meter)
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine, playback_mode="composition")
    duration = beats * .5
    for i in range(int(duration * 100) + 30):
        tick(i / 100)
    assert not transport.running and not engine.clock.running
    assert engine.clock.position_beats == pytest.approx(beats)
    assert transport.active_notes == []
    onsets = [t for t, message in sent if message.type == "note_on"]
    assert onsets and all(t < duration for t in onsets)
    assert not [m for _, m in sent if m.type == "control_change"]
    # One final Note Off for each still-owned physical note, no hanging tails.
    keys = {(m.note, m.channel) for _, m in sent if m.type == "note_on"}
    for key in keys:
        events = [m.type for _, m in sent if (m.note, m.channel) == key]
        assert events[-1] == "note_off"
    event = {"pitch": 0., "velocity": .7, "duration": .8}
    assert engine.apply_composition_event(block, event, beats, gate_checked=True) is None


def test_worker_stall_at_end_clamps_clock_and_never_plays_a_catchup_burst(monkeypatch):
    project, block, engine = free()
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine, playback_mode="composition")
    tick(0)
    count = len([m for _, m in sent if m.type == "note_on"])
    tick(12)
    assert engine.clock.position_beats == 4
    assert not transport.running
    assert len([m for _, m in sent if m.type == "note_on"]) == count


@pytest.mark.parametrize("ending", ["loop", "hold"])
def test_other_end_modes_keep_playing_with_expected_context(monkeypatch, ending):
    project, block, engine = free()
    composition(project, ending)
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine, playback_mode="composition")
    for i in range(26):
        tick(i * .125)
    context = engine.composition_runtime.context(engine.clock.position_beats)
    assert transport.running and engine.clock.position_beats > 4
    assert context["cycle"] == (1 if ending == "loop" else 0)
    assert context["section_progress"] == (pytest.approx(.5625) if ending == "loop" else 1.)
    assert any(t > 2 for t, m in sent if m.type == "note_on")


def test_disabled_composition_does_not_stop_main_transport(monkeypatch):
    project, block, engine = free()
    project.composition["enabled"] = False
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine, playback_mode="composition")
    tick(3)
    assert transport.running and engine.clock.position_beats == 6


def test_start_at_section_and_seek_preserve_absolute_seq_phase(monkeypatch):
    project, block, engine = free()
    composition(project, "hold", meter="7/8", bars=2)
    second = make_section("Build", bars=2, neutral=True)
    project.composition["sections"].append(second)
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine, playback_mode="composition")
    transport.stop()
    begin = engine.composition_runtime.section_start(second["id"])
    assert begin == 7.
    transport.start(position_beats=begin, mode="composition")
    assert engine.clock.position_beats == 7.
    assert transport.step_count[block.id] == 28
    tick(0)
    assert engine.source_positions[block.id] == 28 % 3
    before = len([m for _, m in sent if m.type == "note_on"])
    transport.seek(9.1)
    assert transport.step_count[block.id] == 37
    tick(.02)
    assert len([m for _, m in sent if m.type == "note_on"]) == before
    tick(.075)
    assert len([m for _, m in sent if m.type == "note_on"]) == before + 1
    assert engine.source_positions[block.id] == 37 % 3


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_kit_seek_uses_shared_destination_grid_in_both_modes(monkeypatch, mode):
    project, drum, voices, engine = kit((mode,), bars=2)
    composition(project, "hold", bars=8)
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine, playback_mode="composition")
    tick(0)
    sent.clear()
    transport.seek(4.)
    assert all(transport._kit_schedule[voice.id]["slot"] == 16 for voice in voices)
    tick(0)
    plan = engine.kit_plan(voices[0], 4)
    expected = {v.midi_note for v in voices if plan.at(v.id, 16).allowed}
    assert {m.note for _, m in sent if m.type == "note_on"} == expected
    assert all(m.channel == 9 for _, m in sent if m.type == "note_on")


def test_seek_releases_old_notes_clears_feedback_and_preserves_perform_and_document(monkeypatch):
    project, block, engine = free()
    composition(project, "hold", bars=4)
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine, playback_mode="composition")
    tick(0)
    assert transport.active_notes
    engine.performance.start(block, "dynamic_scatter", beats=8)
    engine.performance.tick(True, beat_delta=2)
    gesture = engine.performance.active[block.id]
    before = document_state(project, engine)
    transport.seek(4)
    assert engine.performance.active[block.id] is gesture
    assert gesture.elapsed_beats == 2
    assert not transport.active_notes
    assert block._parameter_feedback_event is None
    assert document_state(project, engine) == before
    assert any(m.type == "note_off" for _, m in sent)


def test_end_stop_respects_a_tempo_edit(monkeypatch):
    project, block, engine = free()
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine, playback_mode="composition")
    tick(.5)  # beat 1
    transport.set_tempo(60)
    tick(3.49)
    assert transport.running and engine.clock.position_beats == pytest.approx(3.99)
    tick(3.5)
    assert not transport.running and engine.clock.position_beats == 4.
