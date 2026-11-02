from types import SimpleNamespace

import mido
import pytest

from midi_learn import (
    MidiLearnRuntime, decode_input_message, mapping_matches,
    normalize_mapping, normalize_mappings,
)
from auricle_model import Block, Project
from auricle_persistence import project_from_dict


def msg(kind, **kwargs):
    return SimpleNamespace(type=kind, **kwargs)


def test_decode_supported_input_messages_and_ignore_non_controls():
    assert decode_input_message(mido.Message("control_change", channel=1, control=74, value=127)) == {
        "type": "cc", "channel": 1, "number": 74, "value": 1.0,
    }
    assert decode_input_message(mido.Message("note_on", channel=0, note=60, velocity=64))["value"] == pytest.approx(64 / 127)
    assert decode_input_message(mido.Message("pitchwheel", channel=2, pitch=0))["value"] == pytest.approx(8192 / 16383)
    assert decode_input_message(mido.Message("aftertouch", channel=3, value=127))["value"] == 1.0
    assert decode_input_message(mido.Message("polytouch", channel=4, note=67, value=32))["number"] == 67
    assert decode_input_message(msg("note_on", channel=0, note=60, velocity=0)) is None
    assert decode_input_message(msg("clock")) is None


def test_mapping_normalization_and_matching_respects_port_channel_and_number():
    mapping = normalize_mapping({
        "source": {"port": "Keyboard", "type": "cc", "channel": 2, "number": 74},
        "target": {"kind": "block_parameter", "block_id": 3, "parameter": "fill_density"},
        "min": 0, "max": 1,
    })
    event = {"type": "cc", "channel": 2, "number": 74, "value": .5}
    assert mapping_matches(mapping, "Keyboard", event)
    assert not mapping_matches(mapping, "Other", event)
    assert not mapping_matches(mapping, "Keyboard", event | {"channel": 1})
    assert not mapping_matches(mapping, "Keyboard", event | {"number": 71})
    assert normalize_mappings([mapping, None, {}])


def test_soft_takeover_waits_until_controller_crosses_current_parameter():
    mapping = normalize_mapping({
        "id": "pickup", "source": {"type": "cc", "number": 1},
        "target": {"kind": "block_parameter", "block_id": 1, "parameter": "fill_density"},
        "min": 0, "max": 1, "pickup": True,
    })
    runtime = MidiLearnRuntime()
    runtime.prime("pickup", .1)
    event = {"type": "cc", "channel": 0, "number": 1, "value": .2}
    assert runtime.value_for(mapping, "Keyboard", event, .7) is None
    event["value"] = .6
    assert runtime.value_for(mapping, "Keyboard", event, .7) is None
    event["value"] = .75
    assert runtime.value_for(mapping, "Keyboard", event, .7) == pytest.approx(.75)
    event["value"] = .9
    assert runtime.value_for(mapping, "Keyboard", event, .75) == pytest.approx(.9)


def test_soft_takeover_can_be_disabled_and_value_is_scaled_to_target_range():
    mapping = normalize_mapping({
        "source": {"type": "pitchwheel"},
        "target": {"kind": "block_parameter", "block_id": 1, "parameter": "transpose"},
        "min": -12, "max": 12, "pickup": False,
    })
    runtime = MidiLearnRuntime()
    event = {"type": "pitchwheel", "channel": 0, "number": None, "value": .75}
    assert runtime.value_for(mapping, "Keyboard", event, 0) == pytest.approx(6)


def test_project_roundtrip_preserves_midi_learn_mappings_and_input_port():
    payload = {
        "blocks": [{"id": 1, "name": "Lead", "block_type": "MELODY", "parameters": {"fill_density": .4}}],
        "midi_input_port": "Keyboard Input",
        "midi_mappings": [{
            "source": {"port": "Keyboard Input", "type": "cc", "channel": 0, "number": 74},
            "target": {"kind": "block_parameter", "block_id": 1, "parameter": "fill_density"},
            "min": 0, "max": 1,
        }],
    }
    project = project_from_dict(payload)
    assert project.midi_input_port == "Keyboard Input"
    assert len(project.midi_mappings) == 1
    assert project.midi_mappings[0]["source"]["number"] == 74
    legacy = project_from_dict({"blocks": []})
    assert legacy.midi_input_port == ""
    assert legacy.midi_mappings == []


def test_save_load_roundtrip_persists_midi_learn(tmp_path):
    from auricle_persistence import save_project, load_project
    project = Project(blocks=[Block(1, "Lead", "MELODY", parameters={"fill_density": .3})])
    project.midi_input_port = "Controller"
    project.midi_mappings = normalize_mappings([{
        "source": {"port": "Controller", "type": "cc", "channel": 0, "number": 21},
        "target": {"kind": "block_parameter", "block_id": 1, "parameter": "fill_density"},
        "min": 0, "max": 1,
    }])
    path = tmp_path / "midi-learn.auricle.json"
    save_project(project, str(path))
    restored = load_project(str(path))
    assert restored.midi_input_port == "Controller"
    assert restored.midi_mappings[0]["source"]["number"] == 21
    assert restored.midi_mappings[0]["target"]["parameter"] == "fill_density"


def test_integer_target_metadata_is_preserved_for_integer_knobs():
    mapping = normalize_mapping({
        "source": {"type": "cc", "number": 7},
        "target": {"kind": "block_parameter", "block_id": 1,
                   "parameter": "euclidean_steps", "integer": True},
        "min": 1, "max": 32,
    })
    assert mapping["target"]["integer"] is True


def test_input_port_discovery_is_safe_when_backend_raises(monkeypatch):
    from auricle_transport import get_midi_input_names
    monkeypatch.setattr("auricle_transport.mido.get_input_names", lambda: ["Controller Port"])
    assert get_midi_input_names() == (["Controller Port"], None)
    def broken():
        raise RuntimeError("backend unavailable")
    monkeypatch.setattr("auricle_transport.mido.get_input_names", broken)
    names, error = get_midi_input_names()
    assert names == []
    assert "backend unavailable" in error
