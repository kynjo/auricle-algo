from auricle_core import Block, MusicEngine, Project, ROLE_PROFILES


def test_role_defaults_define_distinct_musical_jobs():
    assert ROLE_PROFILES["BASS"]["register_anchor"] < ROLE_PROFILES["MELODY"]["register_anchor"]
    assert ROLE_PROFILES["PAD"]["register_anchor"] < ROLE_PROFILES["MELODY"]["register_anchor"]
    assert ROLE_PROFILES["PAD"]["harmony_size"] == 3
    assert ROLE_PROFILES["CHORD"]["harmony_size"] == 3


def test_bass_and_melody_use_different_registers():
    project = Project(root_note=60, scale="Major", length=4)
    bass = Block(1, "BASS", "BASS", "Pattern", "SEQ", 1, "", 60, {"pattern": "0,4,7,12"})
    melody = Block(2, "MELODY", "MELODY", "Pattern", "SEQ", 1, "", 60, {"pattern": "0,4,7,12"})
    project.blocks = [bass, melody]
    engine = MusicEngine(project)
    engine.generate()
    assert max(bass.outputs["pitch"]) <= 0
    assert max(melody.outputs["pitch"]) >= 4
    assert bass.outputs["pitch"] != melody.outputs["pitch"]


def test_pad_is_sustained_and_polyphonic():
    project = Project(root_note=60, scale="Major", length=4)
    pad = Block(1, "PAD", "PAD", "Pattern", "SEQ", 1, "", 60, {"pattern": "0,0,7,0"})
    project.blocks = [pad]
    engine = MusicEngine(project)
    engine.generate()
    assert pad.outputs["duration"][2] > 1.0
    assert len(engine._chord_pitches(pad, pad.outputs["pitch"][2])) == 3


def test_role_profiles_cover_harmonic_and_melodic_blocks():
    assert {"BASS", "MELODY", "PAD", "CHORD"} <= set(ROLE_PROFILES)
