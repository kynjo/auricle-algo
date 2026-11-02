"""Audible map/motif/interlock behavior, independent of generator/source order."""
from copy import deepcopy
import math

import pytest

from auricle_core import (Block, DrumVoice, MusicEngine, Mutator, Process, Project,
                          ensure_drum_voices, load_project, save_project)
from coordinated_kit import KitCoordinator, KitStep, METERS, voice_role
from drum_rhythm import (LINK_OPERATIONS, MAP_DEFAULTS, RhythmContext, apply_voice_links,
                         enable_musical_kit, motif_states, normalized_links)
from test_coordinated_kit import setup_transport


def musical_kit(mode="SEQ", bars=4, **parameters):
    drum = Block(1, "Musical kit", "DRUM", midi_port="capture", midi_channel=10, mutators=[])
    voices = ensure_drum_voices(drum)
    voices.append(DrumVoice(-107, 1, "Tom", midi_note=45, midi_channel=10, midi_port="capture"))
    for voice in voices:
        voice.mode, voice.algorithm = mode, "Pattern"
        voice.parameters.update(pattern="0", velocity_base=.72, velocity_range=0,
                                velocity_accent=0, fill_density=1, event_probability=1,
                                gate=.65, live_gate=.65)
    enable_musical_kit(drum)
    drum.parameters.update({"kit_phrase_bars": bars, "kit_links_enabled": False, "kit_fill": 0,
                            "kit_variation": 0, **parameters})
    project = Project(blocks=[drum], length=32, seed=314)
    return project, drum, voices, MusicEngine(project)


def hits(plan, vid):
    return {i for i, step in enumerate(plan.rows[vid]) if step.allowed}


@pytest.mark.parametrize("meter,groups", METERS)
@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_map_authors_a_complete_kit_from_silent_generators_on_every_meter(meter, groups, mode):
    project, drum, voices, engine = musical_kit(mode, kit_meter=meter.split(" · ")[0])
    plan = engine.kit_plan(voices[0], 0)
    assert plan.engine == "map" and plan.steps_per_bar == sum(groups)
    assert plan.length == len(plan.bar_states) * sum(groups)
    if mode == "SEQ":
        engine.generate()
    for voice in voices:
        output = voice.outputs["rhythm"] if mode == "SEQ" else [
            bool(engine.live_event(voice, beat=i * .25)) for i in range(plan.length)]
        assert len(output) == plan.length
        assert set(i for i, value in enumerate(output) if value) == hits(plan, voice.id)
    for base in range(0, plan.length, sum(groups)):
        assert plan.at(voices[0].id, base).allowed
    assert all(not (plan.at(voices[2].id, i).allowed and plan.at(voices[3].id, i).allowed)
               for i in range(plan.length))


def test_map_coordinates_produce_distinct_patterns_and_half_time_stays_half_time():
    project, drum, voices, engine = musical_kit(kit_motif_enabled=False, kit_complexity=.7)
    patterns = []
    for x, y in ((0, 0), (1, 0), (0, 1), (1, 1)):
        drum.parameters.update(kit_map_x=x, kit_map_y=y)
        plan = engine.kit_plan(voices[0], 0)
        patterns.append(tuple(tuple(s.allowed for s in row) for row in plan.rows.values()))
    assert len(set(patterns)) == 4
    drum.parameters.update(kit_style="half_time", kit_complexity=0, kit_motif_enabled=False)
    half = engine.kit_plan(voices[0], 0)
    for base in range(0, half.length, 16):
        assert half.at(voices[1].id, base + 8).anchor
        assert not any(half.at(voices[1].id, base + i).allowed for i in (4, 12))


