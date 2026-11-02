"""Audible secondary kit roles and per-step LIVE macro retention."""
from collections import Counter, defaultdict
from copy import deepcopy

import pytest

from auricle_core import Block, MusicEngine, Process, Project, ensure_drum_voices
from coordinated_kit import KitCoordinator, METERS, voice_role
from test_coordinated_kit import setup_transport


def default_kit(mode="LIVE", **parameters):
    drum = Block(1, "Kit", "DRUM", mode=mode, midi_port="capture", midi_channel=10,
                 mutators=[], parameters={"kit_coordinated": True, "kit_phrase_bars": 1, **parameters})
    voices = ensure_drum_voices(drum)
    project = Project(length=32, tempo=120, seed=314, blocks=[drum])
    return project, drum, voices, MusicEngine(project)


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("fill", [0, 1])
def test_new_variants_emit_clap_open_hat_and_perc_as_real_midi(monkeypatch, mode, fill):
    project, drum, voices, engine = default_kit(mode, kit_fill=fill)
    original = deepcopy([v.parameters for v in voices])
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    variations = defaultdict(set)
    try:
        for variant in range(8):
            drum.parameters["kit_variant"] = variant
            engine.regenerate(drum)
            marker = len(sent)
            for i in range(16):
                tick((variant * 16 + i) * .125)
            notes = [(round(t / .125) % 16, msg.note) for t, msg in sent[marker:] if msg.type == "note_on"]
            counts = Counter(note for _, note in notes)
            for voice in voices:
                role = voice_role(voice)
                assert counts[voice.midi_note] >= (2 if role == "perc" and not fill else 1), (variant, role)
                variations[role].add(tuple(i for i, note in notes if note == voice.midi_note))
            hats = [i for i, note in notes if note in (42, 46)]
            assert len(hats) == len(set(hats))
        for role in ("clap", "open_hat", "perc"):
            assert len(variations[role]) > 1, role
        assert [v.parameters for v in voices] == original
    finally:
        transport.stop()


@pytest.mark.parametrize("meter,groups", METERS)
@pytest.mark.parametrize("style", ["straight", "half_time", "broken"])
def test_secondary_parts_survive_source_rests_and_full_one_bar_fill(meter, groups, style):
    project, drum, voices, engine = default_kit(kit_fill=1, kit_meter=meter.split(" · ")[0], kit_style=style)
    for voice in voices:
        voice.algorithm = "Pattern"
        voice.parameters["pattern"] = "0"
    for variant in range(4):
        drum.parameters["kit_variant"] = variant
        plan = engine.kit_plan(voices[0], 0)
        assert plan.rows == KitCoordinator().plan(drum, project.seed, 0).rows
        for role in ("clap", "open_hat", "perc"):
            voice = next(v for v in voices if voice_role(v) == role)
            assert any(engine.live_event(voice, beat=i * .25) for i in range(sum(groups))), (meter, style, variant, role)
        for i in range(sum(groups)):
            hats = [v for v in voices if voice_role(v) in ("closed_hat", "open_hat")]
            assert sum(plan.at(v.id, i).allowed for v in hats) <= 1


def capture_macro_output(monkeypatch, mode, density):
    project, drum, voices, engine = default_kit(mode)
    engine.director.global_macro_values["density"] = density
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    try:
        for slot in range(256):
            tick(slot * .125)
        return {(round(t / .125), msg.note) for t, msg in sent if msg.type == "note_on"}
    finally:
        transport.stop()


def test_global_density_thins_individual_live_hits_instead_of_whole_voices(monkeypatch):
    full = capture_macro_output(monkeypatch, "LIVE", .5)
    reduced = capture_macro_output(monkeypatch, "LIVE", .25)
    assert reduced < full
    assert {note for _, note in reduced} == {36, 38, 42, 46, 39, 50}
    assert reduced == capture_macro_output(monkeypatch, "SEQ", .25)
    assert reduced == capture_macro_output(monkeypatch, "LIVE", .25)


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("gate", ["mute", "voice_density", "probability", "process", "kit_density"])
def test_authored_secondary_parts_respect_explicit_output_gates(monkeypatch, mode, gate):
    project, drum, voices, engine = default_kit(mode, kit_fill=1)
    targets = [v for v in voices if voice_role(v) in ("clap", "open_hat", "perc")]
    for voice in targets:
        if gate == "mute":
            voice.muted = True
        elif gate == "voice_density":
            voice.parameters["fill_density"] = 0
        elif gate == "probability":
            voice.parameters["event_probability"] = 0
        elif gate == "process":
            voice.processes = [Process("Compare", "velocity", 1, {"threshold": 2})]
    if gate == "kit_density":
        drum.parameters["kit_density"] = 0
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    try:
        for slot in range(32):
            tick(slot * .125)
        notes = {msg.note for _, msg in sent if msg.type == "note_on"}
        assert not notes & {v.midi_note for v in targets}
        if gate != "kit_density":
            assert notes
    finally:
        transport.stop()
