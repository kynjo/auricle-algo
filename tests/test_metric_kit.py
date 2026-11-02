"""Published metric examples, musical invariants and actual SEQ/LIVE output."""
import math

import pytest

from coordinated_kit import KitCoordinator, METERS
from drum_rhythm import RhythmContext
from metric_kit import (METRIC_PARAMETERS, anticipation_sources, event_probabilities,
                        indispensability, metric_accents, metric_profile, metric_weights)
from section_automation import parameter_specs
from test_drum_rhythm import musical_kit, hits
from test_coordinated_kit import setup_transport


@pytest.mark.parametrize("factors,expected", [
    ((3, 2), (5, 0, 3, 1, 4, 2)),  # Barlow, Quantification of Harmony and Metre
    ((2, 3), (5, 0, 2, 4, 1, 3)),
    ((3, 2, 2), (11, 0, 6, 3, 9, 1, 7, 4, 10, 2, 8, 5)),  # NIME Fig. 1
])
def test_published_barlow_rank_examples(factors, expected):
    assert indispensability(factors) == expected


@pytest.mark.parametrize("meter,groups", METERS)
def test_every_meter_has_unique_ranks_and_monotone_strata(meter, groups):
    profile = metric_profile(groups)
    assert sorted(profile.ranks) == list(range(sum(groups)))
    assert profile.ranks[0] == sum(groups) - 1
    for r in (0, .01, .45, .9, 1):
        weights = metric_weights(profile, r)
        assert all(math.isfinite(w) and 0 <= w <= 1 for w in weights)
        assert weights[0] == 1
        ordered = sorted(range(len(weights)), key=profile.ranks.__getitem__)
        assert all(weights[a] <= weights[b] + 1e-12 for a, b in zip(ordered, ordered[1:]))
        for m in (0, .1, .85, 1):
            probabilities = event_probabilities(weights, m)
            assert sum(probabilities) == pytest.approx(sum(weights))
            assert all(0 <= p <= 1 for p in probabilities)
        assert event_probabilities(weights, 1) == pytest.approx(weights)
        uniform = event_probabilities(weights, 0)
        assert max(uniform) == min(uniform)
    assert metric_weights(profile, 1) == (1.,) * sum(groups)


def test_compound_and_additive_grouping_are_not_flattened():
    simple = metric_profile((4, 4, 4))
    compound = metric_profile((6, 6))
    assert simple.factors == (3, 2, 2)
    assert compound.factors == (2, 3, 2)
    assert simple.ranks != compound.ranks
    odd = metric_profile((4, 4, 6))
    assert set(sorted(range(14), key=odd.ranks.__getitem__)[-3:]) == {0, 4, 8}


def test_m_controls_accent_placement_without_changing_the_amplitude_distribution():
    profile = metric_profile((4, 4, 4, 4))
    metric = metric_accents(profile, 1, 314, 300)
    flat = metric_accents(profile, 0, 314, 300)
    assert flat != metric
    assert sorted(flat) == sorted(metric)