def test_master_density_is_nested_and_keeps_backbone_before_ornament():
    project, drum, voices, engine = musical_kit(kit_map_x=1, kit_map_y=1, kit_complexity=1,
                                               kit_motif_enabled=False)
    observed = []
    plan = engine.kit_plan(voices[0], 0)
    for amount in (0, .1, .2, .5, .8, 1):
        drum.parameters["kit_density"] = amount; engine.generate()
        observed.append({(v.id, i) for v in voices for i, value in enumerate(v.outputs["rhythm"]) if value})
    assert not observed[0]
    assert all(a <= b for a, b in zip(observed, observed[1:]))
    anchors = {(vid, i) for vid, row in plan.rows.items() for i, step in enumerate(row) if step.anchor}
    assert anchors <= observed[2]
    assert observed[2] < observed[-1]


def test_development_has_memory_return_and_reproducible_random_access():
    project, drum, voices, engine = musical_kit(kit_motif_change=1)
    coordinator = KitCoordinator()
    plans = [coordinator.plan(drum, project.seed, phrase * 16) for phrase in range(8)]
    sequence = [state for plan in plans for state in plan.bar_states]
    assert sequence[0] == "Theme"
    assert {"Variation", "Answer", "Return"} <= set(sequence)
    assert plans[3].bar_states == ("Return",) * 4
    for index, state in enumerate(sequence[:-1]):
        if state == "Fill":
            assert sequence[index + 1] == "Return"
    for phrase in (7, 0, 4, 2, 1):
        assert KitCoordinator().plan(drum, project.seed, phrase * 16).rows == plans[phrase].rows
    # A long seek never needs playback history or an unbounded simulation.
    assert len(coordinator.plan(drum, project.seed, 10**8).bar_states) == 4
    drum.parameters["kit_motif_change"] = 0
    assert all(state == "Theme" for state in coordinator.plan(drum, project.seed, 32).bar_states)


def test_return_restores_the_theme_and_variation_changes_weak_material_only():
    project, drum, voices, engine = musical_kit(kit_motif_change=1, kit_map_x=.6,
                                               kit_map_y=.6, kit_complexity=.8)
    first = engine.kit_plan(voices[0], 0)
    returning = engine.kit_plan(voices[0], 48)
    # First bar and the Return phrase use the same map and stable ornaments.
    for vid in first.rows:
        assert first.rows[vid][:16] == returning.rows[vid][:16]
    assert any(row[:16] != row[16:32] for row in first.rows.values())


@pytest.mark.parametrize("operation", ["support", "answer", "complement", "and", "xor", "copy"])
def test_boolean_link_operations_have_explicit_semantics(operation):
    drum = Block(1, "Kit", "DRUM", mutators=[])
    voices = ensure_drum_voices(drum)
    a, b = voices[0].id, voices[-1].id
    drum.parameters.update(kit_links_enabled=True, kit_voice_links=[dict(
        source=a, destination=b, operation=operation, amount=1, delay=1)])
    source = [True, False, True, False]
    destination = [False, True, True, False]
    rows = {a: [KitStep(value, value) for value in source],
            b: [KitStep(value, value) for value in destination]}
    apply_voice_links(drum, 314, 0, rows, KitStep)
    expected = []
    for i, old in enumerate(destination):
        delayed = source[(i - 1) % 4]
        if operation == "support": value = old or delayed
        elif operation == "answer": value = old or (delayed and not source[i] and not old)
        elif operation == "complement": value = old and not delayed
        elif operation == "and": value = old and delayed
        elif operation == "xor": value = old != delayed
        else: value = delayed
        expected.append(value)
    assert [step.allowed for step in rows[b]] == expected


def test_gap_fill_only_adds_weak_offbeats_and_never_overwrites_anchors():
    drum = Block(1, "Kit", "DRUM", mutators=[])
    voices = ensure_drum_voices(drum)
    source, destination = voices[0].id, voices[-1].id
    drum.parameters.update(kit_links_enabled=True, kit_voice_links=[dict(
        source=source, destination=destination, operation="gap_fill", amount=1, probability=1)])
    rows = {source: [KitStep() for _ in range(16)], destination: [KitStep() for _ in range(16)]}
    rows[destination][5] = KitStep(True, True, .9, False, True, 1.0)
    apply_voice_links(drum, 314, 0, rows, KitStep, (4, 4, 4, 4))
    assert {i for i, step in enumerate(rows[destination]) if step.allowed} == {1, 3, 5, 7, 9, 11, 13, 15}
    assert rows[destination][5].anchor


