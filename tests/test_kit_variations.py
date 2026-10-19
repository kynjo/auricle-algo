"""Meter-aware kit composition and audible per-voice / kit-bus processing."""
from copy import deepcopy
import math

import pytest

from auricle_core import Block, Mutator, Process, MusicEngine, load_project, save_project
from auricle_catalogs import MUTATORS
from coordinated_kit import CREATIVE_DEFAULTS, METERS, KitCoordinator
from test_coordinated_kit import kit, setup_transport
from test_kit_preview_lifecycle import inspector


def capture(engine, voice, count):
    if voice.mode == "SEQ":
        engine.generate_block(voice)
        return deepcopy(voice.outputs)
    result = {part: [] for part in ("rhythm", "pitch", "velocity", "duration", "density", "accent")}
    for i in range(count):
        engine.live_event(voice, beat=i * .25)
        for part in result:
            result[part].append(voice.outputs[part][0])
    return result


@pytest.mark.parametrize("meter,groups", METERS)
@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_meter_plays_complete_bars_on_the_shared_clock(monkeypatch, meter, groups, mode):
    project, drum, voices, engine = kit((mode,), pattern="0", bars=2)
    drum.parameters.update(kit_meter=meter.split(" · ")[0], **CREATIVE_DEFAULTS)
    voices[-1].parameters["kit_role"] = "tom"
    plan = engine.kit_plan(voices[0], 0)
    assert plan.length == sum(groups) * 2
    assert plan.steps_per_bar == sum(groups) and plan.groups == groups
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    for slot in range(plan.length * 2):
        tick(slot * .125)
    kick_slots = {round(t / .125) for t, msg in sent if msg.type == "note_on" and msg.note == voices[0].midi_note}
    assert set(range(0, plan.length * 2, sum(groups))) <= kick_slots
    assert all(abs(t / .125 - round(t / .125)) < 1e-6 for t, msg in sent if msg.type == "note_on")
    transport.stop()


def test_three_four_and_six_eight_have_different_grouping_and_backbeat():
    project, drum, voices, engine = kit(bars=1)
    drum.parameters["kit_meter"] = "3/4"
    a = engine.kit_plan(voices[0], 0)
    drum.parameters["kit_meter"] = "6/8"
    b = engine.kit_plan(voices[0], 0)
    assert a.length == b.length == 12
    assert {i for i in range(12) if a.at(voices[1].id, i).anchor} == {4, 8}
    assert {i for i in range(12) if b.at(voices[1].id, i).anchor} == {6}


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_tom_activity_creates_audible_non_fill_hits_from_a_silent_source(mode):
    project, drum, voices, engine = kit((mode,), pattern="0", bars=1)
    tom = voices[-1]; tom.parameters["kit_role"] = "tom"
    counts = []
    for activity in (0, .25, .5, 1):
        drum.parameters["kit_tom_activity"] = activity
        output = capture(engine, tom, 16)
        counts.append(sum(output["rhythm"]))
        assert not any(engine.kit_plan(tom, 0).at(tom.id, i).fill for i in range(16))
        assert all(v >= .3 for r, v in zip(output["rhythm"], output["velocity"]) if r)
    assert counts == [0, 1, 2, 4]


