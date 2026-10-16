"""v102.2 engine fixes: one regression test per reported bug."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import auricle_core as core  # noqa: E402
from auricle_core import (Block, MusicEngine, Project, Relation, Transport, apply_role_defaults,  # noqa: E402
                          load_project, midi_note_for, save_project)
from generators import SCALE_INTERVALS, quantize_interval_to_scale  # noqa: E402
from voice_leading import VoiceLeading  # noqa: E402


class App:
    def __init__(self, project, engine):
        self.project, self.engine = project, engine
    def set_message(self, *a): pass
    def log_midi_message(self, *a): pass
    def record_generated_event(self, *a): pass


class Port:
    def __init__(self): self.messages = []
    def send(self, m): self.messages.append(m)


def blk(i, name, kind, alg, mode="SEQ", **params):
    b = Block(i, name, kind, alg, mode, parameters=dict(params))
    apply_role_defaults(b)
    return b


def in_scale(project, block, scale="Major"):
    root = core.block_root(project, block)
    notes = [midi_note_for(project, block, v) for r, v in zip(block.outputs["rhythm"], block.outputs["pitch"]) if r > 0]
    return notes, [n for n in notes if (n - root) % 12 not in SCALE_INTERVALS[scale]]


# 1 Voice Smooth direction
def test_voice_smooth_zero_is_free_and_one_is_smooth():
    assert VoiceLeading(smoothness=0.0).process_sequence([0, 4, 7, 12, 2]) == [0, 4, 7, 12, 2]
    smooth = VoiceLeading(smoothness=1.0).process_sequence([0, 11, 0, 11])
    assert smooth == [0, -1, 0, -1]               # nearest octave, pitch class kept
    assert all(v == int(v) for v in VoiceLeading(smoothness=0.6).process_sequence([0, 5, 9, 2, 7]))


# 2 diatonic chords
@pytest.mark.parametrize("scale", ["Major", "Minor", "Dorian", "Harmonic Minor"])
def test_chord_voicings_stay_in_scale(scale):
    p = Project(length=32, root_note=62, scale=scale)
    c = blk(1, "C", "CHORD", "Scale Walker"); p.blocks = [c]
    e = MusicEngine(p); e.generate()
    for r, root_pitch in zip(c.outputs["rhythm"], c.outputs["pitch"]):
        if r > 0:
            for x in e._chord_pitches(c, root_pitch):
                assert (midi_note_for(p, c, x) - 62) % 12 in SCALE_INTERVALS[scale]


def test_chord_on_sixth_degree_is_minor_in_major_key():
    p = Project(root_note=60, scale="Major"); c = blk(1, "C", "CHORD", "Pattern"); p.blocks = [c]
    pitches = MusicEngine(p)._chord_pitches(c, -3.0)          # A in C major
    assert sorted(int(x) % 12 for x in pitches) == [0, 4, 9]   # A C E


# 3 chord -> melody stays in scale
def test_chord_anchor_keeps_melody_in_scale():
    p = Project(length=32, root_note=60, scale="Major")
    ch = blk(1, "C", "CHORD", "Scale Walker"); m = blk(2, "M", "MELODY", "Random Walk", harmony_anchor=.5)
    p.blocks = [ch, m]; MusicEngine(p).generate()
    notes, bad = in_scale(p, m)
    assert notes and not bad


# 4 interval quantization across the octave boundary
def test_interval_quantize_wraps_to_next_octave():
    assert quantize_interval_to_scale(11, "Major Pentatonic") == 12.0
    assert quantize_interval_to_scale(-1, "Major Pentatonic") == 0.0


# 20 key frame: every key and several algorithms send in-scale notes
@pytest.mark.parametrize("root", range(60, 72))
@pytest.mark.parametrize("alg", ["Scale Walker", "Random Walk", "Probability", "Markov", "Interval Walker"])
def test_all_keys_send_in_scale_notes(root, alg):
    p = Project(length=64, root_note=root, scale="Major")
    b = blk(1, "M", "MELODY", alg, probability=1.0); p.blocks = [b]
    MusicEngine(p).generate()
    notes, bad = in_scale(p, b)
    assert notes and not bad


def test_live_events_in_scale_for_non_c_key():
    p = Project(length=16, root_note=69, scale="Major")
    b = blk(1, "M", "MELODY", "Probability", "LIVE", probability=1.0); p.blocks = [b]
    e = MusicEngine(p); e.reset_live()
    events = [e.live_event(b) for _ in range(64)]
    notes = [midi_note_for(p, b, ev["pitch"]) for ev in events if ev]
    assert notes and all((n - 69) % 12 in SCALE_INTERVALS["Major"] for n in notes)


# 5/6 swing direction and humanize without drift
def _transport(**params):
    p = Project(tempo=120)
    s = blk(1, "S", "DRUM", "Pattern", pattern="1", **params); p.blocks = [s]
    e = MusicEngine(p); e.generate()
    return p, s, Transport(App(p, e))


def test_swing_delays_offbeats():
    p, s, t = _transport(timing_swing=0.5)
    iv = t._block_seq_interval(s)
    assert t._swung_time(s, 10.0, 0, iv) == pytest.approx(10.0)
    assert t._swung_time(s, 10.0, 1, iv) == pytest.approx(10.0 + 0.5 * iv)


def test_humanize_does_not_accumulate(monkeypatch):
    p, s, t = _transport(timing_humanize=0.25)
    t.start(); start = t.grid_due[1]; iv = t._block_seq_interval(s)
    for k in range(400):
        due = t.next_due[1]
        monkeypatch.setattr(core.time, "monotonic", lambda v=max(due, t.grid_due[1]): v)
        t.tick()
        assert abs(t.next_due[1] - t.grid_due[1]) <= 0.25 * iv + 1e-9
    assert t.grid_due[1] == pytest.approx(start + 400 * iv)


# 7 mute keeps the clock and the pattern phase
def test_mute_keeps_schedule_and_phase():
    p, s, t = _transport()
    t.running = True; t.next_due = {1: 5.0}; t.grid_due = {1: 5.0}; t.seq_index = {1: 2}
    t.set_block_muted(1, True)
    assert t.next_due == {1: 5.0}
    s.muted = True; port = Port()
    t._seq_event(s, 0.0, port)
    assert t.seq_index[1] == 3 and port.messages == []


# 8 joining blocks land on the master grid; missed steps advance the pattern
def test_missed_steps_advance_pattern_position():
    p, s, t = _transport()
    t.start(); iv = t._block_seq_interval(s); g = t.grid_due[1]
    t.seq_index[1] = 1
    t._advance_seq_clock(s, g + 5.5 * iv, iv)
    assert t.step_count[1] == 5 and t.seq_index[1] == 1 + 4


def test_block_added_during_play_joins_master_grid(monkeypatch):
    p, s, t = _transport()
    t.start(); iv = t.seq_interval
    now = t._master_due + 2.3 * iv
    monkeypatch.setattr(core.time, "monotonic", lambda: now)
    t.tick()
    b = blk(2, "B", "DRUM", "Pattern", pattern="1"); p.blocks.append(b); t.app.engine.generate()
    t.tick()
    assert t.grid_due[2] == pytest.approx(t._master_due) and t.grid_due[2] > now


# 9 relations reach LIVE events, read at the source position
def test_relation_to_live_block_is_audible():
    p = Project(length=16, root_note=60)
    b = blk(1, "B", "BASS", "Scale Walker"); m = blk(2, "M", "MELODY", "Markov", "LIVE")
    p.blocks = [b, m]; p.relations = [Relation(1, "pitch", 2, "pitch", "Copy", 1.0)]
    e = MusicEngine(p); e.generate()
    for pos in range(16):
        e.source_positions[1] = pos
        ev = e.live_event(m)
        if ev:
            assert ev["pitch"] == b.outputs["pitch"][pos]


# 10/11 pitch relations quantized; rhythm relations get real velocity
def test_rhythm_relation_hits_get_velocity_and_gate():
    p = Project(length=16)
    d = blk(1, "D", "DRUM", "Euclidean", pulses=5)
    b = blk(2, "B", "BASS", "Pattern", pattern="0", groove_follow=0.0, groove_accent=0.0)
    p.blocks = [d, b]; p.relations = [Relation(1, "rhythm", 2, "rhythm", "Copy", 1.0)]
    MusicEngine(p).generate()
    hits = [(v, du) for r, v, du in zip(b.outputs["rhythm"], b.outputs["velocity"], b.outputs["duration"]) if r > 0]
    assert len(hits) == 5 and all(v > 0.05 and du > 0 for v, du in hits)


def test_mix_pitch_relation_stays_in_scale():
    p = Project(length=16, root_note=64, scale="Major")
    a = blk(1, "B", "BASS", "Scale Walker"); m = blk(2, "M", "MELODY", "Scale Walker")
    p.blocks = [a, m]; p.relations = [Relation(1, "pitch", 2, "pitch", "Mix", .5)]
    MusicEngine(p).generate()
    notes, bad = in_scale(p, m)
    assert notes and not bad


# 12 selectable role source; 13 Replace differs from Union
def test_drum_source_selection_is_respected():
    p = Project()
    d1 = blk(1, "D1", "DRUM", "Euclidean", pulses=1); d2 = blk(2, "D2", "DRUM", "Euclidean", pulses=7)
    b = blk(3, "B", "BASS", "Random Walk", groove_follow=1.0, relation_drum_source=2)
    p.blocks = [d1, d2, b]; e = MusicEngine(p); e.generate()
    assert sum(1 for x in b.outputs["rhythm"] if x > 0) == 7
    assert e.role_relation_source(b) is d2


def test_groove_replace_differs_from_union():
    outs = {}
    for mode in ("Union", "Replace"):
        p = Project(length=16)
        d = blk(1, "D", "DRUM", "Euclidean", pulses=4)
        b = blk(2, "B", "BASS", "Random Walk", groove_follow=.5, groove_mode=mode)
        p.blocks = [d, b]; MusicEngine(p).generate()
        outs[mode] = (b.outputs["rhythm"], d.outputs["rhythm"])
    assert outs["Union"][0] != outs["Replace"][0]
    bass, drum = outs["Replace"]
    assert all(dr > 0 for br, dr in zip(bass, drum) if br > 0)   # Replace only keeps drum hits


# 15 probability applied once for LIVE under the Director
def test_live_event_does_not_apply_event_probability():
    src = (ROOT / "auricle_engine.py").read_text(encoding="utf-8")
    live = src[src.index("    def live_event"):src.index("    def _chord_pitches")]
    assert "event_probability" not in live.replace("event_probability() already", "")


# 16 crossfade easing
def test_crossfade_uses_known_shape():
    assert '"in-out"' not in (ROOT / "performance_presets.py").read_text(encoding="utf-8")


# 17 SEQ voice leading is deterministic across regenerations
def test_seq_voice_leading_is_idempotent():
    p = Project(length=16); m = blk(1, "M", "MELODY", "Scale Walker"); p.blocks = [m]
    e = MusicEngine(p); e.director.phrase.running = True
    e.generate_block(m); first = list(m.outputs["pitch"])
    e.generate_block(m)
    assert m.outputs["pitch"] == first


# 18 atomic save
def test_failed_save_keeps_previous_file():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "p.json")
        good = Project(); save_project(good, path)
        before = Path(path).read_text(encoding="utf-8")
        bad = Project(); bad.macros = [{"x": object()}]
        with pytest.raises(TypeError):
            save_project(bad, path)
        assert Path(path).read_text(encoding="utf-8") == before
        assert load_project(path).tempo == good.tempo
        assert os.listdir(folder) == ["p.json"]
