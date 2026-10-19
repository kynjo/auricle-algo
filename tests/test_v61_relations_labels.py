"""Behavioral checks for the current inline relation editor."""
import pytest
from test_inline_editors import window, editor, drain


def test_block_colours_and_names_refresh_in_both_endpoint_lists(editor):
    gui, app, win, panel = editor
    win.add_relation(); drain(app)
    row = panel.rows[0]
    win._dirty = False
    panel.rebuild(win.project)
    assert not win._dirty
    for combo in (row.source, row.dest):
        for index, block in enumerate(win.project.blocks):
            assert combo.itemIcon(index).pixmap(12, 12).toImage().pixelColor(6, 6).name() == gui.block_color(win.project, block)
    block = win.project.blocks[0]
    win._card_color_changed(block.id, "#2ac789")
    drain(app)
    win._rename_block(block, "My drums")
    assert panel.rows[0] is row
    for combo in (row.source, row.dest):
        index = combo.findData(block.id)
        assert combo.itemText(index) == "My drums"
        assert combo.itemIcon(index).pixmap(12, 12).toImage().pixelColor(6, 6).name() == "#2ac789"
    assert row.source.currentData() == block.id

