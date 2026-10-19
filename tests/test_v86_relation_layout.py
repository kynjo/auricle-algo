"""Behavioral checks for the current inline relation inspector."""
from test_inline_editors import window, editor, drain
from auricle_persistence import load_project


def test_new_relation_scrolls_into_view_and_mutator_knob_fits(editor):
    gui, app, win, panel = editor
    win.resize(1250, 760)
    win.tabs.setCurrentIndex(2)
    win.show()
    for _ in range(7):
        panel.add_button.click()
        drain(app)
    row = panel.rows[-1]
    bottom = row.mapTo(panel.scroll.viewport(), row.rect().bottomRight()).y()
    assert bottom <= panel.scroll.viewport().height()
    assert panel.scroll.verticalScrollBar().value() > 0
    win.tabs.setCurrentIndex(0)
    win._inspector_state[(win.selected_block_id, "MOTION")] = True
    win.add_mutator()
    drain(app)
    row = win.inspector_page.findChild(gui.MutatorInlineControls)
    assert row.height() >= row.amount.height()
    assert row.amount.geometry().bottom() < row.height()
    win.hide()