def test_complexity_syncopation_variation_and_new_variant_change_reproducible_patterns():
    project, drum, voices, engine = kit(pattern="0", bars=4)
    drum.parameters.update(kit_complexity=1, kit_tom_activity=1)
    original = engine.kit_plan(voices[0], 0)
    assert original.rows == KitCoordinator().plan(drum, project.seed, 0).rows
    assert all(row[:16] == row[16:32] == row[32:48] for row in original.rows.values())
    drum.parameters["kit_complexity"] = 0
    simple = engine.kit_plan(voices[0], 0)
    assert sum(s.force for r in simple.rows.values() for s in r) < sum(s.force for r in original.rows.values() for s in r)
    drum.parameters.update(kit_complexity=1, kit_syncopation=1)
    sync = engine.kit_plan(voices[0], 0)
    assert sync.rows != original.rows
    drum.parameters["kit_variation"] = 1
    varied = engine.kit_plan(voices[0], 0)
    assert any(row[:16] != row[16:32] for row in varied.rows.values())
    assert engine.kit_plan(voices[0], 16).rows != varied.rows
    drum.parameters["kit_variant"] = 1
    new = engine.kit_plan(voices[0], 0)
    assert new.rows != varied.rows
    assert new.rows == KitCoordinator().plan(drum, project.seed, 0).rows
    # Core beats survive every creative setting.
    for plan in (simple, sync, varied, new):
        for vid, row in original.rows.items():
            assert all(not s.anchor or plan.at(vid, i).anchor for i, s in enumerate(row))


def processing_kit(mode, coordinated=False, pattern="1,0,0,0,0,0,0,0"):
    project, drum, voices, engine = kit((mode,), pattern=pattern, bars=1)
    project.length = 8
    drum.parameters.update(kit_coordinated=coordinated, kit_protect_anchors=False)
    return project, drum, voices, engine


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("owner", ["kit", "voice"])
@pytest.mark.parametrize("kind,params,expected", [
    ("Delay", {"delay": 2, "repeats": 1, "decay": 1, "mode": "Replace"}, {2}),
    ("Memory", {"delay": 2, "feedback": 1, "mode": "Replace"}, {2}),
    ("Clock Multiply", {"factor": 2, "mode": "Hold"}, {0, 1}),
    ("Feedback", {"feedback": .5}, set(range(8))),
])
def test_temporal_processes_operate_on_a_cycle_and_activate_real_notes(mode, owner, kind, params, expected):
    project, drum, voices, engine = processing_kit(mode)
    target = drum if owner == "kit" else voices[0]
    target.processes = [Process(kind, "rhythm", 1, params)]
    output = capture(engine, voices[0], 8)
    assert {i for i, hit in enumerate(output["rhythm"]) if hit} == expected
    assert all(v > 0 for r, v in zip(output["rhythm"], output["velocity"]) if r)


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_clock_divide_has_step_phase_in_live_and_seq(mode):
    project, drum, voices, engine = processing_kit(mode, pattern="1")
    drum.processes = [Process("Clock Divide", "rhythm", 1, {"factor": 2, "duty": .5})]
    assert capture(engine, voices[0], 8)["rhythm"] == [1, 1, 0, 0, 1, 1, 0, 0]


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_rotate_moves_the_kit_beat_when_protection_is_disabled(mode):
    project, drum, voices, engine = processing_kit(mode, coordinated=True, pattern="0")
    drum.mutators = [Mutator("Rotate", 1 / 16, "rhythm")]
    output = capture(engine, voices[0], 16)
    assert {i for i, hit in enumerate(output["rhythm"]) if hit} == {7, 15}
    drum.parameters["kit_protect_anchors"] = True
    protected = capture(engine, voices[0], 16)
    assert {i for i, hit in enumerate(protected["rhythm"]) if hit} == {0, 8}


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("part", ["velocity", "duration", "density"])
def test_child_zero_process_is_not_undone_by_parent_chain(mode, part):
    project, drum, voices, engine = processing_kit(mode, pattern="1")
    voices[0].processes = [Process("Compare", part, 1, {"threshold": 2})]
    # A pitch-only parent chain must not normalize or resurrect its children.
    drum.mutators = [Mutator("Transpose", .7, "pitch")]
    assert not any(capture(engine, voices[0], 8)["rhythm"])


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_velocity_and_timing_mutators_apply_once_in_voice_then_kit_order(mode):
    project, drum, voices, engine = processing_kit(mode, pattern="1")
    voice = voices[0]
    voice.parameters.update(gate=.8, live_gate=.8)
    voice.mutators = [Mutator("Scale", 0, "velocity"), Mutator("Scale", 0, "timing")]
    drum.mutators = [Mutator("Scale", 0, "velocity"), Mutator("Scale", 0, "timing")]
    output = capture(engine, voice, 8)
    assert output["velocity"] == pytest.approx([.6 * .25 * .25] * 8)
    assert output["duration"] == pytest.approx([.8 * .25 * .25] * 8)
    voice.mutators = [Mutator("Probability", 0, "timing")]
    assert not any(capture(engine, voice, 8)["rhythm"])


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_parent_processes_change_every_voice_and_child_accent_survives(mode):
    project, drum, voices, engine = processing_kit(mode, pattern="1")
    base = capture(engine, voices[0], 8)
    drum.processes = [Process("Counter", "velocity", .15, {"length": 8})]
    for voice in voices:
        output = capture(engine, voice, 8)
        assert output["velocity"][0] < base["velocity"][0]
        assert output["velocity"][-1] > base["velocity"][-1]
    drum.processes = []
    voices[0].processes = [Process("Compare", "accent", 1, {"threshold": -1})]
    accented = capture(engine, voices[0], 8)
    assert accented["velocity"] == pytest.approx([.78] * 8)
    drum.processes = [Process("Modulo", "velocity", 1, {"modulus": 2, "mode": "Gate", "threshold": .5})]
    assert capture(engine, voices[1], 8)["rhythm"] == [0, 1, 0, 1, 0, 1, 0, 1]