@pytest.mark.parametrize("fragment", range(1, 9))
@pytest.mark.parametrize("_meter,groups", METERS)
def test_full_syncopation_is_bounded_and_resolves_instead_of_rotating_a_bar(fragment, _meter, groups):
    count = sum(groups)
    assert anticipation_sources(groups, 0, fragment, 42) == tuple(range(count))
    mapping = anticipation_sources(groups, 1, fragment, 42)
    assert mapping[0] == 0
    run = 0
    for source, target in enumerate(mapping):
        assert target is None or target in (source, source - 1)
        run = run + 1 if target == source - 1 else 0
        assert run <= fragment
    boundaries = tuple(sum(groups[:i]) for i in range(len(groups)))
    assert any(mapping[pulse] == pulse for pulse in boundaries[1:]) or fragment >= count - groups[-1]
    assert mapping != tuple((i - 1) % count for i in range(count))


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("meter,groups", METERS)
def test_metric_kit_is_audible_from_silent_sources_on_every_meter(mode, meter, groups):
    project, drum, voices, engine = musical_kit(mode, kit_engine="metric", kit_motif_enabled=False,
                                              kit_meter=meter.split(" · ")[0])
    plan = engine.kit_plan(voices[0], 0)
    assert plan.engine == "metric" and plan.steps_per_bar == sum(groups)
    if mode == "SEQ":
        engine.generate()
    for voice in voices:
        output = voice.outputs["rhythm"] if mode == "SEQ" else [
            bool(engine.live_event(voice, beat=i * .25)) for i in range(plan.length)]
        assert {i for i, value in enumerate(output) if value} == hits(plan, voice.id)
    assert any(step.allowed for row in plan.rows.values() for step in row)
    assert all(not (plan.at(voices[2].id, i).allowed and plan.at(voices[3].id, i).allowed)
               for i in range(plan.length))


def test_cache_seek_roster_mutes_and_free_voice_are_deterministic():
    project, drum, voices, engine = musical_kit(kit_engine="metric", kit_motif_change=1,
                                              kit_variation=.8, kit_syncopation=.8)
    coordinator = KitCoordinator()
    plans = [coordinator.plan(drum, project.seed, beat) for beat in (0, 16, 32, 80)]
    assert coordinator.plan(drum, project.seed, 80) is plans[-1]
    drum.drum_voices.reverse()
    for index in (3, 0, 2, 1):
        assert coordinator.plan(drum, project.seed, (0, 16, 32, 80)[index]).rows == plans[index].rows
    voices[0].muted = True
    assert not any(step.allowed for step in coordinator.plan(drum, project.seed, 0).rows[voices[0].id])
    voices[1].parameters["kit_role"] = "free"
    assert voices[1].id not in coordinator.plan(drum, project.seed, 0).rows


def test_each_metric_control_changes_cache_and_automation_has_native_units():
    project, drum, voices, engine = musical_kit(kit_engine="metric", kit_motif_enabled=False)
    coordinator = KitCoordinator()
    first = coordinator.plan(drum, project.seed, 0)
    for key, value in (("kit_metric_density", .95), ("kit_metric_strength", .1), ("kit_metric_fragment", 8)):
        drum.parameters[key] = value
        changed = coordinator.plan(drum, project.seed, 0)
        assert changed.token != first.token
        first = changed
    # Old JSON types cannot turn continuous controls into integer lanes or vice versa.
    drum.parameters.update(kit_metric_density=1, kit_metric_strength=0, kit_metric_fragment=3.)
    specs = parameter_specs(engine, drum)
    for key in ("kit_metric_density", "kit_metric_strength"):
        assert not specs[key].integer
        assert (specs[key].low, specs[key].high) == (0, 1)
    assert specs["kit_metric_fragment"].integer
    assert (specs["kit_metric_fragment"].low, specs["kit_metric_fragment"].high) == (1, 8)
    assert specs["kit_metric_fragment"].unit == "16ths"
    assert all(engine.parameter_catalog(drum)[key] == limits for key, limits in METRIC_PARAMETERS.items())
    assert engine.set_parameter(drum, "kit_metric_fragment", 4.8)
    assert drum.parameters["kit_metric_fragment"] == 5
    assert type(drum.parameters["kit_metric_fragment"]) is int
    assert engine.set_parameter(drum, "kit_metric_strength", .43)
    assert drum.parameters["kit_metric_strength"] == .43


def test_metric_values_survive_project_roundtrip(tmp_path):
    from auricle_core import load_project, save_project
    project, drum, voices, engine = musical_kit(kit_engine="metric", kit_metric_density=.32,
                                              kit_metric_strength=.78, kit_metric_fragment=5)
    path = tmp_path / "metric.auricle.json"
    save_project(project, str(path))
    restored = load_project(str(path))
    assert restored.blocks[0].parameters == drum.parameters
    before = KitCoordinator().plan(drum, project.seed, 16)
    after = KitCoordinator().plan(restored.blocks[0], restored.seed, 16)
    assert after.rows == before.rows


