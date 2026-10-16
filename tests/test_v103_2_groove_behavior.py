from auricle_core import Block, MusicEngine, Project


def build(drum_pattern):
    project = Project(length=4, seed=4)
    drum = Block(1, "DRUM", "DRUM", "Pattern", parameters={
        "pattern": drum_pattern, "fill_density": 1.0,
    })
    bass = Block(2, "BASS", "BASS", "Pattern", parameters={
        "pattern": "1,1,1,1", "fill_density": 1.0,
        "groove_follow": .5, "groove_accent": 0.0,
    })
    project.blocks = [drum, bass]
    engine = MusicEngine(project)
    engine.generate()
    return engine, drum, bass


def test_drum_pattern_updates_musical_context_groove():
    sparse, _, _ = build("1,0,0,0")
    dense, _, _ = build("1,1,1,1")
    assert sparse.musical_context.groove < dense.musical_context.groove
    assert sparse.musical_context.values["groove_metrics"]["density"] < 1.0


def test_groove_context_reaches_bass_generation():
    sparse, _, bass_sparse = build("1,0,0,0")
    dense, _, bass_dense = build("1,1,1,1")
    assert sparse.musical_context.values["groove_applied"]["block"] == bass_sparse.id
    assert dense.musical_context.values["groove_applied"]["block"] == bass_dense.id
    assert bass_sparse.outputs["duration"] != bass_dense.outputs["duration"]
