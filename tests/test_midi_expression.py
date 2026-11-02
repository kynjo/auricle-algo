"""MIDI expression curves, section overrides and global clock transport."""
from types import SimpleNamespace

import mido
import pytest

from auricle_engine import MusicEngine
from auricle_model import Block, Project, ensure_drum_voices
from auricle_persistence import load_project, save_project
from auricle_transport import Transport
from composition_planner import make_section, normalize_composition
from midi_expression import (
    MidiExpressionRuntime, entity_expression_config, normalize_expression,
    normalize_midi_sync,
)


class CapturePort:
    def __init__(self):
        self.messages = []
        self.closed = False

    def send(self, message):
        self.messages.append(message.copy())

    def close(self):
        self.closed = True


def app_for(project):
    engine = MusicEngine(project)
    return SimpleNamespace(
        project=project,
        engine=engine,
        set_message=lambda *_: None,
        log_midi_message=lambda *_: None,
        record_generated_event=lambda *_: None,
    ), engine


def test_normalize_expression_clamps_values_and_keeps_unique_lane_ids():
    config = normalize_expression({"cc_lanes": [
        {"id": "same", "controller": 200, "min": 120, "max": -10,
         "rate_beats": 0, "points": [[0, -2], [1, 2]]},
        {"id": "same", "controller": 74, "enabled": True},
    ]})
    assert len(config["cc_lanes"]) == 2
    assert config["cc_lanes"][0]["controller"] == 119
    assert config["cc_lanes"][0]["min"] == 0
    assert config["cc_lanes"][0]["max"] == 120
    assert config["cc_lanes"][0]["rate_beats"] == pytest.approx(.0625)
    assert config["cc_lanes"][0]["points"] == [[0.0, 0.0], [1.0, 1.0]]
    assert config["cc_lanes"][0]["id"] != config["cc_lanes"][1]["id"]


def test_cc_lane_is_sampled_at_rate_and_does_not_duplicate_same_slot():
    runtime = MidiExpressionRuntime()
    config = normalize_expression({"cc_lanes": [{
        "id": "cutoff", "enabled": True, "controller": 74,
        "min": 10, "max": 110, "period_beats": 4, "rate_beats": .25,
        "shape": "linear", "points": [[0, 0], [1, 1]],
    }]})
    first = runtime.sample(1, config, 0)
    assert first == [{"type": "control_change", "lane_id": "cutoff", "control": 74, "value": 10}]
    assert runtime.sample(1, config, .1) == []
    assert runtime.sample(1, config, .25)[0]["value"] == 16
    assert runtime.sample(1, config, .25) == []


def test_aftertouch_sensitivity_scales_and_clamps_pressure():
    runtime = MidiExpressionRuntime()
    config = normalize_expression({"aftertouch": {
        "enabled": True, "mode": "channel", "sensitivity": 2.0,
        "rate_beats": .25, "points": [[0, .75], [1, .75]],
    }})
    messages = runtime.sample(31, config, 0.0)
    assert messages == [{"type": "aftertouch", "lane_id": "main", "value": 127}]
    assert normalize_expression({"aftertouch": {"sensitivity": -4}})["aftertouch"]["sensitivity"] == 0.0


def test_pitch_bend_and_channel_aftertouch_map_to_midi_ranges():
    runtime = MidiExpressionRuntime()
    config = normalize_expression({
        "pitch_bend": {"enabled": True, "range_semitones": 12,
                       "period_beats": 4, "rate_beats": .25,
                       "shape": "linear", "points": [[0, 0], [1, 1]]},
        "aftertouch": {"enabled": True, "mode": "channel",
                        "period_beats": 4, "rate_beats": .25,
                        "shape": "linear", "points": [[0, 0], [1, 1]]},
    })
    messages = runtime.sample(3, config, 0)
    assert next(item for item in messages if item["type"] == "pitchwheel")["pitch"] == -8192
    assert next(item for item in messages if item["type"] == "aftertouch")["value"] == 0
    messages = runtime.sample(3, config, 2)
    assert next(item for item in messages if item["type"] == "pitchwheel")["pitch"] == 0
    assert next(item for item in messages if item["type"] == "aftertouch")["value"] == 64


