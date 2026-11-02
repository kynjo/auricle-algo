"""Assignments, exact point editing, retained controls and immediate save."""
from copy import deepcopy

import pytest
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from auricle_core import Block, Project
from auricle_persistence import load_project
from parameter_sources_ui import ParameterSourceLabel
from parameter_influence_ui import InfluenceDialog
from test_kit_preview_lifecycle import inspector


def commit(win):
    win.composition_panel.automation_panel.flush()
    win.transport.flush_gui_commands(notify=True)


def test_knob_and_caption_assign_once_without_starting_playback(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    win.selected_block_id = melody.id
    win._refresh_inspector()
    knob = next(w for w in win.inspector_page.findChildren(gui.Knob)
                if getattr(w, '_auricle_parameter', None) == (melody.id, 'gate'))
    def choose_automation():
        menu = QApplication.activePopupWidget()
        action = next(a for a in menu.actions() if a.text().startswith('Automate'))
        menu.setActiveAction(action)
        QTest.keyClick(menu, Qt.Key_Return)
    event = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(2, 2), QPoint(2, 2))
    QTimer.singleShot(0, choose_automation)
    knob.contextMenuEvent(event)
    panel = win.composition_panel.automation_panel
    assert win.tabs.currentWidget() is win.composition_panel
    assert win.composition_panel.composition_tabs.currentWidget() is panel
    commit(win)
    assert len(win.project.composition['sections'][0]['parameter_automation']) == 1
    label = next(w for w in win.inspector_page.findChildren(ParameterSourceLabel) if w.binding == (melody.id, 'gate'))
    QTimer.singleShot(0, choose_automation)
    label.contextMenuEvent(event)
    commit(win)
    assert panel.table.rowCount() == 1 and not win.transport.running
    assert not errors


def test_existing_destination_reselects_row_and_filters_preserve_all_tracks(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.composition_panel.automation_panel
    for owner, key in ((melody, 'gate'), (melody, 'transpose'), (drum.drum_voices[0], 'fill_density')):
        assert panel.assign(owner.id, key)
    assert panel.table.currentRow() == 2
    panel.assign(melody.id, 'gate')
    assert panel.table.currentRow() == 0 and panel.track()['parameter'] == 'gate'
    panel.search.setText('transpose')
    assert panel.table.rowCount() == 1
    assert len(panel.planner._selected_section()['parameter_automation']) == 3
    panel.assign(melody.id, 'gate')
    assert panel.table.rowCount() == 3
    panel.remove_selected(); commit(win)
    assert len(win.project.composition['sections'][0]['parameter_automation']) == 2
    assert not errors


def test_exact_curve_points_source_feedback_and_save_before_coalescer(inspector, tmp_path):
    gui, win, drum, melody, errors = inspector
    win._assign_composition_automation(melody.id, 'gate')
    panel = win.composition_panel.automation_panel
    win.show()
    panel.mode.setCurrentIndex(panel.mode.findData('curve'))
    panel.low.setValue(.1); panel.high.setValue(1.1); panel._range_changed()
    panel._preset_curve(False)
    editor = panel.curve
    editor.resize(600, 104)
    QTest.mouseDClick(editor, Qt.LeftButton, pos=editor.point_position((.5, .6)).toPoint())
    assert len(panel.track()['curve']['points']) == 3
    panel.point_beat.setValue(7.25); panel.point_value.setValue(.75)
    points = panel.track()['curve']['points']
    assert points[1] == pytest.approx([7.25 / 32, .65])
    path = tmp_path / 'automation.json'
    assert win._write_project(path)
    saved = load_project(path)
    assert saved.composition['sections'][0]['parameter_automation'][0]['curve']['points'] == points
    win.project.composition['enabled'] = True
    win.engine.composition_runtime.playback_active = True
    win.transport.playback_mode = 'composition'; win.transport.running = True
    win.engine.clock.position_beats = 7.25
    win.engine.section_automation.advance(7.25)
    panel.update_runtime(); win._update_parameter_sources(force=True)
    assert 'active' in panel.table.item(0, 4).text()
    assert 'Manual' in panel.live.text() and 'Effective' in panel.live.text()
    assert win.engine.parameter_influence.base_value(melody, 'gate', .78) == .78
    win.engine.section_automation.reset(); win.transport.running = False
    assert not errors


def test_undo_redo_and_pending_edit_do_not_leak_to_replacement_project(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.composition_panel.automation_panel
    panel.assign(melody.id, 'gate'); commit(win)
    win.history_controller.reset()
    before = deepcopy(panel.track())
    panel.value.setValue(.31); commit(win); win.history_controller.flush()
    assert win.history_controller.history.can_undo
    win.history_controller.move()
    assert win.project.composition['sections'][0]['parameter_automation'][0] == before
    win.history_controller.move(True)
    assert win.project.composition['sections'][0]['parameter_automation'][0]['value'] == .31
    panel.value.setValue(.44)
    replacement = Project(blocks=[Block(2, 'Other', 'MELODY')])
    win._install_project(replacement, None, 'Replacement')
    panel.flush(); win.transport.flush_gui_commands()
    assert not any(s.get('parameter_automation') for s in replacement.composition['sections'])
    assert not errors


def test_editor_geometry_retains_table_and_curve_and_discrete_dialog_is_safe(inspector):
    gui, win, drum, melody, errors = inspector
    win._assign_composition_automation(melody.id, 'gate')
    panel = win.composition_panel.automation_panel
    panel.mode.setCurrentIndex(panel.mode.findData('curve'))
    win.show()
    for width in (820, 1100, 1440):
        win.resize(width, 900); QTest.qWait(30)
        assert win.width() == width
        assert panel.table.horizontalScrollBar().maximum() == 0
        assert panel.curve.height() == 104 and panel.curve.width() > 140
        table = panel.table
        for _ in range(5): panel.update_runtime()
        assert panel.table is table
    melody.mode = 'LIVE'
    dialog = InfluenceDialog(win, melody.id, '@algorithm')
    assert 'Pattern' in dialog.values.text()
    dialog.close(); dialog.deleteLater()
    assert not errors
