import pytest

from auricle_core import Block, MusicEngine, Project, Relation


def _live_block(algorithm="Probability"):
    return Block(
        1, "LIVE", "MELODY", algorithm, "LIVE", 1, "", 60,
        {"probability": 1.0, "probability_pitch_range": 2, "live_gate": .5,
         "fill_density": 1.0},
    )


def test_global_macros_are_applied_to_live_velocity_and_density():
    low = _live_block()
    high = _live_block()
    low_engine = MusicEngine(Project(blocks=[low]))
    high_engine = MusicEngine(Project(blocks=[high]))
    low_engine.director.set_global_macro("energy", 0.0)
    high_engine.director.set_global_macro("energy", 1.0)
    low_events = [low_engine.live_event(low) for _ in range(24)]
    high_events = [high_engine.live_event(high) for _ in range(24)]
    low_velocity = sum(event["velocity"] for event in low_events if event) / 24
    high_velocity = sum(event["velocity"] for event in high_events if event) / 24
    assert high_velocity > low_velocity

    sparse = _live_block("Euclidean")
    dense = _live_block("Euclidean")
    sparse.parameters.update(euclidean_steps=16, pulses=8)
    dense.parameters.update(euclidean_steps=16, pulses=8)
    sparse_engine = MusicEngine(Project(blocks=[sparse]))
    dense_engine = MusicEngine(Project(blocks=[dense]))
    sparse_engine.director.set_global_macro("density", 0.0)
    dense_engine.director.set_global_macro("density", 1.0)
    sparse_hits = sum(sparse_engine.live_event(sparse) is not None for _ in range(64))
    dense_hits = sum(dense_engine.live_event(dense) is not None for _ in range(64))
    assert dense_hits > sparse_hits


def test_generate_applies_persisted_macro_routes():
    block = Block(1, "MELODY", "MELODY", "Pattern", "SEQ", parameters={"pattern": "1,1,1,1", "fill_density": .2})
    project = Project(blocks=[block], macros=[{
        "name": "Density", "control": "density", "value": 1.0,
        "routes": [{"block_id": 1, "parameter": "fill_density", "min": .1, "max": .9, "amount": 1.0}],
    }])
    MusicEngine(project).generate()
    assert block.parameters["fill_density"] == pytest.approx(.9)


def test_visible_role_route_replaces_builtin_role_transform():
    drum = Block(1, "DRUM", "DRUM", "Pattern", "SEQ", parameters={"pattern": "1,0,1,0"})
    bass = Block(2, "BASS", "BASS", "Pattern", "SEQ", parameters={
        "pattern": "1,1,1,1", "groove_follow": 1.0,
    })
    project = Project(length=4, blocks=[drum, bass], relations=[
        Relation(1, "rhythm", 2, "rhythm", "Follow", 0.5),
    ])
    MusicEngine(project).generate()
    # The explicit route is the sole transform.  Applying the built-in first
    # would produce a second blend and a different third step.
    assert bass.outputs["rhythm"] == [1.0, .5, 1.0, .5]
