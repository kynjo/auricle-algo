from pathlib import Path

GUI_SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"
ROOT = Path(__file__).resolve().parents[1]


def _section(source: str, start: str, end: str) -> str:
    return source[source.index(start):source.index(end)]


def test_structure_exposes_pattern_and_timing_parameters():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    section = _section(source, "# STRUCTURE", "# MUSICAL")
    for key in ("structure_length", "fill_density", "event_probability", "structure_rotation",
                "timing_rate", "timing_swing", "gate", "timing_humanize", "timing_offset"):
        assert f'"{key}"' in section


def test_musical_exposes_scale_pitch_harmony_and_representation():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    section = _section(source, "# MUSICAL", "# MOTION")
    for key in ("scale_root", "scale_name", "transpose", "octave", "pitch_range",
                "harmony_size", "harmony_spread", "harmony_inversion",
                "velocity_base", "velocity_range", "velocity_random", "velocity_accent"):
        assert f'"{key}"' in section


def test_motion_has_mutation_controls_and_no_future_sections():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    section = _section(source, "# MOTION", "# MONITOR / diagnostics")
    for key in ("mutation_pitch", "mutation_rhythm", "mutation_velocity", "mutation_timing"):
        assert f'"{key}"' in section
    assert 'InspectorGroup("STOCHASTIC"' not in section
    assert 'InspectorGroup("MODULATION"' not in section
    assert 'InspectorGroup("EVOLUTION"' not in section


def test_core_supports_structure_length_rotation_and_timing_rate():
    catalogs = (ROOT / "auricle_catalogs.py").read_text(encoding="utf-8")
    transport = (ROOT / "auricle_transport.py").read_text(encoding="utf-8")
    assert '"structure_length"' in catalogs
    assert '"structure_rotation"' in catalogs
    assert 'def _block_seq_interval' in transport
    assert 'timing_swing' in transport
    assert 'timing_humanize' in transport
    assert 'timing_offset' in transport


def test_core_supports_timing_mutation_target():
    source = (ROOT / "auricle_engine.py").read_text(encoding="utf-8")
    assert 'run("timing", representation.duration)' in source