def test_polyphonic_aftertouch_waits_for_held_note_and_updates_new_notes():
    runtime = MidiExpressionRuntime()
    config = normalize_expression({"aftertouch": {
        "enabled": True, "mode": "polyphonic", "period_beats": 4,
        "rate_beats": .25, "shape": "linear", "points": [[0, .5], [1, .5]],
    }})
    assert runtime.sample(7, config, 0, active_notes=[]) == []
    first = runtime.sample(7, config, 0, active_notes=[60])
    assert first == [{"type": "polytouch", "lane_id": "main", "note": 60, "value": 64}]
    second = runtime.sample(7, config, .25, active_notes=[60, 64])
    assert second == [{"type": "polytouch", "lane_id": "main", "note": 64, "value": 64}]


def test_section_override_changes_pitch_bend_and_inherits_unset_cc_lanes():
    block = Block(1, "Lead", "MELODY")
    block.midi_expression = {"cc_lanes": [{"id": "base", "enabled": True, "controller": 1}]}
    section = {"midi_automation": {"1": {
        "pitch_bend": {"enabled": True, "range_semitones": 7},
    }}}
    result = entity_expression_config(block, section=section)
    assert result["cc_lanes"][0]["controller"] == 1  # omitted lanes inherit the block setting
    assert result["pitch_bend"]["enabled"] is True
    assert result["pitch_bend"]["range_semitones"] == 7


def test_parent_drum_expression_is_inherited_by_voice_and_voice_can_override():
    drum = Block(1, "Kit", "DRUM", midi_channel=10)
    voice = ensure_drum_voices(drum)[0]
    drum.midi_expression = {"cc_lanes": [{"id": "parent", "enabled": True, "controller": 1}]}
    result = entity_expression_config(voice, parent=drum)
    assert result["cc_lanes"][0]["controller"] == 1
    voice.midi_expression = {"cc_lanes": [{"id": "voice", "enabled": True, "controller": 74}]}
    result = entity_expression_config(voice, parent=drum)
    assert [lane["controller"] for lane in result["cc_lanes"]] == [74]


def test_project_roundtrip_preserves_block_voice_section_automation_and_clock(tmp_path):
    drum = Block(1, "Kit", "DRUM")
    voice = ensure_drum_voices(drum)[0]
    drum.midi_expression = {"cc_lanes": [{"controller": 1, "enabled": True}]}
    voice.midi_expression = {"pitch_bend": {"enabled": True, "range_semitones": 5}}
    section = make_section("Build", blocks=[drum], neutral=True)
    section["midi_automation"] = {str(voice.id): {"aftertouch": {"enabled": True, "mode": "polyphonic"}}}
    project = Project(blocks=[drum], composition={"enabled": True, "meter": "4/4", "loop": True,
                                                  "sections": [section]},
                      midi_sync={"clock_out": True, "transport_messages": True, "clock_port": "capture"})
    path = tmp_path / "expression.auricle.json"
    save_project(project, path)
    loaded = load_project(path)
    loaded_drum = loaded.blocks[0]
    loaded_voice = loaded_drum.drum_voices[0]
    assert loaded_drum.midi_expression["cc_lanes"][0]["controller"] == 1
    assert loaded_voice.midi_expression["pitch_bend"]["range_semitones"] == 5
    assert loaded.composition["sections"][0]["midi_automation"][str(loaded_voice.id)]["aftertouch"]["mode"] == "polyphonic"
    assert loaded.midi_sync["clock_out"] is True
    assert loaded.midi_sync["clock_port"] == "capture"


def test_transport_sends_expression_in_seq_and_live_modes():
    for mode in ("SEQ", "LIVE"):
        block = Block(1, "Lead", "MELODY", mode=mode, midi_port="capture", midi_channel=2)
        block.midi_expression = {"cc_lanes": [{"controller": 74, "enabled": True,
                                                "period_beats": 4, "rate_beats": .25,
                                                "points": [[0, .25], [1, .75]]}]}
        project = Project(blocks=[block])
        app, engine = app_for(project)
        transport = Transport(app)
        port = CapturePort()
        transport.outputs["capture"] = port
        engine.clock.position_beats = 0
        transport._tick_midi_expression(0)
        assert [message.type for message in port.messages] == ["control_change"]
        assert port.messages[0].control == 74
        assert port.messages[0].channel == 1
        assert 0 <= port.messages[0].value <= 127


