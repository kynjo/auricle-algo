"""Behavior of the four kit controls across generators, MIDI timing and UI."""
import copy
import os
import random
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from auricle_core import Block, MusicEngine, Project, Relation, Transport, ensure_drum_voices, load_project, save_project
from auricle_catalogs import GENERATORS
from auricle_drum import KIT_DEFAULTS


def kit_project(mode="SEQ", algorithm="Pattern", pattern="1", **parameters):
    drum = Block(1, "Kit", "DRUM", mode=mode, mutators=[])
    voice = ensure_drum_voices(drum)[0]
    drum.drum_voices = [voice]
    voice.mode, voice.algorithm = mode, algorithm
    voice.parameters = {"pattern": pattern, "velocity_base": .6, "velocity_accent": 0,
                        "velocity_range": 0, "live_min_beats": .4, "live_max_beats": .4,
                        "fill_density": 1.0, **parameters}
    project = Project(length=16, tempo=120, seed=314, blocks=[drum])
    return project, drum, voice, MusicEngine(project)


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("algorithm", GENERATORS)
def test_master_density_silences_every_generator_and_fills(mode, algorithm):
    project, drum, voice, engine = kit_project(mode, algorithm)
    drum.parameters.update(kit_density=0, kit_fill=1)
    if mode == "SEQ":
        engine.generate()
        assert not any(voice.outputs["rhythm"])
        assert not any(drum.outputs["rhythm"])
    else:
        assert all(engine.live_event(voice) is None for _ in range(32))
    assert not any(voice.outputs["velocity"])


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_density_is_monotonic_reproducible_and_does_not_change_voice_settings(mode):
    hit_sets = []
    for density in (0, .25, .5, .75, 1):
        project, drum, voice, engine = kit_project(mode)
        project.length = 128
        original = copy.deepcopy(voice.parameters)
        drum.parameters["kit_density"] = density
        if mode == "SEQ":
            engine.generate()
            hits = {i for i, hit in enumerate(voice.outputs["rhythm"]) if hit}
            previous = copy.deepcopy(voice.outputs)
            engine.generate()
            assert voice.outputs == previous
        else:
            events = [engine.live_event(voice) for _ in range(128)]
            hits = {i for i, event in enumerate(events) if event}
            engine.reset_live()
            assert events == [engine.live_event(voice) for _ in range(128)]
        assert voice.parameters == original
        hit_sets.append(hits)
    assert hit_sets[0] == set()
    assert hit_sets[-1] == set(range(128))
    assert all(a < b for a, b in zip(hit_sets, hit_sets[1:]))


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("cycle", [8, 16])
def test_fill_adds_only_at_end_of_cycle_and_respects_voice_density(mode, cycle):
    project, drum, voice, engine = kit_project(mode, pattern="0", structure_length=cycle)
    original = copy.deepcopy(voice.parameters)
    drum.parameters["kit_fill"] = 1
    expected = {i for i in range(16) if i % cycle >= 3 * cycle // 4}
    if mode == "SEQ":
        engine.generate()
        hits = {i for i, hit in enumerate(voice.outputs["rhythm"]) if hit}
    else:
        hits = {i for i in range(16) if engine.live_event(voice)}
    assert hits == expected
    assert voice.parameters == original
    voice.parameters["fill_density"] = 0
    engine.reset_live()
    if mode == "SEQ":
        engine.generate()
        assert not any(voice.outputs["rhythm"])
    else:
        assert all(engine.live_event(voice) is None for _ in range(16))


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_fill_zero_preserves_silence(mode):
    project, drum, voice, engine = kit_project(mode, pattern="0")
    drum.parameters["kit_fill"] = 0
    if mode == "SEQ":
        engine.generate()
        assert not any(voice.outputs["rhythm"])
    else:
        assert all(engine.live_event(voice) is None for _ in range(32))


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("algorithm, parameters", [
    ("Bresenham", {"bres_pulses": 0}),
    ("Probability", {"probability": 0}),
    ("Markov", {"markov_rest": 1}),
])
def test_fill_reaches_rhythm_and_probability_generators(mode, algorithm, parameters):
    project, drum, voice, engine = kit_project(mode, algorithm, **parameters)
    drum.parameters["kit_fill"] = 1
    if mode == "SEQ":
        engine.generate()
        hits = {i for i, hit in enumerate(voice.outputs["rhythm"]) if hit}
    else:
        hits = {i for i in range(16) if engine.live_event(voice)}
    assert hits == {12, 13, 14, 15}


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_humanize_changes_velocity_without_suppressing_hits(mode):
    project, drum, voice, engine = kit_project(mode)
    def velocities():
        engine.reset_live()
        if mode == "SEQ":
            engine.generate()
            assert all(voice.outputs["rhythm"])
            return voice.outputs["velocity"][:]
        return [engine.live_event(voice)["velocity"] for _ in range(16)]
    clean = velocities()
    drum.parameters["kit_humanize"] = 1
    varied = velocities()
    assert varied != clean
    assert varied == velocities()
    assert all(.85 * a <= b <= 1.15 * a for a, b in zip(clean, varied))
    drum.parameters["kit_humanize"] = 0
    assert velocities() == clean


def test_seq_swing_and_humanize_affect_due_times_without_grid_drift():
    project, drum, voice, engine = kit_project()
    transport = Transport(SimpleNamespace(project=project, engine=engine))
    drum.parameters["kit_swing"] = .6
    voice.parameters["timing_swing"] = .1
    assert transport._swung_time(voice, 10, 0, .2) == 10
    assert transport._swung_time(voice, 10.2, 1, .2) == pytest.approx(10.28)
    assert transport._swung_time(voice, 10.4, 2, .2) == 10.4
    drum.parameters.update(kit_humanize=1, kit_swing=1)
    voice.parameters.update(timing_swing=.5, timing_humanize=.25)
    times = [transport._swung_time(voice, i * .2, i, .2) for i in range(128)]
    assert all(a <= b for a, b in zip(times, times[1:]))
    assert all(-.05 - 1e-10 <= t - i * .2 <= .15 + 1e-10 for i, t in enumerate(times))
    assert voice.parameters["timing_swing"] == .5


@pytest.mark.parametrize("pattern", ["1", "0,1"])
def test_live_swing_counts_rests_and_keeps_pair_duration(pattern):
    project, drum, voice, engine = kit_project("LIVE", pattern=pattern)
    drum.parameters["kit_swing"] = 1
    intervals = []
    for _ in range(16):
        event = engine.live_event(voice)
        intervals.append(event["interval"] if event else engine._live_interval(voice, engine._rng_for(voice)))
    assert intervals == pytest.approx([.3, .1] * 8)
    assert sum(intervals) == pytest.approx(3.2)


def test_live_humanize_is_bounded_and_does_not_consume_generator_randomness():
    project, drum, voice, engine = kit_project("LIVE")
    drum.parameters["kit_humanize"] = 1
    rng = random.Random(42)
    previous_rng_state = rng.getstate()
    intervals = []
    for index in range(64):
        engine.live_state[voice.id] = {"events": index + 1}
        rng.setstate(previous_rng_state)
        intervals.append(engine._live_interval(voice, rng))
    assert len(set(intervals)) > 1
    assert all(.16 <= interval <= .24 for interval in intervals)
    # Boundary jitter telescopes instead of accumulating across the stream.
    assert abs(sum(intervals) - 64 * .2) <= .04
    humanized_state = rng.getstate()
    drum.parameters["kit_humanize"] = 0
    rng.setstate(previous_rng_state)
    engine._live_interval(voice, rng)
    assert rng.getstate() == humanized_state


def test_mixed_kit_generates_seq_voices_under_live_parent_and_keeps_live_phase():
    project, drum, voice, engine = kit_project("LIVE")
    live_voice = copy.deepcopy(voice)
    live_voice.id -= 1
    drum.drum_voices.append(live_voice)
    voice.mode = "SEQ"
    engine.generate()
    assert len(voice.outputs["rhythm"]) == 16
    assert engine.live_event(live_voice)
    state = copy.deepcopy(engine.live_state)
    live_outputs = copy.deepcopy(live_voice.outputs)
    drum.parameters["kit_density"] = 0
    engine.regenerate(drum)
    assert not any(voice.outputs["rhythm"])
    assert engine.live_state == state
    assert live_voice.outputs == live_outputs
    assert engine.live_event(live_voice) is None


def test_kit_density_updates_relation_source_and_does_not_affect_another_kit():
    project, drum, voice, engine = kit_project()
    other = Block(2, "Other kit", "DRUM")
    ensure_drum_voices(other)
    melody = Block(3, "Melody", "MELODY", "Pattern", parameters={"pattern": "1"}, mutators=[])
    project.blocks.extend([other, melody])
    project.relations.append(Relation(1, "rhythm", 3, "rhythm", "Copy", 1.0))
    engine.generate()
    other_before = copy.deepcopy(other.outputs)
    assert any(melody.outputs["rhythm"])
    drum.parameters["kit_density"] = 0
    engine.regenerate(drum)
    assert not any(melody.outputs["rhythm"])
    assert other.outputs == other_before


def test_kit_settings_round_trip(tmp_path):
    project, drum, voice, engine = kit_project()
    drum.parameters.update(kit_density=.43, kit_swing=.61, kit_humanize=.72, kit_fill=.89)
    path = tmp_path / "kit.json"
    save_project(project, str(path))
    restored = load_project(str(path))
    assert restored.blocks[0].parameters == drum.parameters
    engine.generate()
    MusicEngine(restored).generate()
    assert restored.blocks[0].drum_voices[0].outputs == voice.outputs


def test_kit_knobs_update_sound_without_rebuilding_editor(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    import auricle_gui as gui

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(gui, "get_midi_output_names", lambda: ([], None))
    win = gui.MainWindow()
    win.performance_timer.stop()
    win.transport_worker.stop()
    try:
        project, drum, voice, engine = kit_project()
        win._install_project(project, None, "Kit controls")
        win.selected_block_id, win.selected_drum_voice_id = drum.id, voice.id
        win._refresh_inspector()
        # Let deferred project-install/selection refreshes finish before the
        # user starts a drag; these are independent of kit knob changes.
        QTest.qWait(50)
        panel = win.drum_kit_layout.itemAt(0).widget()
        assert panel is not None
        knobs = {key: panel.findChild(gui.ParamKnob, key) for key in KIT_DEFAULTS}
        assert all(knobs.values())
        regenerations = []
        original_regenerate = win.engine.regenerate
        def regenerate(block):
            regenerations.append(block.id)
            original_regenerate(block)
        monkeypatch.setattr(win.engine, "regenerate", regenerate)
        knobs["kit_density"].setValue(0)
        knobs["kit_swing"].setValue(.8)
        knobs["kit_humanize"].setValue(.9)
        knobs["kit_fill"].setValue(.7)
        QTest.qWait(65)
        app.processEvents()
        assert drum.parameters["kit_swing"] == .8
        assert not any(voice.outputs["rhythm"])
        assert win.drum_kit_layout.itemAt(0).widget() is panel
        assert win.selected_drum_voice_id == voice.id
        assert win._dirty
        assert regenerations == [drum.id]
        knobs["kit_density"].setValue(1)
        QTest.qWait(65)
        assert any(voice.outputs["rhythm"])
    finally:
        win.hide()
        win.deleteLater()
        app.processEvents()
