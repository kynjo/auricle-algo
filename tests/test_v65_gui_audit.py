from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"


def _class_block(source, name, next_name):
    start = source.index(f"class {name}")
    end = source.index(f"class {next_name}", start)
    return source[start:end]


def test_no_global_groupbox_indicator_hack():
    source = SOURCE.read_text()
    assert "QGroupBox::indicator" not in source


def test_layer_group_passes_title_to_qgroupbox():
    source = SOURCE.read_text()
    block = _class_block(source, "LayerGroup(QGroupBox):", "PatchNode")
    assert "super().__init__(title, parent)" in block


def test_accordion_state_is_idempotent():
    source = SOURCE.read_text()
    block = _class_block(source, "InspectorGroup(QGroupBox):", "LayerGroup(QGroupBox):")
    assert "self._expanded = True" in block
    layer = _class_block(source, "LayerGroup(QGroupBox):", "PatchNode")
    assert "if expanded == self._expanded:" in layer
    assert "self._expanded = expanded" in layer


def test_stop_is_not_a_checkable_state_button():
    source = SOURCE.read_text()
    assert 'self.stop = QPushButton("STOP"); self.stop.setObjectName("transportStop")' in source
    assert 'self.stop.setCheckable(True)' not in source
    assert 'self.stop.setChecked(not running)' not in source


def test_midi_inspector_updates_without_active_block_list_rebuild():
    source = SOURCE.read_text()
    start = source.index("    def _set_channel(")
    end = source.index("    def randomize_parameter", start)
    block = source[start:end]
    assert "if self.selected_block_id == b.id:" in block
    assert "self._refresh_inspector()" in block