def test_pitch_bend_sends_rpn_range_and_stop_returns_wheel_and_pressure_to_neutral():
    block = Block(1, "Lead", "MELODY", midi_port="capture", midi_channel=1)
    block.midi_expression = {
        "pitch_bend": {"enabled": True, "range_semitones": 12, "points": [[0, 1], [1, 1]]},
        "aftertouch": {"enabled": True, "mode": "channel", "points": [[0, 1], [1, 1]]},
    }
    project = Project(blocks=[block])
    app, engine = app_for(project)
    transport = Transport(app)
    port = CapturePort(); transport.outputs["capture"] = port
    engine.clock.position_beats = 0
    transport._tick_midi_expression(0)
    assert [m.control for m in port.messages if m.type == "control_change"] == [101, 100, 6, 38, 101, 100]
    assert any(m.type == "pitchwheel" and m.pitch == 8191 for m in port.messages)
    assert any(m.type == "aftertouch" and m.value == 127 for m in port.messages)
    transport._reset_expression()
    assert port.messages[-2].type == "pitchwheel" and port.messages[-2].pitch == 0
    assert port.messages[-1].type == "aftertouch" and port.messages[-1].value == 0


def test_midi_clock_is_one_24ppqn_stream_with_start_spp_continue_and_stop():
    project = Project(tempo=120, blocks=[Block(1, "Lead", "MELODY", midi_port="capture")],
                      midi_sync={"clock_out": True, "transport_messages": True,
                                 "song_position_pointer": True, "clock_port": "*"})
    app, _engine = app_for(project)
    transport = Transport(app)
    port = CapturePort(); transport.outputs["capture"] = port
    transport.running = True
    transport._start_midi_clock(0, now=10.0)
    assert port.messages[-1].type == "start"
    transport._tick_midi_clock(10.021)
    assert port.messages[-1].type == "clock"
    transport._seek_midi_clock(2.0, now=10.1, running=True)
    assert port.messages[-2].type == "songpos" and port.messages[-2].pos == 8
    assert port.messages[-1].type == "continue"
    transport._stop_midi_clock()
    assert port.messages[-1].type == "stop"


def test_midi_sync_defaults_off_for_legacy_projects():
    assert normalize_midi_sync({}) == {
        "clock_out": False, "transport_messages": False,
        "song_position_pointer": True, "clock_port": "*",
    }
    config = normalize_composition({"sections": [make_section()]})
    assert config["sections"][0]["midi_automation"] == {}


def test_section_automation_is_applied_only_in_composition_playback():
    block = Block(1, "Lead", "MELODY", midi_port="capture")
    block.midi_expression = {"cc_lanes": [{"controller": 1, "enabled": True,
                                            "period_beats": 4, "rate_beats": .25,
                                            "points": [[0, .2], [1, .2]]}]}
    section = make_section("Build", blocks=[block], neutral=True)
    section["midi_automation"] = {"1": {"cc_lanes": [{"controller": 74, "enabled": True,
                                                        "period_beats": 4, "rate_beats": .25,
                                                        "points": [[0, .8], [1, .8]]}]}}
    project = Project(blocks=[block], composition=normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True, "sections": [section],
    }))
    app, engine = app_for(project)
    transport = Transport(app)
    port = CapturePort(); transport.outputs["capture"] = port

    engine.composition_runtime.playback_active = False
    transport._tick_midi_expression(0)
    assert port.messages[-1].control == 1

    port.messages.clear(); transport.expression_runtime.reset()
    engine.composition_runtime.playback_active = True
    transport._tick_midi_expression(0)
    assert port.messages[-1].control == 74


def test_expression_is_available_for_every_block_role_and_drum_voice():
    blocks = [Block(i, role, role, mode="SEQ", midi_port="capture", midi_channel=i,
                    midi_expression={"cc_lanes": [{"controller": 11, "enabled": True}]})
              for i, role in enumerate(("BASS", "MELODY", "PAD", "CHORD"), 1)]
    drum = Block(5, "Kit", "DRUM", midi_port="capture", midi_channel=10)
    voice = ensure_drum_voices(drum)[0]
    voice.midi_expression = {"cc_lanes": [{"controller": 74, "enabled": True}]}
    blocks.append(drum)
    project = Project(blocks=blocks)
    app, engine = app_for(project)
    transport = Transport(app)
    port = CapturePort(); transport.outputs["capture"] = port
    transport._tick_midi_expression(0)
    controllers = [message.control for message in port.messages if message.type == "control_change"]
    assert controllers.count(11) == 4
    assert 74 in controllers


