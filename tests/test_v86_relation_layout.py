from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"

def test_relation_inspector_uses_single_horizontal_editor_row():
    s = SOURCE.read_text(encoding="utf-8")
    block = s[s.index("class RelationGraphEditor"):s.index("class RelationEditor")]
    assert "row = QHBoxLayout()" in block
    assert 'add_field("Source", self.source' in block
    assert 'add_field("Output", self.source_part' in block
    assert 'add_field("Operation", self.algorithm' in block
    assert 'add_field("Destination", self.dest' in block
    assert 'add_field("Input", self.dest_part' in block
    assert 'add_field("Amount", self.amount' in block
    assert 'add_field("Curve", self.curve' in block
    assert 'add_field("Delay", self.delay' in block
    assert 'add_field("Probability", self.probability' in block
    assert "state_cell = QVBoxLayout()" in block

def test_relation_inspector_no_longer_uses_vertical_form_rows():
    s = SOURCE.read_text(encoding="utf-8")
    block = s[s.index("class RelationGraphEditor"):s.index("class RelationEditor")]
    assert 'form = QFormLayout(inspector_box)' not in block
    assert 'form.addRow("Source block"' not in block