def test_metric_composition_context_reaches_the_shared_cadence():
    project, drum, voices, engine = musical_kit(kit_engine="metric", kit_motif_enabled=True, kit_fill=1)
    context = RhythmContext("section", 16, 40)
    plan = KitCoordinator().plan(drum, project.seed, 4, context)
    assert plan.context == context
    assert all(not step.fill for row in plan.rows.values() for step in row[:16])
    assert any(row[39].fill for row in plan.rows.values())


@pytest.mark.parametrize("meter", ["4/4", "7/8"])
def test_metric_plan_matches_captured_midi_with_mixed_seq_live_across_phrases(monkeypatch, meter):
    project, drum, voices, engine = musical_kit(bars=2, kit_engine="metric", kit_meter=meter,
                                              kit_motif_enabled=False, kit_variation=.6,
                                              kit_syncopation=.8, kit_fill=.3)
    for index, voice in enumerate(voices):
        voice.mode = "LIVE" if index % 2 else "SEQ"
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    expected = []
    for slot in range(112):
        plan = engine.kit_plan(voices[0], slot * .25)
        expected.extend((round(slot * .125, 5), voice.midi_note) for voice in voices
                        if plan.at(voice.id, slot).allowed)
        tick(slot * .125)
    actual = [(t, message.note) for t, message in sent if message.type == "note_on"]
    assert sorted(actual) == sorted(expected)
    assert all(message.channel == 9 for t, message in sent if message.type == "note_on")
    transport.stop()
    assert not transport.active_notes


def test_master_silence_and_variation_zero_have_their_documented_meaning():
    project, drum, voices, engine = musical_kit(kit_engine="metric", kit_motif_enabled=False,
                                              kit_variation=0, kit_fill=0)
    plan = engine.kit_plan(voices[0], 0)
    for row in plan.rows.values():
        assert row[:16] == row[16:32] == row[32:48] == row[48:64]
    drum.parameters["kit_density"] = 0
    engine.generate()
    assert all(not any(voice.outputs["rhythm"]) for voice in voices)


def test_composition_curves_apply_native_ranges_and_restore_authored_metric_values():
    from composition_planner import make_section, normalize_composition
    from parameter_sources import SourceSnapshot
    from section_automation import make_track
    project, drum, voices, engine = musical_kit(kit_engine="metric", kit_metric_density=.3,
                                              kit_metric_strength=.8, kit_metric_fragment=2)
    section = make_section("Metric section", [drum], bars=2, neutral=True)
    project.composition = normalize_composition({"enabled": True, "sections": [section]})
    engine.composition_runtime.playback_active = True
    section = project.composition["sections"][0]
    for key, low, high in (("kit_metric_density", 0, 1), ("kit_metric_strength", 0, 1),
                           ("kit_metric_fragment", 1, 8)):
        track = make_track(engine, drum, key)
        track.update(mode="curve", low=low, high=high,
                     curve={"enabled": True, "shape": "linear", "points": [[0, 0], [1, 1]]})
        section.setdefault("parameter_automation", []).append(track)
    engine.section_automation.advance(4.)
    assert drum.parameters["kit_metric_density"] == .5
    assert drum.parameters["kit_metric_strength"] == .5
    assert drum.parameters["kit_metric_fragment"] == 4
    assert type(drum.parameters["kit_metric_fragment"]) is int
    marks = SourceSnapshot(engine).marks(drum.id, "kit_metric_density")
    assert any(mark.source == "Composition" and mark.active for mark in marks)
    engine.section_automation.reset()
    assert drum.parameters["kit_metric_density"] == .3
    assert drum.parameters["kit_metric_strength"] == .8
    assert drum.parameters["kit_metric_fragment"] == 2
