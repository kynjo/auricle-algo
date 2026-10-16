from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"


def test_relations_are_not_node_widgets():
    source = SOURCE.read_text(encoding="utf-8")
    assert "class RelationNode" not in source
    assert "class RelationBlockNode" not in source
    assert "class RelationPort" not in source
    assert "QGraphicsProxyWidget" not in source


def test_relations_use_model_table_and_single_inspector():
    source = SOURCE.read_text(encoding="utf-8")
    assert "class RelationGraphEditor(QWidget):" in source
    assert "QTableWidget" in source
    assert '"RELATION INSPECTOR"' in source
    assert "self.table.setSelectionBehavior(QAbstractItemView.SelectRows)" in source


def test_relation_delete_is_model_first_and_deferred_refresh():
    source = SOURCE.read_text(encoding="utf-8")
    block = source[source.index("def delete_selected_relation"):source.index("def delete_relation", source.index("def delete_selected_relation"))]
    assert "remove_relation(self.project, index)" in block
    assert "self.host.engine.generate()" in block
    assert "QTimer.singleShot(0" in block


def test_relation_editor_has_no_embedded_graph_widgets():
    source = SOURCE.read_text(encoding="utf-8")
    assert "QGraphicsProxyWidget(self)" not in source
    assert "relation_nodes" not in source
    assert "rebuild_edges_only" not in source


def test_current_version_is_sequential():
    version = (Path(__file__).resolve().parents[1] / "version.py").read_text(encoding="utf-8")
    assert __import__("re").search(r'APP_VERSION = "v110"', version)


def test_relation_amount_uses_paramknob_signal():
    source = SOURCE.read_text(encoding="utf-8")
    block = source[source.index("class RelationGraphEditor"):source.index("class RelationEditor")]
    assert "self.amount.changed.connect(self._inspector_changed)" in block
    assert "self.amount.valueChanged" not in block
