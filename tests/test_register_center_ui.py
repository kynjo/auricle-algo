"""Register automation is visible on Center, with manual Transpose untouched."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from parameter_sources_ui import ParameterSourceLabel

from test_kit_preview_lifecycle import inspector


def knob(gui, win, block_id, key):
    return next(widget for widget in win.findChildren(gui.Knob)
                if getattr(widget, "_auricle_parameter", None) == (block_id, key))


def label(win, block_id, key):
    return next(widget for widget in win.findChildren(ParameterSourceLabel) if widget.binding == (block_id, key))


def test_composition_exposes_register_center_and_disables_it_for_drum_voices(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.composition_panel
    columns = [panel.block_table.horizontalHeaderItem(i).text() for i in range(panel.block_table.columnCount())]
    assert "Register Center" in columns and "Transpose" not in columns
    assert not panel.block_table.cellWidget(0, 4).isEnabled()
    last = panel.block_table.rowCount() - 1
    assert panel.block_table.cellWidget(last, 4).isEnabled()
    panel.block_table.cellWidget(last, 4).setValue(12)
    assert panel._selected_section()["blocks"][str(melody.id)]["register_center"] == 12
    assert "Register Center" in panel.parameter_list.text()
    assert "Transpose" not in panel.parameter_list.text()
    assert not errors


def test_composition_and_perform_move_center_needle_and_leave_transpose_needle_at_manual_value(inspector):
    gui, win, drum, melody, errors = inspector
    win.selected_block_id = melody.id
    win._refresh_inspector()
    center = knob(gui, win, melody.id, "role_center")
    transpose = knob(gui, win, melody.id, "transpose")
    manual_center, manual_transpose = center.value(), transpose.value()
    section = win.project.composition["sections"][0]
    section["blocks"][str(melody.id)]["register_center"] = 12.
    win.project.composition["enabled"] = True
    win._update_parameter_sources(force=True)
    assert center.displayValue() == manual_center + 12
    assert transpose.displayValue() == manual_transpose
    assert win.engine.performance.start(melody, "register_rise", beats=8)
    win.engine.performance.tick(True, beat_delta=4)
    win._update_parameter_sources(force=True)
    assert center.value() == manual_center
    assert center.displayValue() == manual_center + 18
    assert transpose.displayValue() == manual_transpose
    assert {mark.source for mark in label(win, melody.id, "role_center").source_marks} == {"Perform", "Composition"}
    assert not label(win, melody.id, "transpose").source_marks
    assert "Effective register center" in label(win, melody.id, "role_center").toolTip()
    win.project.composition["enabled"] = False
    win.engine.performance.stop(melody.id)
    win._update_parameter_sources(force=True)
    assert center.displayValue() == manual_center
    assert transpose.displayValue() == manual_transpose
    assert not errors


def test_register_center_section_edit_participates_in_undo_redo(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.composition_panel
    row = panel.block_table.rowCount() - 1
    win.history_controller.reset()
    panel.block_table.cellWidget(row, 4).setValue(12)
    win.history_controller.flush()
    assert win.project.composition["sections"][0]["blocks"][str(melody.id)]["register_center"] == 12
    win.history_controller.move()
    QTest.qWait(20)
    assert panel.block_table.cellWidget(row, 4).value() == 0
    win.history_controller.move(True)
    QTest.qWait(20)
    assert panel.block_table.cellWidget(row, 4).value() == 12
    assert not errors
