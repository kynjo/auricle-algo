from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]/"auricle_gui.py"

def test_relation_inspector_exposes_transform_controls():
    s=SOURCE.read_text(encoding="utf-8")
    block=s[s.index("class RelationGraphEditor"):s.index("class RelationEditor")]
    for token in ["self.curve", "self.delay", "self.probability", "self.enabled", "duplicate_selected_relation"]:
        assert token in block

def test_relation_table_has_state_column():
    s=SOURCE.read_text(encoding="utf-8")
    assert 'COLUMNS = ("", "Source", "Output", "Operation", "Destination", "Input", "Amount", "State")' in s