@pytest.mark.parametrize("name", MUTATORS)
@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_every_rhythm_mutator_changes_a_nonuniform_drum_pattern(name, mode):
    project, drum, voices, engine = processing_kit(mode, pattern="1,0,1,0,0,1,0,0")
    before = capture(engine, voices[0], 8)["rhythm"]
    engine.reset_live()
    amount = {"Transpose": .8, "Octave": .8, "Mutate": 1., "Humanize": 1.,
              "Mirror": .65, "Probability": 0., "Scale": 0.}.get(name, .4)
    drum.mutators = [Mutator(name, amount, "rhythm")]
    output = capture(engine, voices[0], 8)
    assert len(output["rhythm"]) == 8
    assert all(math.isfinite(v) for values in output.values() for v in values)
    assert output["rhythm"] != before


def test_parent_parameter_modulation_is_sampled_once_per_slot_with_one_tick_latency(monkeypatch):
    project, drum, voices, engine = kit(pattern="1", bars=1)
    target = Block(2, "Target", "MELODY", "Probability", parameters={"probability": .25}, mutators=[])
    project.blocks.append(target)
    drum.processes = [Process("Parameter Modulation", "rhythm", 1, {
        "destination_block": 2, "destination_parameter": "probability", "min": 0., "max": 1.,
        "source_min": 0., "source_max": 1., "smoothing": 0.,
    })]
    calls = []
    original = engine.collect_parameter_modulations
    def collect(block, index=0):
        if block is drum:
            calls.append(index)
        original(block, index)
    monkeypatch.setattr(engine, "collect_parameter_modulations", collect)
    transport, _, _, tick = setup_transport(monkeypatch, project, engine)
    tick(0)
    assert target.parameters["probability"] == .25 and calls == [0]
    tick(.005)
    assert target.parameters["probability"] == 1 and calls == [0]
    tick(.125)
    assert calls == [0, 1]
    transport.stop()


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_child_mutation_precedes_parent_process_and_pitch_keeps_hardware_note(monkeypatch, mode):
    project, drum, voices, engine = processing_kit(mode, coordinated=True, pattern="1")
    voices[0].mutators = [Mutator("Scale", 0, "velocity")]
    drum.processes = [Process("Compare", "velocity", 1, {
        "threshold": .3, "true_value": .8, "false_value": .4})]
    drum.mutators = [Mutator("Transpose", 1, "pitch"), Mutator("Octave", 1, "pitch")]
    output = capture(engine, voices[0], 16)
    assert all(v == .4 for r, v in zip(output["rhythm"], output["velocity"]) if r)
    for voice in voices[1:]:
        voice.muted = True
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    for i in range(16):
        tick(i * .125)
    assert {msg.note for _, msg in sent if msg.type == "note_on"} == {voices[0].midi_note}
    transport.stop()


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_zero_voice_density_gates_new_process_hits_in_independent_mode(mode):
    project, drum, voices, engine = processing_kit(mode, pattern="0")
    voices[0].parameters["fill_density"] = 0
    drum.processes = [Process("Compare", "rhythm", 1, {"threshold": -1})]
    assert not any(capture(engine, voices[0], 8)["rhythm"])


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("part", ["velocity", "duration", "density"])
def test_keep_beat_does_not_override_a_dynamics_gate_followed_by_a_rhythm_gate(mode, part):
    project, drum, voices, engine = processing_kit(mode, coordinated=True, pattern="1")
    drum.parameters["kit_protect_anchors"] = True
    voices[0].processes = [Process("Compare", part, 1, {"threshold": 2})]
    drum.processes = [Process("Compare", "rhythm", 1, {"threshold": 2})]
    assert not any(capture(engine, voices[0], 16)["rhythm"])


