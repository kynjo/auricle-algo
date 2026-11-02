from auricle_model import Project, Block
from auricle_persistence import save_project, load_project
from auricle_transport import get_midi_input_names
from midi_learn import normalize_mappings
from midi_expression import normalize_expression, normalize_midi_sync


def test_project_keeps_midi_learn_and_expression_fields_together():
    project = Project(blocks=[Block(1, "Lead", "MELODY")])
    assert hasattr(project, "midi_input_port")
    assert hasattr(project, "midi_mappings")
    assert hasattr(project, "midi_sync")
    assert hasattr(project.blocks[0], "midi_expression")


def test_project_roundtrip_keeps_midi_learn_and_expression_together(tmp_path):
    project = Project(blocks=[Block(1, "Lead", "MELODY", parameters={"fill_density": .4})])
    project.midi_input_port = "Controller In"
    project.midi_mappings = normalize_mappings([{
        "source": {"port": "Controller In", "type": "cc", "channel": 0, "number": 74},
        "target": {"kind": "block_parameter", "block_id": 1, "parameter": "fill_density"},
        "min": 0, "max": 1,
    }])
    project.midi_sync = normalize_midi_sync({"clock_out": True})
    project.blocks[0].midi_expression = normalize_expression({
        "cc_lanes": [{"controller": 74, "enabled": True, "points": [[0, 0], [1, 1]]}]
    })
    path = tmp_path / "combined-midi.auricle.json"
    save_project(project, str(path))
    restored = load_project(str(path))
    assert restored.midi_input_port == "Controller In"
    assert len(restored.midi_mappings) == 1
    assert restored.midi_sync["clock_out"] is True
    assert restored.blocks[0].midi_expression


def test_midi_input_port_discovery_is_callable(monkeypatch):
    import auricle_transport
    monkeypatch.setattr(auricle_transport.mido, "get_input_names", lambda: ["Controller In"])
    assert get_midi_input_names() == (["Controller In"], None)
