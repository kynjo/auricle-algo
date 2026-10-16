from pathlib import Path

GUI_SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"


def test_relation_parameters_have_visible_table_columns():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    assert 'COLUMNS = ("", "Source", "Output", "Operation", "Destination", "Input", "Amount", "State")' in source


def test_relation_editor_has_single_inspector():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    assert 'QGroupBox("RELATION INSPECTOR")' in source
    assert 'form.addRow("Source block", self.source)' in source
    assert 'form.addRow("Destination block", self.dest)' in source
    assert 'form.addRow("Amount", self.amount)' in source


def test_relation_block_position_compatibility_hook_remains_safe():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    assert 'def forget_block_position(self, block_id):' in source
    assert 'return None' in source
    assert 'self.relation_graph.forget_block_position(b.id)' in source