def test_modulation_keeps_fractional_kit_values_and_refreshes_seq_children_of_live_parent():
    project, drum, voices, engine = processing_kit("SEQ", pattern="1")
    drum.mode = "LIVE"
    for key in (*CREATIVE_DEFAULTS, "kit_density", "kit_fill", "kit_humanize", "kit_swing"):
        drum.parameters[key] = 0  # JSON may store integral zero.
        assert engine.set_parameter(drum, key, .37)
        assert drum.parameters[key] == .37
    drum.parameters["kit_density"] = 1
    engine.generate()
    assert any(voices[0].outputs["rhythm"])
    engine.pending_parameter_modulations[(drum.id, "kit_density")] = 0
    assert engine.apply_pending_parameter_modulations() == [drum]
    assert all(not any(v.outputs["rhythm"]) for v in voices)


def test_controls_round_trip_and_grid_updates_in_place_without_deleting_the_inspector(inspector, tmp_path):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = inspector
    drum.parameters["kit_coordinated"] = True
    win._refresh_inspector()
    panel = win.drum_kit_layout.itemAt(0).widget()
    for meter, groups in KIT_METERS_FOR_TEST:
        panel.meter_selector.setCurrentIndex(panel.meter_selector.findData(meter))
        assert panel.plan_ruler.steps == sum(groups)
        assert all(len(lane.steps) == sum(groups) and lane.groups == groups for lane in panel.plan_lanes.values())
        win.transport.running = True
        try:
            for step in range(sum(groups)):
                win.engine.clock.position_beats = step * .25
                panel.update_position()
                assert panel.plan_ruler.cursor == step
                assert all(lane.cursor == step for lane in panel.plan_lanes.values())
        finally:
            win.transport.running = False
    for key in CREATIVE_DEFAULTS:
        panel.findChild(gui.ParamKnob, key).setValue(.85)
    QTest.qWait(65)
    panel.keep_beat.setChecked(False)
    panel.new_variant.click()
    assert win.drum_kit_layout.itemAt(0).widget() is panel
    assert not errors
    path = tmp_path / "kit.json"
    save_project(win.project, str(path))
    loaded = load_project(str(path)).blocks[0]
    assert loaded.parameters["kit_meter"] == "12/8"
    assert loaded.parameters["kit_variant"] == 1
    assert loaded.parameters["kit_protect_anchors"] is False
    assert all(loaded.parameters[key] == .85 for key in CREATIVE_DEFAULTS)


KIT_METERS_FOR_TEST = [(label.split(" · ")[0], groups) for label, groups in METERS]
