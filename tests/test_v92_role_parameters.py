from auricle_core import Block, MusicEngine, Project, apply_role_defaults


def test_role_defaults_are_materialized_as_editable_parameters():
    for role in ("BASS", "MELODY", "PAD", "CHORD"):
        b = Block(1, role, role, "Pattern", "SEQ", 1, "", 60, {})
        apply_role_defaults(b)
        assert "role_center" in b.parameters
        assert "role_width" in b.parameters
        assert "role_density" in b.parameters
        assert "role_duration" in b.parameters
        assert "role_root_bias" in b.parameters


def test_role_center_and_width_are_used_in_pitch_mapping():
    project = Project(root_note=60, scale="Major", length=4)
    bass = Block(1, "BASS", "BASS", "Pattern", "SEQ", 1, "", 60,
                 {"pattern": "0,4,7,12", "role_center": -6, "role_width": 12})
    project.blocks = [bass]
    MusicEngine(project).generate()
    assert min(bass.outputs["pitch"]) >= -12
    assert max(bass.outputs["pitch"]) <= 0


def test_role_duration_replaces_hidden_type_multiplier():
    project = Project(root_note=60, scale="Major", length=2)
    melody = Block(1, "MELODY", "MELODY", "Pattern", "SEQ", 1, "", 60,
                   {"pattern": "4,0", "gate": 1.0, "role_duration": 2.0})
    project.blocks = [melody]
    MusicEngine(project).generate()
    assert melody.outputs["duration"][0] == 2.0


def test_role_density_is_effective_generation_control():
    project = Project(root_note=60, scale="Major", length=16)
    bass = Block(1, "BASS", "BASS", "Pattern", "SEQ", 1, "", 60,
                 {"pattern": "0,4,7,12", "role_density": 0.0})
    project.blocks = [bass]
    MusicEngine(project).generate()
    assert not any(bass.outputs["rhythm"])
