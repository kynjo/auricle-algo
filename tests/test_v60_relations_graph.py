"""Behavioral checks for the current inline relation editor."""
import pytest
from test_inline_editors import window, editor, drain


def test_duplicate_delete_and_stale_callbacks_keep_the_right_relation(editor):
    gui, app, win, panel = editor
    import shiboken6

    win.add_relation(); drain(app)
    first = panel.rows[0]
    first.curve.setCurrentText("Exponential")
    first.amount.setValue(.73)
    first.duplicate.click()
    drain(app)
    second = panel.rows[1]
    assert second.relation.id != first.relation.id
    assert second.relation.curve == "Exponential"
    assert second.relation.amount == pytest.approx(.73)
    first.remove.click()
    assert shiboken6.isValid(first)  # no native widget deletion in its own signal
    assert win.project.relations == [second.relation]
    first.amount.setValue(.1)  # late event from a removed row must be ignored
    assert second.relation.amount == pytest.approx(.73)
    drain(app)
    assert panel.rows == [second]
    second.amount.setValue(.24)
    assert win.project.relations[0].amount == pytest.approx(.24)