def test_disabling_pitch_bend_while_playing_returns_to_center():
    block = Block(1, "Lead", "MELODY", midi_port="capture")
    block.midi_expression = {"pitch_bend": {"enabled": True, "points": [[0, 1], [1, 1]]}}
    project = Project(blocks=[block])
    app, engine = app_for(project)
    transport = Transport(app)
    port = CapturePort(); transport.outputs["capture"] = port
    transport._tick_midi_expression(0)
    assert port.messages[-1].type == "pitchwheel" and port.messages[-1].pitch == 8191
    block.midi_expression = {}
    engine.clock.position_beats = .25
    transport._tick_midi_expression(.25)
    assert port.messages[-1].type == "pitchwheel" and port.messages[-1].pitch == 0


def test_midi_clock_deduplicates_multiple_names_for_same_physical_port():
    project = Project(tempo=120, blocks=[Block(1, "Lead", "MELODY")],
                      midi_sync={"clock_out": True, "transport_messages": False, "clock_port": "*"})
    app, _engine = app_for(project)
    transport = Transport(app)
    port = CapturePort()
    transport.outputs["capture-a"] = port
    transport.outputs["capture-b"] = port
    assert len(transport._clock_port_items()) == 1
    transport.running = True
    transport._start_midi_clock(0, now=10.0)
    transport._tick_midi_clock(10.021)
    assert [message.type for message in port.messages].count("clock") == 1


def test_dedicated_clock_output_is_opened_without_block_routing(monkeypatch):
    project = Project(midi_sync={"clock_out": True, "clock_port": "clock-only"})
    app, _engine = app_for(project)
    transport = Transport(app)
    port = CapturePort()
    monkeypatch.setattr("auricle_transport.get_midi_output_names", lambda: (["clock-only"], None))
    monkeypatch.setattr("auricle_transport.mido.open_output", lambda name: port)
    transport.refresh_ports()
    assert transport.outputs["clock-only"] is port


def test_disabling_cc_lane_returns_controller_to_lane_minimum():
    block = Block(1, "Lead", "MELODY", midi_port="capture")
    block.midi_expression = {"cc_lanes": [{"controller": 74, "enabled": True,
                                            "min": 12, "max": 127,
                                            "points": [[0, 1], [1, 1]]}]}
    project = Project(blocks=[block])
    app, engine = app_for(project)
    transport = Transport(app)
    port = CapturePort(); transport.outputs["capture"] = port
    transport._tick_midi_expression(0)
    assert port.messages[-1].control == 74 and port.messages[-1].value == 127
    block.midi_expression = {}
    engine.clock.position_beats = .25
    transport._tick_midi_expression(.25)
    assert port.messages[-1].control == 74 and port.messages[-1].value == 12


def test_disabled_composition_block_does_not_keep_sending_expression():
    block = Block(1, "Lead", "MELODY", midi_port="capture")
    block.midi_expression = {"pitch_bend": {"enabled": True, "points": [[0, 1], [1, 1]]}}
    section = make_section("Break", blocks=[block], neutral=True)
    section["blocks"]["1"]["enabled"] = False
    project = Project(blocks=[block], composition=normalize_composition({
        "enabled": True, "meter": "4/4", "loop": True, "sections": [section],
    }))
    app, engine = app_for(project)
    engine.composition_runtime.playback_active = True
    transport = Transport(app)
    port = CapturePort(); transport.outputs["capture"] = port
    transport._tick_midi_expression(0)
    assert port.messages == []


def test_section_timebase_spans_one_section_instead_of_repeating_loop():
    runtime = MidiExpressionRuntime()
    config = normalize_expression({"cc_lanes": [{
        "controller": 74, "enabled": True, "min": 0, "max": 100,
        "timebase": "section", "period_beats": 4, "rate_beats": .25,
        "shape": "linear", "points": [[0, 0], [1, 1]],
    }]})
    result = runtime.sample(1, config, beat=12, context={"local_beat": 2, "section_progress": .5})
    assert result[0]["value"] == 50


def test_midi_clock_emits_24_pulses_per_quarter_note():
    project = Project(tempo=120, midi_sync={"clock_out": True, "transport_messages": False})
    app, _engine = app_for(project)
    transport = Transport(app)
    port = CapturePort(); transport.outputs["capture"] = port
    transport.running = True
    transport._start_midi_clock(0, now=0.0)
    interval = 60.0 / 120.0 / 24.0
    for pulse in range(1, 25):
        transport._tick_midi_clock(pulse * interval + 1e-7)
    assert [message.type for message in port.messages].count("clock") == 24


