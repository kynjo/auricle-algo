from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]/"auricle_gui.py"

def test_relation_filter_and_validation_exist():
    s=SOURCE.read_text(encoding="utf-8")
    block=s[s.index("class RelationGraphEditor"):s.index("class RelationEditor")]
    assert "Filter relations" in block and "def _apply_filter" in block and "def validate_relations" in block

def test_relation_ids_are_assigned_for_new_relations():
    s=SOURCE.read_text(encoding="utf-8")
    assert 'relation.id = next_relation_id(self.project)' in s
