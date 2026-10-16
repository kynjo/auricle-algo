from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"


def _class_block(source, name, next_name):
    start = source.index(f"class {name}")
    end = source.index(f"class {next_name}", start)
    return source[start:end]


def test_inspector_group_does_not_use_qgroupbox_checkable_state():
    source = SOURCE.read_text()
    block = _class_block(source, "InspectorGroup(QGroupBox):", "LayerGroup(QGroupBox):")
    assert "self.setCheckable(False)" in block
    assert "accordion_toggled = Signal(bool)" in block
    assert "self.accordion_toggled.emit(self._expanded)" not in block
    assert "Non-collapsible nested inspector group" in block


def test_layer_group_does_not_use_qgroupbox_checkable_state():
    source = SOURCE.read_text()
    block = _class_block(source, "LayerGroup(QGroupBox):", "PatchNode")
    assert "self.setCheckable(False)" in block
    assert "accordion_toggled = Signal(bool)" in block
    assert "self.accordion_toggled.emit(self._expanded)" in block


def test_inspector_refresh_uses_accordion_signal_not_qgroupbox_toggled():
    source = SOURCE.read_text()
    start = source.index("    def _refresh_inspector(")
    end = source.index("    def _remember_group", start)
    block = source[start:end]
    assert ".accordion_toggled.connect" in block
    assert ".toggled.connect(lambda checked" not in block
