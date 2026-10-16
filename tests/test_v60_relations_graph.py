from pathlib import Path

GUI_SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"


def test_relations_graph_is_no_longer_node_based():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    assert "class RelationNode" not in source
    assert "class RelationBlockNode" not in source
    assert "class RelationPort" not in source
    assert "QGraphicsProxyWidget" not in source


def test_relations_editor_uses_table_selection():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    assert "QTableWidget" in source
    assert "self.table.setSelectionBehavior(QAbstractItemView.SelectRows)" in source
    assert "self.table.itemSelectionChanged.connect(self._selection_changed)" in source


def test_relation_delete_is_not_tied_to_graphic_node_teardown():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    block = source[source.index("def delete_selected_relation"):source.index("def delete_relation", source.index("def delete_selected_relation"))]
    assert "remove_relation(self.project, index)" in block
    assert "QTimer.singleShot(0" in block
