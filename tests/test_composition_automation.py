"""Musical-time curves, output expression and preserved source material."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from auricle_core import Block, Project, MusicEngine, Transport, ensure_drum_voices
from auricle_persistence import save_project, load_project
from composition_automation import normalize_curve, curve_value
from composition_planner import make_section, normalize_composition
from harmonic_plan import preset as harmony_preset
from parameter_sources import SourceSnapshot, feedback_value
from project_history import document_state
from test_coordinated_kit import kit


def curve(start=.1, end=.9, shape="smooth"):
    return normalize_curve({"shape": shape, "points": [[0, start], [1, end]]})


def setup(mode="SEQ", kind="MELODY", meter="4/4"):
    block = Block(1, "Lead", kind, "Pattern", mode, parameters={
        "pattern": "1,2,3,4", "fill_density": 1., "event_probability": 1.,
        "velocity_base": .6, "velocity_accent": 0., "velocity_random": 0.,
        "velocity_range": 0., "gate": .8, "role_center": 0., "role_width": 48.,
    }, mutators=[])
    section = make_section("Verse", [block], bars=2, neutral=True)
    section["blocks"] = {}
    section["transition_bars"] = 0.
    project = Project(seed=47, blocks=[block], composition={
        "enabled": True, "meter": meter, "loop": True, "sections": [section]})
    engine = MusicEngine(project)
    engine.generate()
    return engine, block, section


@pytest.mark.parametrize("shape,expected", [("linear", .3), ("smooth", .225), ("step", .1)])
def test_curve_interpolation_endpoints_and_bounds(shape, expected):
    lane = curve(shape=shape)
    assert curve_value(lane, .25) == pytest.approx(expected)
    assert curve_value(lane, -1) == .1
    assert curve_value(lane, 2) == .9
    assert all(.1 <= curve_value(lane, i / 1000) <= .9 for i in range(1001))


def test_curve_normalization_bounds_bad_points_and_is_idempotent():
    lane = normalize_curve({"shape": "bad", "points": [None, [float("nan"), .2], [0, 0],
                           [.7, 5], [.7, .8], [1, .4], ["x", 0]]})
    assert lane["shape"] == "smooth"
    assert lane["points"] == [[0., 0.], [.7, .8], [1., .4]]
    assert normalize_curve(lane) == lane
    assert len(normalize_curve({"points": [[i / 200, .5] for i in range(10000)]})["points"]) <= 66
    assert normalize_curve(None) is None


@pytest.mark.parametrize("meter,bar_beats", [("4/4", 4), ("6/8", 3), ("7/8", 3.5)])
def test_curves_share_musical_time_loop_and_final_hold(meter, bar_beats):
    engine, block, section = setup(meter=meter)
    section["macros"]["energy"] = .5
    section["macro_curves"] = {"energy": curve()}
    runtime = engine.composition_runtime
    def energy(beat):
        context = runtime.context(beat)
        return runtime.effective_macros(context["section"], engine.director.global_macro_values, context)["energy"]
    assert energy(0) == .1
    assert energy(bar_beats) == pytest.approx(.5)
    assert energy(2 * bar_beats) == .1
    engine.project.composition["loop"] = False
    assert energy(200) == .9
    section["macros"]["energy"] = None
    assert energy(100) == engine.director.global_macro_values["energy"]


def test_incoming_blend_and_loop_seam_are_continuous_and_can_follow_global():
    engine, block, first = setup()
    first.update(bars=1, transition_bars=.25)
    first["macros"]["energy"] = .2
    last = make_section("Drop", bars=1, neutral=True)
    last["transition_bars"] = .25
    last["macros"]["energy"] = .9
    engine.project.composition["sections"].append(last)
    runtime = engine.composition_runtime
    def energy(beat):
        context = runtime.context(beat)
        return runtime.effective_macros(context["section"], engine.director.global_macro_values, context)["energy"]
    assert energy(0) == .2
    assert energy(4 - 1e-5) == pytest.approx(energy(4), abs=1e-6)
    assert energy(4.5) == pytest.approx(.55)
    assert energy(5) == .9
    assert energy(8 - 1e-5) == pytest.approx(energy(8), abs=1e-6)
    assert energy(9) == .2
    last["macros"]["energy"] = None
    assert energy(4) == .2
    assert energy(5) == engine.director.global_macro_values["energy"]


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_curves_change_dispatched_velocity_and_density_without_rewriting_project(mode):
    engine, block, section = setup(mode)
    section["macros"].update(energy=.5, density=.5, variation=.5)
    section["macro_curves"] = {"energy": curve(.1, .9), "density": curve(.1, .5)}
    before = document_state(engine.project, engine)
    source = deepcopy(block.outputs)
    transport = Transport(SimpleNamespace(engine=engine, project=engine.project,
                                          record_generated_event=lambda *args: None))
    accepted = []
    for start in (0., 4.):
        count = 0
        for i in range(64):
            event = {"pitch": 1., "velocity": .6, "duration": .8}
            result = transport._dispatch_event(block, event, None, .125, start + i / 64)
            count += result is not None
            if result:
                accepted.append((start, result["velocity"]))
        accepted.append(("count", count))
    assert accepted[-1][1] > next(v for k, v in accepted if k == "count")
    early = [v for k, v in accepted if k == 0.]
    late = [v for k, v in accepted if k == 4.]
    assert min(late) > max(early)
    assert document_state(engine.project, engine) == before
    assert block.outputs == source
    engine.clock.position_beats = 4
    snap = SourceSnapshot(engine)
    assert feedback_value(snap, None, "energy", snap.marks(None, "energy")).effective == pytest.approx(.5)


def test_expression_changes_gate_and_metric_accent_with_neutral_defaults():
    engine, block, section = setup()
    event = {"pitch": 1., "velocity": .6, "duration": .8}
    assert engine.apply_composition_event(block, event.copy(), 0, gate_checked=True) == event
    section["blocks"]["1"] = {"gate": .5, "accent": 1.}
    strong = engine.apply_composition_event(block, event.copy(), 0, gate_checked=True)
    weak = engine.apply_composition_event(block, event.copy(), .25, gate_checked=True)
    assert strong["duration"] == .4 and weak["duration"] == .4
    assert strong["velocity"] > event["velocity"] > weak["velocity"]
    snap = SourceSnapshot(engine)
    assert snap.marks(block.id, "gate")[0].source == "Composition"
    assert feedback_value(snap, block.id, "gate", snap.marks(block.id, "gate")).effective == .4


@pytest.mark.parametrize("kind", ["MELODY", "BASS", "CHORD", "PAD", "DRUM"])
def test_octave_spread_is_deterministic_preserves_chords_register_and_drum_note(kind):
    engine, block, section = setup(kind=kind)
    section["blocks"]["1"] = {"octave_spread": 1.}
    event = {"pitch": 0., "velocity": .6, "duration": .8}
    if kind in ("CHORD", "PAD"):
        event["pitches"] = [0., 4., 7.]
    a = engine.apply_composition_event(block, event.copy(), 0, gate_checked=True)
    b = engine.apply_composition_event(block, event.copy(), 0, gate_checked=True)
    assert a == b
    if kind == "DRUM":
        assert a["pitch"] == 0
    else:
        assert abs(a["pitch"]) == 12
        assert all(-24 <= note <= 24 for note in a.get("pitches", [a["pitch"]]))
        if "pitches" in a:
            assert [p - a["pitches"][0] for p in a["pitches"]] == [0, 4, 7]
    block.parameters["role_width"] = 6
    assert engine.apply_composition_event(block, event.copy(), 0, gate_checked=True)["pitch"] == 0


def test_section_harmony_multiplier_reaches_the_real_harmonic_runtime():
    engine, block, section = setup()
    engine.project.harmonic_plan = harmony_preset("C – Am – F – G")
    block.parameters["harmonic_strength"] = 1.
    section["macros"]["tension"] = .5
    section["blocks"]["1"] = {"harmony": 0.}
    event = {"pitch": 2., "velocity": .6, "duration": .8}
    free = engine.harmonize_event(block, event.copy(), 0)
    section["blocks"]["1"]["harmony"] = 1.
    anchored = engine.harmonize_event(block, event.copy(), 0)
    assert free["pitch"] == 2.
    assert anchored["pitch"] != free["pitch"]


def test_curve_expression_save_load_duplicate_and_document_history(tmp_path):
    engine, block, section = setup()
    section["macros"]["energy"] = .4
    section["macro_curves"] = {"energy": curve()}
    section["transition_bars"] = .5
    section["blocks"]["1"] = {"gate": .5, "accent": .4, "octave_spread": .3, "harmony": .7}
    path = str(tmp_path / "curves.json")
    save_project(engine.project, path)
    restored = load_project(path)
    assert restored.composition == normalize_composition(engine.project.composition)
    assert restored.composition["sections"][0]["macro_curves"]["energy"] == curve()
    assert document_state(engine.project, engine)["composition"]["sections"][0]["blocks"]["1"]["gate"] == .5


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("technique,key", [("dynamic_scatter", "velocity_random"),
                                          ("register_bloom", "role_width"), ("harmonic_resolve", "harmonic_strength")])
def test_expanded_perform_techniques_write_real_layers_and_restore_manual(mode, technique, key):
    engine, block, _ = setup(mode)
    before = deepcopy(block.parameters)
    assert engine.performance.start(block, technique, beats=8)
    engine.performance.tick(True, beat_delta=4)
    assert key in block.parameters
    assert block.parameters[key] != before.get(key)
    assert SourceSnapshot(engine).marks(block.id, key)[0].source == "Perform"
    engine.performance.stop(block.id)
    assert block.parameters == before


def test_live_dynamic_scatter_changes_actual_event_velocities():
    engine, block, _ = setup("LIVE")
    engine.project.composition["enabled"] = False
    plain = [engine.live_event(block)["velocity"] for _ in range(24)]
    engine.reset_live()
    engine.performance.start(block, "dynamic_scatter", beats=8)
    engine.performance.tick(True, beat_delta=6)
    scattered = [engine.live_event(block)["velocity"] for _ in range(24)]
    assert scattered != plain
    assert all(.05 <= value <= 1 for value in scattered)


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_kit_evolution_changes_real_plan_and_stop_restores_it(mode):
    project, drum, voices, engine = kit((mode,), bars=2)
    before = deepcopy(drum.parameters)
    original = deepcopy(engine.kit_plan(voices[0], 0).rows)
    assert engine.performance.start(drum, "kit_evolution", beats=16)
    engine.performance.tick(True, beat_delta=12)
    assert engine.kit_plan(voices[0], 0).rows != original
    assert all(engine.sequence_step_beats(voice) == .25 for voice in voices)
    engine.performance.stop(drum.id)
    assert drum.parameters == before
