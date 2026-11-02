"""Audible rhythm/clock regressions from the October algorithm audit."""
from types import SimpleNamespace

import pytest

from auricle_core import Block, MusicEngine, Project, Transport, ensure_drum_voices
from generators import euclidean
from motif_engine import Motif


def setup(mode="LIVE", algorithm="Euclidean", length=16, **parameters):
    block = Block(1, "Rhythm", "DRUM", algorithm, mode, midi_port="capture",
                  mutators=[], parameters={"pulses": 5, "fill_density": 1,
                  "event_probability": 1, "velocity_range": 0, **parameters})
    project = Project(tempo=120, length=length, seed=517, blocks=[block])
    return project, block, MusicEngine(project)


@pytest.mark.parametrize("steps", [1, 4, 7, 16, 32])
def test_euclidean_exact_counts_downbeat_spacing_and_rotation(steps):
    for pulses in range(steps + 1):
        pattern = euclidean(steps, pulses)
        assert sum(pattern) == pulses
        assert set(pattern) <= {0, 1}
        if pulses:
            assert pattern[0] == 1
            hits = [i for i, hit in enumerate(pattern) if hit]
            gaps = [b - a for a, b in zip(hits, hits[1:] + [steps])]
            assert max(gaps) - min(gaps) <= 1
        for rotation in (-1, 1, steps + 2):
            r = rotation % steps
            assert euclidean(steps, pulses, rotation) == pattern[r:] + pattern[:r]
    assert euclidean(steps, -1) == [0] * steps
    assert euclidean(steps, steps + 3) == [1] * steps
    assert euclidean(0, 4) == []


@pytest.mark.parametrize("steps", [4, 7, 16, 32])
def test_live_euclidean_matches_seq_for_every_pulse_count(steps):
    for pulses in range(steps + 1):
        _, block, engine = setup("SEQ", length=steps, euclidean_steps=steps, pulses=pulses)
        engine.generate()
        expected = block.outputs["rhythm"][:]
        block.mode = "LIVE"
        for rotation in (0, 1):
            block.parameters["euclidean_rotation"] = rotation
            engine.reset_live()
            actual = [int(engine.live_event(block) is not None) for _ in range(steps * 3)]
            assert actual == (expected[rotation:] + expected[:rotation]) * 3


@pytest.mark.parametrize("cycle,steps,rotation", [(12, 7, 3), (8, 4, 1), (16, 7, 0)])
def test_live_and_seq_match_structure_rotation_and_partial_tiling(cycle, steps, rotation):
    _, block, engine = setup("SEQ", euclidean_steps=steps, pulses=3,
                            euclidean_rotation=2, structure_length=cycle,
                            structure_rotation=rotation)
    engine.generate()
    expected = block.outputs["rhythm"][:]
    block.mode = "LIVE"
    assert [int(engine.live_event(block) is not None) for _ in range(48)] == expected * 3


def test_euclidean_zero_is_editable_and_live_technique_overrides_are_used():
    _, block, engine = setup(pulses=16)
    assert engine.parameter_catalog(block)["pulses"][1] == 0
    engine.performance.active[block.id] = SimpleNamespace(current_values={
        "euclidean_steps": 4, "pulses": 1, "euclidean_rotation": 1})
    assert [bool(engine.live_event(block)) for _ in range(8)] == [False, False, False, True] * 2
    engine.performance.active[block.id].current_values["pulses"] = 0
    assert not any(engine.live_event(block) for _ in range(16))


def test_default_kit_presets_start_kick_on_downbeat_and_snare_on_backbeats():
    drum = Block(1, "Kit", "DRUM", mode="SEQ", mutators=[])
    voices = ensure_drum_voices(drum)
    engine = MusicEngine(Project(length=16, blocks=[drum]))
    engine.generate()
    positions = {v.name: [i for i, hit in enumerate(v.outputs["rhythm"]) if hit] for v in voices}
    assert positions["KICK"] == [0, 4, 8, 12]
    assert positions["SNARE"] == positions["CLAP"] == [4, 12]
    assert positions["CLOSED HAT"] == list(range(0, 16, 2))


def intervals(engine, block, count):
    result = []
    for _ in range(count):
        event = engine.live_event(block)
        result.append(event["interval"] if event else engine._live_interval(block, engine._rng_for(block)))
    return result


