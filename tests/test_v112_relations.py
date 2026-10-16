from auricle_core import Block, MusicEngine, Project


def test_drum_to_bass_strict_groove_mask_and_accent():
    project = Project(length=4, seed=1)
    drum = Block(1, "DRUM", "DRUM", "Pattern", "SEQ", parameters={
        "pattern": "1,0,1,0", "fill_density": 1.0,
    })
    bass = Block(2, "BASS", "BASS", "Pattern", "SEQ", parameters={
        "pattern": "0,2,0,2", "fill_density": 1.0,
        "groove_follow": 1.0, "groove_accent": 1.0,
    })
    project.blocks = [drum, bass]
    engine = MusicEngine(project)
    engine.generate()

    assert bass.outputs["rhythm"] == drum.outputs["rhythm"]
    assert all(bass.outputs["velocity"][i] > 0 for i in (0, 2))
    assert all(bass.outputs["duration"][i] > 0 for i in (0, 2))
    assert engine.musical_context.values["drum_to_bass"]["groove_follow"] == 1.0


def test_drum_to_bass_zero_amount_preserves_generator_material():
    project = Project(length=4, seed=1)
    drum = Block(1, "DRUM", "DRUM", "Pattern", "SEQ", parameters={
        "pattern": "1,0,1,0", "fill_density": 1.0,
    })
    bass = Block(2, "BASS", "BASS", "Pattern", "SEQ", parameters={
        "pattern": "0,2,0,2", "fill_density": 1.0,
        "groove_follow": 0.0, "groove_accent": 0.0,
    })
    project.blocks = [drum, bass]
    MusicEngine(project).generate()
    assert bass.outputs["rhythm"] == [0.0, 1.0, 0.0, 1.0]


def test_chord_to_melody_anchors_to_chord_tones():
    project = Project(length=4, seed=7)
    chord = Block(1, "CHORD", "CHORD", "Pattern", "SEQ", parameters={
        "pattern": "1,1,1,1", "fill_density": 1.0,
    })
    melody = Block(2, "MELODY", "MELODY", "Pattern", "SEQ", parameters={
        "pattern": "11,9,6,4", "fill_density": 1.0,
        "harmony_anchor": 1.0,
    })
    project.blocks = [chord, melody]
    engine = MusicEngine(project)
    engine.generate()

    for i, pitch in enumerate(melody.outputs["pitch"]):
        tones = engine._chord_pitches(chord, chord.outputs["pitch"][i])
        assert any(round(pitch - tone) % 12 == 0 for tone in tones)
    assert engine.musical_context.values["chord_to_melody"]["harmony_anchor"] == 1.0


def test_chord_to_melody_zero_amount_is_bypass():
    project = Project(length=4, seed=7)
    chord = Block(1, "CHORD", "CHORD", "Pattern", "SEQ", parameters={
        "pattern": "1,1,1,1", "fill_density": 1.0,
    })
    melody = Block(2, "MELODY", "MELODY", "Pattern", "SEQ", parameters={
        "pattern": "11,9,6,4", "fill_density": 1.0,
        "harmony_anchor": 0.0,
    })
    project.blocks = [chord, melody]
    engine = MusicEngine(project)
    engine.generate()
    baseline_project = Project(length=4, seed=7)
    baseline = Block(2, "MELODY", "MELODY", "Pattern", "SEQ", parameters={
        "pattern": "11,9,6,4", "fill_density": 1.0,
        "harmony_anchor": 0.0,
    })
    baseline_project.blocks = [baseline]
    MusicEngine(baseline_project).generate()
    assert melody.outputs["pitch"] == baseline.outputs["pitch"]
