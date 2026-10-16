"""Behavioral coverage for the LIVE side of Perform techniques."""

from auricle_core import Block, MusicEngine, Project


def live_block(algorithm="Pattern", parameters=None):
    values = {"pattern": "1", "live_min_beats": .4, "live_max_beats": .4}
    values.update(parameters or {})
    block = Block(1, "LIVE", "MELODY", algorithm, "LIVE", parameters=values)
    project = Project(tempo=120, length=16, blocks=[block])
    return project, block, MusicEngine(project)


def test_live_timing_rate_changes_interval_without_regenerating_material():
    _, block, engine = live_block(parameters={"timing_rate": 2.0})
    engine.live_state[block.id] = {"events": 0}
    slow = engine._live_interval(block, engine._rng_for(block))
    block.parameters["timing_rate"] = .5
    fast = engine._live_interval(block, engine._rng_for(block))
    assert slow == .1
    assert fast == .4


def test_live_timing_swing_and_humanize_are_consumed():
    _, block, engine = live_block(parameters={"timing_swing": .5, "timing_humanize": 0.0})
    engine.live_state[block.id] = {"events": 1}
    swung = engine._live_interval(block, engine._rng_for(block))
    assert swung == .25


def test_live_gate_reads_active_staccato_or_tenuto_override():
    project = Project(tempo=120, length=16, blocks=[
        Block(1, "DRUM", "DRUM", "Pattern", "LIVE", parameters={
            "pattern": "1", "live_min_beats": .4, "live_max_beats": .4, "live_gate": .65,
        })
    ])
    block = project.blocks[0]
    engine = MusicEngine(project)
    engine.performance.active[block.id] = type("State", (), {"current_values": {"gate": .22}})()
    event = engine.live_event(block)
    assert event is not None
    assert event["duration"] == .22
    engine.performance.active[block.id].current_values = {"gate": .98}
    event = engine.live_event(block)
    assert event is not None
    assert event["duration"] == .98


def test_live_velocity_reads_dynamic_and_accent_overrides():
    _, block, engine = live_block(parameters={"velocity_range": 0.0})
    baseline = engine.live_event(block)
    assert baseline is not None
    engine.reset_live()
    engine.performance.active[block.id] = type("State", (), {
        "current_values": {"velocity_base": .20, "velocity_accent": .40}
    })()
    event = engine.live_event(block)
    assert event is not None
    assert event["velocity"] < baseline["velocity"]
    assert event["velocity"] > .20


def test_live_euclidean_rotation_changes_the_phase():
    _, block, engine = live_block(
        algorithm="Euclidean",
        parameters={"euclidean_steps": 4, "pulses": 1, "euclidean_rotation": 0},
    )
    first = [engine.live_event(block) is not None for _ in range(4)]
    engine.reset_live()
    block.parameters["euclidean_rotation"] = 1
    rotated = [engine.live_event(block) is not None for _ in range(4)]
    assert first != rotated