def test_link_probability_phase_and_legacy_defaults_are_deterministic():
    drum = Block(1, "Kit", "DRUM", mutators=[])
    voices = ensure_drum_voices(drum)
    source, destination = voices[0].id, voices[-1].id
    legacy = dict(source=source, destination=destination, operation="support", amount=1, delay=0)
    drum.parameters.update(kit_links_enabled=True, kit_voice_links=[legacy])
    rows_a = {source: [KitStep(i == 0, i == 0) for i in range(8)], destination: [KitStep() for _ in range(8)]}
    rows_b = deepcopy(rows_a)
    apply_voice_links(drum, 123, 0, rows_a, KitStep)
    assert [step.allowed for step in rows_a[destination]] == [True, False, False, False, False, False, False, False]
    legacy.update(phase=2, probability=1)
    apply_voice_links(drum, 123, 0, rows_b, KitStep)
    assert [step.allowed for step in rows_b[destination]] == [False, False, True, False, False, False, False, False]
    legacy["probability"] = 0
    rows_c = deepcopy(rows_a)
    rows_c[destination] = [KitStep() for _ in range(8)]
    apply_voice_links(drum, 123, 0, rows_c, KitStep)
    assert not any(step.allowed for step in rows_c[destination])


def test_interlock_moves_collisions_to_nearest_weak_slot_and_accent_link_only_changes_expression():
    drum = Block(1, "Kit", "DRUM", mutators=[])
    voices = ensure_drum_voices(drum)
    source, destination = voices[0].id, voices[-1].id
    drum.parameters.update(kit_links_enabled=True, kit_voice_links=[dict(
        source=source, destination=destination, operation="interlock", amount=1)])
    source_row = [KitStep(i == 2, i == 2) for i in range(16)]
    destination_row = [KitStep(i == 2, i == 2, .9, False, False, .6) for i in range(16)]
    rows = {source: source_row, destination: destination_row}
    apply_voice_links(drum, 9, 0, rows, KitStep, (4, 4, 4, 4))
    assert not rows[destination][2].allowed
    assert rows[destination][3].allowed

    drum.parameters["kit_voice_links"] = [dict(source=source, destination=destination,
        operation="accent", amount=1, probability=1)]
    destination_row = [KitStep(i == 2, i == 2, .9, False, False, .6) for i in range(16)]
    original_accent = destination_row[2].accent
    rows = {source: source_row, destination: destination_row}
    apply_voice_links(drum, 9, 0, rows, KitStep, (4, 4, 4, 4))
    assert rows[destination][2].allowed
    assert rows[destination][2].accent > original_accent



def test_suggested_links_are_role_aware_and_use_separate_strength_and_probability():
    from drum_rhythm import suggested_links
    drum = Block(1, "Kit", "DRUM", mutators=[])
    voices = ensure_drum_voices(drum)
    links = suggested_links(drum)
    operations = {item["operation"] for item in links}
    assert {"answer", "gap_fill", "interlock"} <= operations
    assert all(0 < item["amount"] <= 1 and 0 < item["probability"] <= 1 for item in links)
    assert all("phase" in item and "delay" in item for item in links)
    voices[-1].muted = True
    assert all(item["source"] != voices[-1].id and item["destination"] != voices[-1].id
               for item in suggested_links(drum))


def test_map_interpolation_is_continuous_and_meter_group_aware():
    from drum_rhythm import map_scores
    middle = map_scores("kick", 12, .5, .5, (6, 6))
    left = map_scores("kick", 12, .49, .5, (6, 6))
    right = map_scores("kick", 12, .51, .5, (6, 6))
    assert len(middle) == 12
    assert max(abs(a-b) for a, b in zip(left, right)) < .08
    grouped = map_scores("kick", 14, .5, .5, (4, 4, 6))
    plain = map_scores("kick", 14, .5, .5)
    assert len(grouped) == 14 and all(0 <= value <= 1 for value in grouped)
    assert grouped[12] >= plain[12]  # secondary pulse inside the final 7/8 group


