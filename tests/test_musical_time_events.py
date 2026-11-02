"""Shared musical-time grid and canonical event model regressions."""
from types import SimpleNamespace

import pytest

from auricle_core import Block, MusicEngine, Project, Transport
from musical_clock import MusicalClock, MusicalGrid
from musical_events import MusicalEvent


def test_grid_uses_absolute_quarter_note_beats_and_stable_boundaries():
    grid = MusicalGrid(step_beats=0.25)
    assert grid.slot_at(0.0) == 0
    assert grid.slot_at(0.2499999999, "floor") == 1
    assert grid.slot_at(0.2500000001, "floor") == 1
    assert grid.slot_at(0.251, "ceil") == 2
    assert grid.beat_at(7) == pytest.approx(1.75)
    assert grid.quantize(1.88) == pytest.approx(2.0)
    assert grid.quantize(1.88, "floor") == pytest.approx(1.75)
    assert grid.quantize(1.88, "ceil") == pytest.approx(2.0)


def test_grid_understands_compound_and_uneven_meters():
    six_eight = MusicalGrid.from_meter(6, 8, step_beats=0.25)
    seven_eight = MusicalGrid.from_meter(7, 8, step_beats=0.25)
    assert six_eight.beats_per_bar == pytest.approx(3.0)
    assert six_eight.position_at(3.5).bar_number == 2
    assert six_eight.position_at(3.5).beat_in_bar == pytest.approx(0.5)
    assert six_eight.position_at(1.0).step_in_bar == 4
    assert six_eight.steps_per_bar == pytest.approx(12)
    assert seven_eight.beats_per_bar == pytest.approx(3.5)
    assert seven_eight.position_at(3.5).bar_number == 2
    assert seven_eight.position_at(3.5).beat_in_bar == pytest.approx(0.0)


def test_grid_cycle_and_phrase_origin_share_one_conversion():
    grid = MusicalGrid(step_beats=0.25, origin_beats=1.0)
    assert grid.cycle_index(3.0, 8) == 1
    assert grid.cycle_origin(3.0, 8) == pytest.approx(3.0)
    assert grid.cycle_origin(2.99, 8) == pytest.approx(1.0)


def test_clock_converts_seconds_and_beats_and_reports_bar_position():
    clock = MusicalClock(120)
    clock.start(10.0, 120)
    assert clock.advance(10.5) == pytest.approx(1.0)
    assert clock.seconds_for_beats(2) == pytest.approx(1.0)
    assert clock.seconds_for_beats(2, 60) == pytest.approx(2.0)
    assert clock.beats_for_seconds(1, 60) == pytest.approx(1.0)
    pos = clock.musical_position((6, 8), step_beats=0.25)
    assert pos.bar_number == 1
    assert pos.beat_in_bar == pytest.approx(1.0)


def test_legacy_event_normalizes_gate_to_musical_duration_and_preserves_extras():
    event = MusicalEvent.from_mapping(
        {"pitch": 7, "velocity": 1.4, "duration": 0.5, "interval": 0.25,
         "pitches": [7, 11], "_composition_slot": 9, "harmony_remaining_beats": 1.0},
        beat=2.5, interval_beats=0.5, source_id=42, role="CHORD", channel=18, port="MIDI A",
    )
    result = event.to_mapping()
    assert result["beat"] == pytest.approx(2.5)
    assert result["interval_beats"] == pytest.approx(0.5)
    assert result["duration_beats"] == pytest.approx(0.25)
    assert result["duration"] == pytest.approx(0.5)
    assert result["velocity"] == 1.0
    assert result["pitches"] == [7.0, 11.0]
    assert result["source_id"] == 42
    assert result["role"] == "CHORD"
    assert result["channel"] == 16
    assert result["port"] == "MIDI A"
    assert result["_composition_slot"] == 9
    assert result["interval"] == 0.25
    assert result["harmony_remaining_beats"] == 1.0
    assert event.duration_seconds(120) == pytest.approx(0.125)


def test_event_recomputes_duration_after_gate_transform():
    original = MusicalEvent.from_mapping({"pitch": 0, "duration": 0.5}, interval_beats=1.0)
    transformed = original.to_mapping()
    transformed["duration"] = 0.25
    final = MusicalEvent.from_mapping(
        transformed, beat=4.0, interval_beats=1.0, recompute_duration=True
    )
    assert final.duration_beats == pytest.approx(0.25)


