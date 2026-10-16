from auricle_core import Block, MusicEngine, Project, apply_role_defaults


def live_block(block_id, name, role, pattern, **params):
    values = {"pattern": pattern, "fill_density": 1.0, "event_probability": 1.0}
    values.update(params)
    block = Block(block_id, name, role, "Pattern", "LIVE", parameters=values)
    apply_role_defaults(block)
    return block


def test_live_drum_rest_reaches_live_bass_relation():
    project = Project(length=4, seed=11)
    drum = live_block(1, "DRUM", "DRUM", "1,0")
    bass = live_block(2, "BASS", "BASS", "1", groove_follow=1.0, groove_accent=0.0)
    project.blocks = [drum, bass]
    engine = MusicEngine(project)
    engine.reset_live()

    assert engine.live_event(drum) is not None
    assert engine.live_event(bass) is not None
    assert engine.live_event(drum) is None
    # The source's current rest must replace its previous LIVE output before
    # the bass relation is evaluated; stale source events would leak through.
    assert engine.live_event(bass) is None


def test_live_chord_rest_does_not_reanchor_melody_to_stale_chord():
    project = Project(length=4, seed=12)
    chord = live_block(1, "CHORD", "CHORD", "1,0")
    melody = live_block(2, "MELODY", "MELODY", "4,7", harmony_anchor=1.0)
    project.blocks = [chord, melody]
    engine = MusicEngine(project)
    engine.reset_live()

    assert engine.live_event(chord) is not None
    first = engine.live_event(melody)
    assert first is not None
    assert engine.live_event(chord) is None
    second = engine.live_event(melody)
    assert second is not None
    assert second["pitch"] == 7.0