@pytest.mark.parametrize("algorithm,pattern", [("Pattern", "1"), ("Pattern", "0,1"), ("Probability", "1")])
@pytest.mark.parametrize("bounds", [(.4, .4), (.03, 2.5)])
def test_live_swing_preserves_each_pair_even_with_variable_intervals_and_rests(algorithm, pattern, bounds):
    _, block, engine = setup(algorithm=algorithm, pattern=pattern,
                            live_min_beats=bounds[0], live_max_beats=bounds[1])
    straight = intervals(engine, block, 64)
    block.parameters["timing_swing"] = .5
    engine.reset_live()
    swung = intervals(engine, block, 64)
    assert all(t > 0 for t in swung)
    for i in range(0, 64, 2):
        assert swung[i] > straight[i]
        assert swung[i + 1] < straight[i + 1]
        assert sum(swung[i:i+2]) == pytest.approx(sum(straight[i:i+2]))


def test_voice_and_kit_swing_share_one_bounded_offset():
    drum = Block(1, "Kit", "DRUM", mode="LIVE", parameters={"kit_swing": 1})
    voice = ensure_drum_voices(drum)[0]
    drum.drum_voices = [voice]
    voice.algorithm = "Pattern"
    voice.parameters.update(pattern="0,1", timing_swing=.5, live_min_beats=.4, live_max_beats=.4)
    engine = MusicEngine(Project(tempo=120, blocks=[drum]))
    assert intervals(engine, voice, 16) == pytest.approx([.3, .1] * 8)


def test_humanize_stays_bounded_and_does_not_accumulate_timing_error():
    _, block, engine = setup(algorithm="Pattern", pattern="1", live_min_beats=.03, live_max_beats=2.5)
    straight = intervals(engine, block, 256)
    block.parameters.update(timing_swing=.5, timing_humanize=.25)
    engine.reset_live()
    varied = intervals(engine, block, 256)
    # Interior boundary displacements cancel. Only the first/last bounded
    # jitter remains at an even end; it cannot grow with the number of steps.
    assert abs(sum(varied) - sum(straight)) <= .25 * (straight[0] + straight[-1])
    assert all(t > 0 for t in varied)
    engine.reset_live()
    assert intervals(engine, block, 256) == varied


@pytest.mark.parametrize("pulses", [0, 1, 5, 16])
def test_euclidean_pulses_do_not_change_cycle_duration(pulses):
    _, block, engine = setup(pulses=pulses, timing_swing=.5, timing_rate=2)
    result = intervals(engine, block, 32)
    assert result == pytest.approx([.09375, .03125] * 16)
    assert sum(result) == pytest.approx(2)