def test_event_from_output_streams_uses_the_same_canonical_model():
    event = MusicalEvent.from_outputs(
        {"rhythm": [1, 0], "pitch": [3, 4], "velocity": [0.7, 0.8], "duration": [0.6, 0.7]},
        0, beat=1.25, interval_beats=0.25, source_id=5, role="MELODY", composition_slot=4,
    )
    assert event is not None
    result = event.to_mapping()
    assert result["beat"] == pytest.approx(1.25)
    assert result["interval_beats"] == pytest.approx(0.25)
    assert result["duration_beats"] == pytest.approx(0.15)
    assert result["pitch"] == pytest.approx(3)
    assert result["velocity"] == pytest.approx(0.7)
    assert result["_composition_slot"] == 4
    assert MusicalEvent.from_outputs({"rhythm": [0]}, 0, beat=0, interval_beats=.25) is None


def test_transport_dispatch_adds_canonical_event_time_metadata(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("auricle_transport.time.monotonic", lambda: now[0])
    block = Block(1, "Lead", "MELODY", "Pattern", "SEQ", midi_port="capture",
                  mutators=[], parameters={"fill_density": 1, "event_probability": 1,
                                            "role_center": 0, "role_width": 48,
                                            "harmony_anchor": 0})
    project = Project(tempo=120, length=8, blocks=[block])
    engine = MusicEngine(project)
    recorded = []
    app = SimpleNamespace(project=project, engine=engine, set_message=lambda _: None,
                          record_generated_event=lambda owner, event: recorded.append(dict(event)),
                          log_midi_message=lambda *_: None)
    transport = Transport(app)
    result = transport._dispatch_event(
        block, {"pitch": 2, "velocity": .8, "duration": .5}, None,
        interval=.25, beat=1.5,
    )
    assert result is not None
    assert result["beat"] == pytest.approx(1.5)
    # 0.25 seconds at 120 BPM = 0.5 beats; gate .5 = .25 beats.
    assert result["duration_beats"] == pytest.approx(.25)
    assert result["source_id"] == block.id
    assert result["role"] == "MELODY"
    assert recorded[0]["duration_beats"] == pytest.approx(.25)


def test_live_generator_emits_canonical_musical_time_fields():
    block = Block(7, "Live lead", "MELODY", "Pattern", "LIVE", mutators=[],
                  parameters={"pattern": "1", "fill_density": 1, "event_probability": 1,
                              "live_min_beats": .5, "live_max_beats": .5,
                              "live_gate": .5, "role_center": 0, "role_width": 48,
                              "harmony_anchor": 0})
    project = Project(tempo=120, length=8, blocks=[block])
    engine = MusicEngine(project)
    event = engine.live_event(block, beat=2.0)
    assert event is not None
    assert event["beat"] == pytest.approx(2.0)
    assert event["interval_beats"] == pytest.approx(.5)
    assert event["duration_beats"] == pytest.approx(
        event["interval_beats"] * event["duration"]
    )
    assert event["source_id"] == block.id
    assert event["role"] == "MELODY"


def test_seq_transport_uses_absolute_slot_as_event_beat_not_worker_time():
    block = Block(11, "SEQ lead", "MELODY", "Pattern", "SEQ", midi_port="capture",
                  mutators=[], parameters={"pattern": "1", "fill_density": 1,
                                            "event_probability": 1, "role_center": 0,
                                            "role_width": 48, "harmony_anchor": 0})
    project = Project(tempo=120, length=8, blocks=[block])
    engine = MusicEngine(project)
    engine.generate()
    # Simulate a worker callback slightly after its scheduled beat.
    engine.clock.position_beats = 1.1
    recorded = []
    app = SimpleNamespace(project=project, engine=engine, set_message=lambda _: None,
                          record_generated_event=lambda owner, event: recorded.append(dict(event)),
                          log_midi_message=lambda *_: None)
    transport = Transport(app)
    transport.step_count[block.id] = 4
    transport.seq_index[block.id] = 0
    transport._seq_event(block, 100.1, None)
    assert recorded
    assert recorded[0]["beat"] == pytest.approx(1.0)
    assert recorded[0]["interval_beats"] == pytest.approx(.25)