def test_duplicate_cc_controller_lanes_are_deduplicated_deterministically():
    config = normalize_expression({"cc_lanes": [
        {"id": "first", "controller": 74, "enabled": True},
        {"id": "second", "controller": 74, "enabled": True},
        {"id": "third", "controller": 1, "enabled": True},
    ]})
    assert [lane["id"] for lane in config["cc_lanes"]] == ["first", "third"]


def test_poly_aftertouch_retriggered_note_is_repressured_in_same_rate_slot():
    runtime = MidiExpressionRuntime()
    config = normalize_expression({"aftertouch": {
        "enabled": True, "mode": "polyphonic", "points": [[0, .7], [1, .7]],
    }})
    first = runtime.sample(9, config, 0, active_notes=[60])
    assert first[0]["note"] == 60
    runtime.note_released(9, 60)
    retrigger = runtime.sample(9, config, 0, active_notes=[60])
    assert retrigger == [{"type": "polytouch", "lane_id": "main", "note": 60, "value": 89}]


def test_changing_sync_settings_while_running_stops_old_clock_before_applying_new():
    project = Project(midi_sync={"clock_out": True, "transport_messages": True, "clock_port": "*"})
    app, engine = app_for(project)
    transport = Transport(app)
    port = CapturePort(); transport.outputs["capture"] = port
    transport.running = True
    transport._start_midi_clock(0, now=1.0)
    assert port.messages[-1].type == "start"
    transport.refresh_ports = lambda: None
    transport.set_midi_sync_config({"clock_out": False, "transport_messages": False, "clock_port": "*"})
    assert port.messages[-1].type == "stop"
    assert project.midi_sync["clock_out"] is False
    assert transport._clock_next_due is None


def test_polyphonic_aftertouch_reaches_note_started_in_second_expression_pass_same_tick():
    runtime = MidiExpressionRuntime()
    config = normalize_expression({"aftertouch": {
        "enabled": True, "mode": "polyphonic", "rate_beats": .25,
        "points": [[0, .6], [1, .6]],
    }})
    # First transport pass happens before the block has emitted its Note On.
    assert runtime.sample(21, config, 1.0, active_notes=[]) == []
    # The second pass is at the same beat, but must still initialize the new note.
    messages = runtime.sample(21, config, 1.0, active_notes=[67])
    assert messages == [{"type": "polytouch", "lane_id": "main", "note": 67, "value": 76}]


def test_polyphonic_aftertouch_resets_pressure_when_a_note_leaves_the_active_set():
    runtime = MidiExpressionRuntime()
    config = normalize_expression({"aftertouch": {
        "enabled": True, "mode": "polyphonic", "rate_beats": .25,
        "points": [[0, 1], [1, 1]],
    }})
    runtime.sample(22, config, 0.0, active_notes=[60, 64])
    messages = runtime.sample(22, config, .01, active_notes=[64])
    assert messages == [{"type": "polytouch", "lane_id": "main", "note": 60, "value": 0}]


def test_tempo_change_reanchors_midi_clock_to_new_24ppqn_interval(monkeypatch):
    block = Block(1, "Lead", "MELODY", midi_port="capture")
    project = Project(tempo=120, blocks=[block], midi_sync={"clock_out": True})
    app, _engine = app_for(project)
    transport = Transport(app)
    monkeypatch.setattr("auricle_transport.time.monotonic", lambda: 100.0)
    transport.running = True
    transport._clock_next_due = 100.01
    transport.set_tempo(60)
    assert transport._clock_next_due == pytest.approx(100.0 + 60.0 / 60.0 / 24.0)


def test_midi_clock_reanchors_pulse_interval_when_tempo_changes():
    project = Project(tempo=120, midi_sync={"clock_out": True, "transport_messages": False})
    app, _engine = app_for(project)
    transport = Transport(app)
    port = CapturePort(); transport.outputs["capture"] = port
    transport.running = True
    transport._start_midi_clock(0, now=0.0)
    interval_120 = 60.0 / 120.0 / 24.0
    transport._tick_midi_clock(interval_120 + 1e-7)
    assert port.messages[-1].type == "clock"
    project.tempo = 60
    count = len(port.messages)
    transport._tick_midi_clock(interval_120 + .001)
    assert len(port.messages) == count
    interval_60 = 60.0 / 60.0 / 24.0
    transport._tick_midi_clock(interval_120 + .001 + interval_60 + 1e-7)
    assert port.messages[-1].type == "clock"
