from pathlib import Path

GUI_SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"


def test_inspector_has_five_user_facing_layers():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    for layer in ("SOURCE", "STRUCTURE", "MUSICAL", "MOTION", "MONITOR"):
        assert f'make_layer("{layer}"' in source or f'"{layer}",' in source
    assert 'make_layer("MONITOR"' in source


def test_structure_owns_universal_density_and_probability():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    structure = source[source.index('# STRUCTURE'):source.index('# MUSICAL')]
    source_layer = source[source.index('# SOURCE'):source.index('# STRUCTURE')]
    assert '"fill_density"' in structure
    assert '"event_probability"' in structure
    assert 'add_fill_density()' not in source_layer
    assert 'Event Probability' not in source_layer


def test_musical_layer_exposes_common_scale_and_pitch_controls():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    musical = source[source.index('# MUSICAL'):source.index('# MOTION')]
    for key in ('scale_root', 'scale_name', 'transpose', 'octave'):
        assert f'"{key}"' in musical


def test_motion_contains_mutation_and_process_sections():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    motion = source[source.index('# MOTION'):source.index('# MONITOR / diagnostics')]
    assert 'InspectorGroup("MUTATION"' in motion
    assert 'InspectorGroup("PROCESS"' in motion
    assert 'ProcessInlineControls' in motion


def test_output_layer_is_removed_and_midi_routing_stays_in_block_header():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    header = source[source.index('# BLOCK identity'):source.index('# SOURCE')]
    monitor = source[source.index('# MONITOR / diagnostics'):source.index('    def _remember_group')]
    assert 'make_layer("OUTPUT"' not in source
    assert 'InspectorGroup("OUTPUT PORTS"' not in source
    assert 'header_label("MIDI Ch")' in header
    assert 'header_label("Base note")' in header
    assert 'header_label("MIDI Out")' in header
    assert 'MIDI PIANO ROLL' in monitor
    assert 'BlockStatePanel' not in monitor
