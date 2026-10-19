"""Behavioral checks for the current inline relation editor."""
import pytest
from test_inline_editors import window, editor, drain
from auricle_core import Block, Project


def test_add_relation_immediately_creates_an_editable_row(editor):
    gui, app, win, panel = editor
    panel.add_button.click()
    assert len(win.project.relations) == 1
    drain(app)
    relation = win.project.relations[0]
    assert relation.source_block != relation.destination_block
    assert relation.id > 0
    assert len(panel.rows) == 1
    assert not hasattr(panel, "table")
    assert panel.rows[0].relation is relation
    assert panel.rows[0].source.isEnabled()
    assert win._dirty



def test_pending_add_does_not_reintroduce_rows_after_project_switch(editor):
    gui, app, win, panel = editor
    win.add_relation()
    replacement = Project(blocks=[Block(22, "Only block", "MELODY", "Pattern")])
    win._install_project(replacement, None, "Replacement")
    drain(app)
    assert panel.project is replacement
    assert not panel.rows
    assert not panel.add_button.isEnabled()

