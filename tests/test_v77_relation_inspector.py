"""Behavioral checks for the current inline relation inspector."""
from test_inline_editors import window, editor, drain
from auricle_persistence import load_project


def test_relation_fields_update_model_and_output_without_rebuilding(editor):
    gui, app, win, panel = editor
    win.add_relation(); drain(app)
    row = panel.rows[0]
    row.source.setCurrentIndex(row.source.findData(3))
    row.dest.setCurrentIndex(row.dest.findData(4))
    row.source_part.setCurrentText("velocity")
    row.dest_part.setCurrentText("velocity")
    row.algorithm.setCurrentText("Copy")
    row.amount.setValue(1)
    row.curve.setCurrentText("Linear")
    row.delay.setCurrentIndex(row.delay.findData(2))
    row.probability.setValue(.75)
    row.enabled.setChecked(False)
    relation = row.relation
    assert (relation.source_block, relation.destination_block) == (3, 4)
    assert (relation.source_part, relation.destination_part) == ("velocity", "velocity")
    assert (relation.amount, relation.delay, relation.probability, relation.enabled) == (1, 2, .75, False)
    row.probability.setValue(1)
    row.delay.setCurrentIndex(0)
    row.enabled.setChecked(True)
    assert win.get_block(4).outputs["velocity"] == win.get_block(3).outputs["velocity"]
    assert panel.rows[0] is row



def test_inline_relations_persist_all_fields(editor, tmp_path):
    gui, app, win, panel = editor
    win.add_relation(); drain(app)
    row = panel.rows[0]
    row.curve.setCurrentText("Threshold")
    row.delay.setCurrentIndex(row.delay.findData(8))
    row.algorithm.setCurrentText("Modulate")
    row.amount.setValue(.27)
    row.probability.setValue(.62)
    row.enabled.setChecked(False)
    path = tmp_path / "inline.json"
    assert win._write_project(str(path))
    original = row.relation
    restored = load_project(str(path))
    assert restored.relations == [original]
    win._install_project(restored, str(path), "Restored")
    drain(app)
    row = panel.rows[0]
    assert row.curve.currentText() == "Threshold"
    assert row.delay.currentData() == 8
    assert not row.enabled.isChecked()
    assert not win._dirty