@pytest.mark.parametrize("length,rate,position", [(16, 1, 0), (32, 2, 5), (7, .5, 8)])
def test_director_seq_uses_real_step_duration_and_absolute_cycle(length, rate, position):
    _, block, engine = setup("SEQ", "Pattern", length=length, pattern="1", timing_rate=rate)
    engine.director.phrase.running = True
    engine.clock.position_beats = position
    seen = []
    engine.director.rhythm_decision = lambda owner, beat: seen.append(beat) or 0
    engine.generate_block(block)
    step = .25 / rate
    origin = (position // (length * step)) * length * step
    assert seen == pytest.approx([origin + i * step for i in range(length)])
    seen.clear()
    engine.generate_block(block)
    assert seen == pytest.approx([origin + i * step for i in range(length)])


def test_director_motif_uses_authored_step_and_not_project_length_or_rate():
    project, block, engine = setup("SEQ", "Pattern", length=32, pattern="1", timing_rate=4)
    motif = Motif("drums", "Three steps", role="DRUM", notes=[0]*3, rhythm=[1]*3,
                  velocity=[.8]*3, step_beats=.75)
    engine.director.motifs.register(motif)
    block.parameters["motif_id"] = motif.id
    engine.director.phrase.running = True
    seen = []
    engine.director.rhythm_decision = lambda owner, beat: seen.append(beat) or 0
    engine.generate_block(block, motif_beat=5)
    assert seen == [4.5, 5.25, 6]


@pytest.mark.parametrize("meter", ["3/4", "6/8", "7/8"])
def test_director_kit_decisions_use_plan_origin_and_shared_quarter_beats(meter):
    drum = Block(1, "Kit", "DRUM", mode="SEQ", parameters={
        "kit_coordinated": True, "kit_meter": meter, "kit_phrase_bars": 2})
    voice = ensure_drum_voices(drum)[0]
    drum.drum_voices = [voice]
    voice.parameters.update(kit_role="kick", timing_rate=4, pattern="1")
    voice.algorithm = "Pattern"
    engine = MusicEngine(Project(length=32, blocks=[drum]))
    engine.director.phrase.running = True
    first = engine.kit_plan(voice, 0)
    start = first.length * .25
    plan = engine.kit_plan(voice, start + .5)
    seen = []
    engine.director.rhythm_decision = lambda owner, beat: seen.append(beat) or 0
    engine.generate_block(voice, motif_beat=start + .5)
    expected = [start + i * .25 for i in range(plan.length) if plan.at(voice.id, plan.start_slot + i).allowed]
    assert expected
    assert seen == pytest.approx(expected)
    assert engine._seq_director_origins[voice.id] == start


def test_director_density_decisions_match_seq_and_live_at_the_same_positions():
    _, block, engine = setup("SEQ", "Pattern", pattern="1")
    engine.director.phrase.running = True
    engine.director.density = .1
    state = engine.director.snapshot()
    engine.director.snapshot = lambda: state
    decisions = []
    for start in (0, 4, 8):
        block.mode = "SEQ"
        engine.generate_block(block, motif_beat=start)
        expected = block.outputs["rhythm"][:]
        block.mode = "LIVE"
        actual = [int(engine.live_event(block, beat=start + i * .25) is not None) for i in range(16)]
        assert actual == expected
        decisions.append(actual)
    assert any(0 in row for row in decisions)
    assert decisions[0] != decisions[1]


def transport_run(monkeypatch, mode, *, edit=None, ticks=None, algorithm="Euclidean", **parameters):
    project, block, engine = setup(mode, algorithm, **parameters)
    now, sent, errors = [100.0], [], []
    monkeypatch.setattr("auricle_transport.time.monotonic", lambda: now[0])
    app = SimpleNamespace(project=project, engine=engine, set_message=lambda _: None,
                          record_generated_event=lambda *_: None, log_midi_message=lambda *_: None)
    transport = Transport(app)
    transport.refresh_ports = lambda: None
    transport._log_error = lambda context, error: errors.append((context, str(error)))
    transport.outputs["capture"] = SimpleNamespace(send=lambda message: sent.append((now[0]-100, message)))
    transport.start()
    for t in (ticks if ticks is not None else [i / 200 for i in range(1, 800)]):
        now[0] = 100 + t
        if edit:
            edit(t, block, engine, transport)
        transport.tick()
    assert not errors
    return [(round(t, 6), msg.note) for t, msg in sent if msg.type == "note_on"], transport


@pytest.mark.parametrize("swing", [0, .5])
def test_euclidean_actual_midi_times_match_seq_and_live(monkeypatch, swing):
    seq, _ = transport_run(monkeypatch, "SEQ", timing_swing=swing)
    live, _ = transport_run(monkeypatch, "LIVE", timing_swing=swing)
    assert live == seq
    assert len(live) == 10
    assert live[0][0] == .005


def test_euclidean_clock_survives_tempo_changes_stalls_and_mode_switches(monkeypatch):
    def edit(t, block, engine, transport):
        if t == .4:
            transport.set_tempo(90)
        if t == .7:
            block.mode = "SEQ"
        if t == 1.2:
            block.mode = "LIVE"
            engine.reset_live()
    ticks = [i / 200 for i in range(1, 800) if not 1.5 < i / 200 < 2.3]
    actual, _ = transport_run(monkeypatch, "LIVE", edit=edit, ticks=ticks, timing_swing=.5)
    def tempo_only(t, block, engine, transport):
        if t == .4:
            transport.set_tempo(90)
    expected, _ = transport_run(monkeypatch, "SEQ", edit=tempo_only, ticks=ticks, timing_swing=.5)
    assert actual == expected


def test_free_live_polling_lateness_does_not_accumulate(monkeypatch):
    times = [.005, .305, .405, .705, .805, 1.105, 1.205]
    notes, transport = transport_run(monkeypatch, "LIVE", algorithm="Pattern", pattern="1",
                                    ticks=times, timing_swing=.5, live_min_beats=.4, live_max_beats=.4)
    assert [t for t, _ in notes] == times
    assert transport.next_live[1] == pytest.approx(101.5)


def test_director_seq_refreshes_decisions_on_cycle_boundary(monkeypatch):
    origins = []
    def edit(t, block, engine, transport):
        if t == .005:
            engine.director.phrase.running = True
            engine.performance.tick = lambda *args, **kwargs: None
            original = engine.generate_block
            def track(b, motif_beat=None):
                original(b, motif_beat)
                origins.append(engine._seq_director_origins[b.id])
            engine.generate_block = track
    transport_run(monkeypatch, "SEQ", edit=edit)
    assert origins.count(4) == 1
