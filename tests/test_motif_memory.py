"""Persistent motif history, project round-trips and cycle-safe transforms."""
from dataclasses import asdict

from auricle_core import Block, MusicEngine, Project, load_project, save_project
from motif_engine import Motif
from motif_development import MotifDevelopment


def source():
    return Motif("theme", "Theme", notes=[0, 2, 4, 7],
                 rhythm=[1, 0, 1, 1], velocity=[.9, 0, .7, .85], step_beats=.5)


def test_motif_variant_memory_roundtrips_and_can_be_recalled(tmp_path):
    motif = source()
    block = Block(1, "Lead", "MELODY", parameters={"motif_id": motif.id,
                 "motif_development": "combined", "motif_amount": .8})
    project = Project(blocks=[block], motifs={motif.id: asdict(motif)})
    engine = MusicEngine(project)
    engine.director.motifs.register(motif)
    first = engine.motif_variant(block, 2)
    second = engine.motif_variant(block, 4)
    assert first.token != second.token
    assert project.motif_memory["version"] == 1

    path = tmp_path / "motif-memory.json"
    save_project(project, path)
    restored = load_project(path)
    restored_engine = MusicEngine(restored)
    history = restored_engine.motif_development.history[1]
    assert [item.token for item in history][-2:] == [first.token, second.token]
    assert restored_engine.hold_motif(restored.blocks[0], token=first.token)
    recalled = restored_engine.motif_variant(restored.blocks[0], 8)
    assert recalled.motif.notes == first.motif.notes


def test_memory_loader_ignores_malformed_entries_and_is_bounded():
    runtime = MotifDevelopment({"version": 1, "owners": {
        "7": {"source_id": "theme", "variants": [
            {"motif": {"id": "theme", "name": "ok", "notes": [0], "rhythm": [1]},
             "cycle": 0, "token": "valid"},
            {"motif": {"id": "broken", "notes": "bad"}, "cycle": "bad"},
        ]},
    }})
    assert len(runtime.history[7]) == 1
    assert runtime.history[7][0].token == "valid"
    assert runtime.export_memory()["version"] == 1


def test_manual_transform_creates_child_without_mutating_parent():
    motif = source()
    block = Block(1, "Lead", "MELODY", parameters={"motif_id": motif.id})
    project = Project(blocks=[block], motifs={motif.id: asdict(motif)})
    engine = MusicEngine(project)
    engine.director.motifs.register(motif)
    original = asdict(motif)
    transformed, pending = engine.transform_motif(block, "retrograde")
    assert not pending
    assert transformed.id != motif.id
    assert transformed.parent_id == motif.id
    assert transformed.transformation == "retrograde"
    assert transformed.notes == list(reversed(motif.notes))
    assert asdict(motif) == original
    assert block.parameters["motif_id"] == transformed.id
    assert project.motifs[transformed.id]["parent_id"] == motif.id


def test_manual_transform_while_playing_commits_only_at_next_cycle():
    motif = source()
    block = Block(1, "Lead", "MELODY", parameters={"motif_id": motif.id})
    project = Project(blocks=[block], motifs={motif.id: asdict(motif)})
    engine = MusicEngine(project)
    engine.director.motifs.register(motif)
    engine.clock.start(0, 120)
    engine.clock.position_beats = 1.5  # source cycle is two beats
    queued, pending = engine.transform_motif(block, "retrograde")
    assert pending and queued.id == motif.id
    assert block.parameters["motif_id"] == motif.id
    assert engine.motif_variant(block, 1.99).motif.id == motif.id
    variant = engine.motif_variant(block, 2.0)
    assert block.parameters["motif_id"] != motif.id
    assert variant.motif.id == block.parameters["motif_id"]
    assert variant.motif.notes == list(reversed(motif.notes))
    assert "motif_pending_transform" not in block.parameters


def test_pending_transform_is_cancelled_if_source_binding_changes():
    first, second = source(), Motif("other", "Other", notes=[7, 5], rhythm=[1, 1])
    block = Block(1, "Lead", "MELODY", parameters={"motif_id": first.id})
    project = Project(blocks=[block], motifs={first.id: asdict(first), second.id: asdict(second)})
    engine = MusicEngine(project)
    engine.director.motifs.register(first)
    engine.director.motifs.register(second)
    engine.clock.start(0, 120)
    engine.clock.position_beats = 1
    engine.transform_motif(block, "retrograde")
    block.parameters["motif_id"] = second.id
    engine.motif_variant(block, 10)
    assert block.parameters["motif_id"] == second.id
    assert "motif_pending_transform" not in block.parameters


def test_coordinated_drum_rejects_independent_duration_transforms():
    from auricle_core import ensure_drum_voices
    drum = Block(1, "Kit", "DRUM", parameters={"kit_coordinated": True})
    voice = ensure_drum_voices(drum)[0]
    motif = Motif("drum_theme", "Drum theme", role="DRUM", rhythm=[1, 0, 1, 0])
    voice.parameters["motif_id"] = motif.id
    project = Project(blocks=[drum], motifs={motif.id: asdict(motif)})
    engine = MusicEngine(project)
    engine.director.motifs.register(motif)
    try:
        engine.transform_motif(voice, "augment", 2)
    except ValueError as exc:
        assert "shared timing grid" in str(exc)
    else:
        raise AssertionError("A coordinated voice must not change its independent step duration")