def test_links_are_order_independent_safe_for_cycles_and_preserve_anchors():
    project, drum, voices, engine = musical_kit(kit_links_enabled=True)
    kick, perc = voices[0], voices[5]
    drum.parameters["kit_voice_links"] = [
        dict(source=kick.id, destination=perc.id, operation="support", delay=1, amount=1),
        dict(source=perc.id, destination=kick.id, operation="xor", delay=2, amount=1)]
    first = engine.kit_plan(kick, 0)
    drum.drum_voices.reverse(); drum.parameters["kit_voice_links"].reverse()
    second = KitCoordinator().plan(drum, project.seed, 0)
    assert first.rows == second.rows
    assert first.at(kick.id, 0).anchor and first.at(kick.id, 8).anchor
    drum.parameters["kit_links_enabled"] = False
    assert engine.kit_plan(kick, 0).rows != first.rows


def test_links_ignore_disabled_muted_free_self_and_foreign_voices():
    project, drum, voices, engine = musical_kit()
    a, b = voices[0], voices[5]
    route = dict(source=a.id, destination=b.id, operation="copy", amount=1)
    drum.parameters["kit_voice_links"] = [route]
    assert normalized_links(drum)
    for edit in ({"enabled": False}, {"source": b.id}, {"destination": -9999},
                 {"source": []}, {"operation": []}, {"amount": 0}):
        drum.parameters["kit_voice_links"] = [{**route, **edit}]
        result = normalized_links(drum)
        assert not result or result[0][3] == 0
    drum.parameters["kit_voice_links"] = [route]
    a.muted = True; assert not normalized_links(drum)
    a.muted = False; a.parameters["kit_role"] = "free"
    assert not normalized_links(drum)


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_new_plan_respects_process_mutator_silence_and_voice_density(mode):
    project, drum, voices, engine = musical_kit(mode)
    voice = voices[0]
    for owner, kind in ((voice, "process"), (drum, "process"), (voice, "mutator"), (drum, "mutator")):
        owner.processes = [Process("Compare", "velocity", 1, {"threshold": 2, "true_value": 0, "false_value": 0})] if kind == "process" else []
        owner.mutators = [Mutator("Threshold", 1, "velocity")] if kind == "mutator" else []
        if mode == "SEQ":
            engine.generate_block(voice); assert not any(voice.outputs["rhythm"])
        else:
            assert all(engine.live_event(voice, beat=i * .25) is None for i in range(64))
        owner.processes = []; owner.mutators = []
    voice.parameters["fill_density"] = 0
    if mode == "SEQ":
        engine.generate_block(voice); assert not any(voice.outputs["rhythm"])
    else:
        assert all(engine.live_event(voice, beat=i * .25) is None for i in range(64))


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_captured_midi_follows_map_relations_and_keeps_fixed_notes(monkeypatch, mode):
    project, drum, voices, engine = musical_kit(mode, bars=1, kit_links_enabled=True)
    drum.parameters["kit_voice_links"] = [dict(source=voices[0].id, destination=voices[5].id,
                                              operation="support", delay=1, amount=1)]
    plan = engine.kit_plan(voices[0], 0)
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    for slot in range(16):
        tick(slot * .125)
    actual = {(round(t / .125), message.note) for t, message in sent if message.type == "note_on"}
    expected = {(slot, voice.midi_note) for voice in voices for slot in hits(plan, voice.id)}
    assert actual == expected
    assert all(message.channel == 9 for _, message in sent if message.type == "note_on")
    transport.stop()


