"""Behavioral checks for the current inline relation inspector."""
from test_inline_editors import window, editor, drain
from auricle_persistence import load_project


def test_filter_add_and_empty_state(editor):
    gui, app, win, panel = editor
    win.add_relation(); drain(app)
    panel.filter_edit.setText("no match")
    assert panel.rows[0].isHidden()
    assert not panel.empty.isHidden()
    panel.add_button.click(); drain(app)
    assert panel.filter_edit.text() == ""
    assert all(not row.isHidden() for row in panel.rows)
    for row in list(panel.rows):
        row.remove.click()
    drain(app)
    assert not panel.rows
    assert not win.project.relations
    assert not panel.empty.isHidden()

