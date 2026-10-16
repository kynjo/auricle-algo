from pathlib import Path

GUI_SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"


def _source():
    return GUI_SOURCE.read_text(encoding="utf-8")


def test_collapsed_layer_applies_visibility_after_content_is_attached():
    source = _source()
    start = source.index("def make_layer")
    end = source.index("# BLOCK identity", start)
    block = source[start:end]
    assert "layer._apply_children_visibility()" in block


def test_midi_controls_live_in_block_header():
    source = _source()
    header = source[source.index("# BLOCK identity"):source.index("# SOURCE")]
    assert 'header_label("MIDI Ch")' in header
    assert 'header_label("Base note")' in header
    assert 'header_label("MIDI Out")' in header
    assert 'make_layer("OUTPUT"' not in source


def test_inspector_knob_cells_are_wide_enough_for_labels():
    source = _source()
    musical = source[source.index("# MUSICAL"):source.index("# MOTION")]
    structure = source[source.index("# STRUCTURE"):source.index("# MUSICAL")]
    assert "cell.setFixedWidth(74)" in musical
    assert "cell.setFixedWidth(74)" in structure


def test_mutator_rows_have_room_for_knob_value():
    source = _source()
    motion = source[source.index("# MOTION"):source.index("# MONITOR / diagnostics")]
    assert "wrapper.setMinimumHeight(78)" in motion
    assert "QSizePolicy.Expanding, QSizePolicy.Fixed" in motion


def test_add_buttons_share_the_same_style_object():
    source = _source()
    motion = source[source.index("# MOTION"):source.index("# MONITOR / diagnostics")]
    assert motion.count('setObjectName("inspectorAddButton")') == 2
    assert 'setFixedHeight(26)' in motion
    theme_source = (Path(__file__).resolve().parents[1] / 'ui_themes.py').read_text(encoding='utf-8')
    assert 'QPushButton#inspectorAddButton' in theme_source


def test_accordion_groups_have_explicit_child_visibility_helper():
    source = _source()
    for cls in ("InspectorGroup(QGroupBox):", "LayerGroup(QGroupBox):"):
        start = source.index(f"class {cls}")
        end = source.find("class ", start + len(cls))
        block = source[start:end if end != -1 else len(source)]
        assert "def _apply_children_visibility" in block
        assert "self._apply_children_visibility()" in block