def test_composition_cadence_uses_actual_section_end_and_blocks_bypasses_it():
    from composition_planner import make_section
    project, drum, voices, engine = musical_kit(kit_fill=1)
    section = make_section("Verse"); section["bars"] = 2
    project.composition = dict(enabled=True, meter="4/4", ending="loop", sections=[section])
    engine.composition_runtime.playback_active = True
    plan = engine.kit_plan(voices[0], 0)
    assert plan.context.end_slot == 32
    assert any(plan.at(v.id, i).fill for v in voices for i in range(28, 32))
    assert not any(plan.at(v.id, i).fill for v in voices for i in range(32, 64))
    engine.composition_runtime.playback_active = False
    bypass = engine.kit_plan(voices[0], 0)
    assert bypass.context == RhythmContext()
    assert any(bypass.at(v.id, i).fill for v in voices for i in range(60, 64))


@pytest.mark.parametrize("mode", ["SEQ", "LIVE", "MIXED"])
def test_composition_section_inside_a_kit_buffer_uses_the_same_plan_for_output(monkeypatch, mode):
    from composition_planner import make_section, normalize_composition
    project, drum, voices, engine = musical_kit(kit_links_enabled=True, kit_motif_change=1, kit_fill=.8)
    for index, voice in enumerate(voices):
        voice.mode = ("LIVE" if index % 2 else "SEQ") if mode == "MIXED" else mode
    project.composition = normalize_composition(dict(enabled=True, loop=True, sections=[
        make_section("Verse", bars=2, neutral=True), make_section("Chorus", bars=3, neutral=True),
        make_section("Outro", bars=1, neutral=True)]))
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine, playback_mode="composition")
    expected = set()
    for slot in range(128):
        plan = engine.drum_plan(drum, slot * .25)
        expected.update((slot, voice.midi_note) for voice in voices if plan.at(voice.id, slot).allowed)
        tick(slot * .125)
    actual = {(round(time / .125), message.note) for time, message in sent if message.type == "note_on"}
    assert actual == expected
    # Seek into a section that starts in the middle of the 64-slot buffer.
    transport.seek(9.5); count = len(sent); tick(127 * .125)
    plan = engine.drum_plan(drum, 9.5)
    assert {message.note for _, message in sent[count:] if message.type == "note_on"} == {
        voice.midi_note for voice in voices if plan.at(voice.id, 38).allowed}
    transport.stop()


def test_settings_roundtrip_new_variant_and_real_parameter_routes(tmp_path):
    project, drum, voices, engine = musical_kit(kit_links_enabled=True, kit_motif_change=1)
    original = deepcopy([v.parameters for v in voices])
    path = tmp_path / "musical-kit.json"; save_project(project, str(path))
    restored = load_project(str(path)); other = MusicEngine(restored)
    assert other.kit_plan(restored.blocks[0].drum_voices[0], 0).rows == engine.kit_plan(voices[0], 0).rows
    catalog = engine.parameter_catalog(drum)
    assert all(key in catalog and catalog[key][1:] == (0, 1) for key in MAP_DEFAULTS)
    assert "kit_voice_links" not in catalog and "kit_motif_return" not in catalog
    old = engine.kit_plan(voices[0], 0)
    assert engine.set_parameter(drum, "kit_map_y", 1)
    assert engine.kit_plan(voices[0], 0).rows != old.rows
    drum.parameters["kit_variant"] = 10
    assert engine.kit_plan(voices[0], 16).rows != old.rows
    assert [v.parameters for v in voices] == original


@pytest.mark.parametrize("bad", [None, "invalid", float("nan"), float("inf"), {}, []])
def test_corrupt_optional_controls_are_bounded_and_do_not_break_the_kit(bad):
    project, drum, voices, engine = musical_kit()
    drum.parameters.update({key: bad for key in (*MAP_DEFAULTS, "kit_variant", "kit_motif_return")})
    drum.parameters["kit_voice_links"] = bad
    plan = engine.kit_plan(voices[0], 0)
    assert all(math.isfinite(s.accent) and 0 <= s.importance <= 1 for row in plan.rows.values() for s in row)
