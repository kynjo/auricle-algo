"""Looped harmony must retain its musical register in generated and sent MIDI."""
import pytest

from auricle_core import Block, Project, MusicEngine, midi_note_for
from harmonic_plan import HarmonicRuntime, PRESETS, QUALITIES, preset
from voice_leading import VoiceLeading
from test_coordinated_kit import setup_transport


def notes_for(runtime, block, beat, pitch=-12):
    event = runtime.apply(block, {'pitch': pitch, 'velocity': .8}, beat)
    return [midi_note_for(runtime.project, block, p) for p in event['pitches']]


@pytest.mark.parametrize('name', PRESETS)
@pytest.mark.parametrize('role', ['CHORD', 'PAD'])
@pytest.mark.parametrize('reverse', [False, True])
def test_long_progressions_stay_in_register_in_either_direction(name, role, reverse):
    plan = preset(name)
    if reverse:
        plan['chords'].reverse()
    block = Block(1, role, role, parameters={'role_center': -12, 'role_width': 24})
    runtime = HarmonicRuntime(Project(blocks=[block], harmonic_plan=plan))
    for bar in range(100 * len(plan['chords'])):
        notes = notes_for(runtime, block, bar*4)
        assert 36 <= min(notes) <= max(notes) <= 60
        assert {note % 12 for note in notes} == set(runtime.at(bar*4)['pitch_classes'])


@pytest.mark.parametrize('mode', ['SEQ', 'LIVE'])
@pytest.mark.parametrize('role', ['CHORD', 'PAD'])
def test_long_running_transport_emits_bounded_chords(monkeypatch, mode, role):
    block = Block(1, role, role, 'Pattern', mode, midi_port='capture', mutators=[], parameters={
        'pattern': '1', 'live_min_beats': .25, 'live_max_beats': .25,
        'fill_density': 1, 'event_probability': 1,
        'role_center': -12, 'role_width': 24})
    project = Project(blocks=[block], harmonic_plan=preset('Dm7 – G7 – Cmaj7'))
    engine = MusicEngine(project)
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    try:
        # 32 complete loops / 96 bars, including the previously rising ii-V-I.
        for i in range(32 * 3 * 16 + 1):
            tick(i*.125)
        onsets = [(t, msg.note) for t, msg in sent if msg.type == 'note_on' and msg.velocity > 0]
        assert len(onsets) > 300
        assert {engine.harmonic_runtime.at(t*2)['name'] for t, _ in onsets} == {'Dm7', 'G7', 'Cmaj7'}
        assert all(36 <= note <= 60 for _, note in onsets)
        assert all(note % 12 in engine.harmonic_runtime.at(t*2)['pitch_classes'] for t, note in onsets)
    finally:
        transport.stop()


def test_register_controls_apply_without_waiting_for_next_chord():
    block = Block(1, 'Chords', 'CHORD', parameters={'role_center': -12, 'role_width': 24})
    runtime = HarmonicRuntime(Project(blocks=[block], harmonic_plan=preset()))
    first = notes_for(runtime, block, 0)
    block.parameters['role_center'] += 12
    raised = notes_for(runtime, block, .25)
    assert raised == [note+12 for note in first]
    block.midi_note -= 24
    lowered = notes_for(runtime, block, .5)
    assert lowered == [note-24 for note in raised]
    block.parameters['role_width'] = 6
    narrowed = notes_for(runtime, block, .75)
    assert {note % 12 for note in narrowed} == {note % 12 for note in first}
    # Generator pitch changes cannot accumulate into a new register either.
    for bar in range(32):
        notes = notes_for(runtime, block, bar*4, pitch=bar*12)
        assert 24 <= min(notes) <= max(notes) <= 48


def test_narrowing_register_repositions_current_chord():
    block = Block(1, 'Chords', 'CHORD', parameters={'role_center': -12, 'role_width': 48})
    plan = preset('C – Am – F – G')
    runtime = HarmonicRuntime(Project(blocks=[block], harmonic_plan=plan))
    assert notes_for(runtime, block, 0, pitch=0) == [60, 64, 67]
    block.parameters['role_width'] = 24
    assert notes_for(runtime, block, .25, pitch=0) == [48, 52, 55]


@pytest.mark.parametrize('quality', QUALITIES)
@pytest.mark.parametrize('inversion,spread,width', [(0, 7, 24), (1, 14, 24), (-1, 36, 6)])
def test_octave_selection_preserves_voicing_even_when_wider_than_register(quality, inversion, spread, width):
    intervals = list(QUALITIES[quality][1])
    notes = [60+i for i in intervals]
    for _ in range(abs(inversion) % len(notes)):
        notes = notes[1:]+[notes[0]+12] if inversion > 0 else [notes[-1]-12]+notes[:-1]
    for i in range(1, len(notes)):
        while notes[i]-notes[0] < spread*i/(len(notes)-1):
            notes[i] += 12
    notes.sort()
    bounded = VoiceLeading.resolve_chord(notes, [110, 114, 117, 121], register=(48-width/2, 48+width/2))
    assert [note-bounded[0] for note in bounded] == [note-notes[0] for note in notes]
    assert {n % 12 for n in bounded} == set(intervals)
    assert abs((bounded[0]+bounded[-1])/2 - 48) <= 6


@pytest.mark.parametrize('base', [0, 12, 108, 127])
def test_extreme_midi_bases_keep_chord_tones_and_distinct_voices(base):
    block = Block(1, 'Chords', 'CHORD', midi_note=base, parameters={
        'harmony_inversion': -1, 'harmony_spread': 36, 'role_width': 6})
    runtime = HarmonicRuntime(Project(blocks=[block], harmonic_plan=preset('Dm7 – G7 – Cmaj7')))
    for bar in range(24):
        notes = notes_for(runtime, block, bar*4)
        assert 0 <= min(notes) <= max(notes) <= 127
        assert len(notes) == len(set(notes)) == 4
        assert {n % 12 for n in notes} == set(runtime.at(bar*4)['pitch_classes'])


def test_reset_and_plan_edit_clear_register_memory():
    block = Block(1, 'Chords', 'CHORD')
    project = Project(blocks=[block], harmonic_plan=preset())
    runtime = HarmonicRuntime(project)
    first = notes_for(runtime, block, 0)
    notes_for(runtime, block, 4)
    runtime.reset()
    assert not runtime.register_centers and not runtime.voicings and not runtime.tokens
    assert notes_for(runtime, block, 0) == first
    project.harmonic_plan['enabled'] = False
    assert not runtime.follows(block)
    assert not runtime.register_centers and not runtime.voicings and not runtime.tokens
