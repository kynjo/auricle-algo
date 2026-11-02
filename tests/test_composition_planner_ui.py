"""Optional offscreen Qt checks for the Composition Planner editor."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QModelIndex, QRect, QPoint
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtWidgets import QApplication, QWidget, QComboBox, QStyleOptionViewItem, QStyle, QAbstractItemView
from PySide6.QtTest import QTest
from threading import RLock

from auricle_model import Block, Project, ensure_drum_voices
from auricle_engine import MusicEngine
from composition_planner_ui import CompositionPlannerPanel
from composition_planner import make_section
from ui_themes import theme_names, theme_palette, mix, contrast_ratio
from test_kit_preview_lifecycle import inspector


class _Transport:
    def __init__(self):
        self._state_lock = RLock()
        self.running = False
        self.playback_mode = "composition"
        self.composition_position = 0.0
        self.released = []

    def _release_block_notes(self, block_id):
        self.released.append(int(block_id))


class _Host(QWidget):
    def __init__(self):
        super().__init__()
        drum = Block(1, "KIT", "DRUM")
        ensure_drum_voices(drum)
        melody = Block(2, "LEAD", "MELODY")
        self.project = Project(blocks=[drum, melody])
        self.engine = MusicEngine(self.project)
        self.transport = _Transport()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Midnight", "Solar"])
        self.dirty_count = 0
        self.messages = []

    def _mark_dirty(self):
        self.dirty_count += 1

    def set_message(self, message):
        self.messages.append(str(message))


def _app():
    return QApplication.instance() or QApplication([])


def test_composition_tab_has_all_eight_types_and_individual_drum_voice_rows():
    _app()
    host = _Host()
    panel = CompositionPlannerPanel(host)
    assert panel.section_type.count() == 8
    assert panel.section_list.count() == 1
    assert panel.block_table.rowCount() == 7  # six voices plus melody
    labels = [panel.block_table.item(row, 0).text() for row in range(panel.block_table.rowCount())]
    assert any("KICK" in label for label in labels)
    assert any("LEAD" in label for label in labels)


def test_add_duplicate_reorder_remove_and_per_block_edit_persist_to_project():
    _app()
    host = _Host()
    panel = CompositionPlannerPanel(host)
    panel.section_type_add.setCurrentText("Build")
    panel.add_button.click()
    assert len(host.project.composition["sections"]) == 2
    assert host.project.composition["sections"][1]["type"] == "Build"
    panel.duplicate_button.click()
    assert len(host.project.composition["sections"]) == 3
    panel.up_button.click()
    assert panel.section_list.currentRow() == 1
    density = panel.block_table.cellWidget(0, 2)
    density.setValue(.35)
    selected = host.project.composition["sections"][panel.section_list.currentRow()]
    block_id = str(panel.block_table.item(0, 0).data(Qt.UserRole))
    assert selected["blocks"][block_id]["density"] == pytest.approx(.35)
    panel.remove_button.click()
    assert len(host.project.composition["sections"]) == 2
    assert host.dirty_count >= 4


def test_enabling_composition_regenerates_source_without_density_pruning():
    _app()
    host = _Host()
    panel = CompositionPlannerPanel(host)
    panel.enabled.setChecked(True)
    assert host.project.composition["enabled"] is True
    assert host.engine.composition_runtime.enabled() is True


def _form(panel, host):
    host.project.composition["sections"] = [
        make_section("Intro", bars=2), make_section("Build", bars=4), make_section("Drop", bars=6),
    ]
    panel.sync_from_project()
    return host.project.composition["sections"]


def test_internal_drag_move_preserves_selected_section_and_its_settings(tmp_path):
    from auricle_persistence import save_project, load_project

    _app()
    host = _Host()
    panel = CompositionPlannerPanel(host)
    sections = _form(panel, host)
    sections[0]["blocks"]["2"]["density"] = .37
    selected_id = sections[0]["id"]
    panel.section_list.setCurrentRow(0)
    assert panel.section_list.dragDropMode() == QAbstractItemView.InternalMove
    assert panel.section_list.defaultDropAction() == Qt.MoveAction
    # InternalMove uses this native model operation when the drop is accepted.
    assert panel.section_list.model().moveRows(QModelIndex(), 0, 1, QModelIndex(), 3)
    _app().processEvents()
    reordered = host.project.composition["sections"]
    assert [section["id"] for section in reordered] == [sections[1]["id"], sections[2]["id"], selected_id]
    assert panel.section_list.currentItem().data(Qt.UserRole) == selected_id
    assert panel._selected_section()["blocks"]["2"]["density"] == .37
    assert panel.section_name.text() == sections[0]["name"]
    assert [panel.section_list.item(i).text().split()[0] for i in range(3)] == ["01", "02", "03"]
    assert host.dirty_count == 1
    path = tmp_path / "form.json"
    save_project(host.project, str(path))
    assert load_project(str(path)).composition == host.project.composition


def test_drag_reorder_is_one_undo_redo_edit(inspector):
    _gui, win, _drum, _melody, errors = inspector
    panel = win.composition_panel
    sections = _form(panel, win)
    original = [section["id"] for section in sections]
    win.history_controller.reset()
    assert panel.section_list.model().moveRows(QModelIndex(), 0, 1, QModelIndex(), 3)
    QTest.qWait(15)
    win.history_controller.flush()
    assert [s["id"] for s in win.project.composition["sections"]] == original[1:] + original[:1]
    assert win.history_controller.history.index == 1
    win.history_controller.move()
    QTest.qWait(15)
    assert [s["id"] for s in win.project.composition["sections"]] == original
    win.history_controller.move(True)
    QTest.qWait(15)
    assert [s["id"] for s in win.project.composition["sections"]] == original[1:] + original[:1]
    assert not errors


@pytest.mark.parametrize("name", theme_names())
def test_selected_section_text_is_visible_in_every_theme(name):
    _app()
    host = _Host()
    host.theme_combo.addItems([name])
    host.theme_combo.setCurrentText(name)
    panel = CompositionPlannerPanel(host)
    theme = theme_palette(name)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 180, 62)
    option.state = QStyle.State_Selected | QStyle.State_Enabled | QStyle.State_Active
    pixmap = QPixmap(option.rect.size())
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    panel.section_delegate.paint(painter, option, panel.section_list.model().index(0, 0))
    painter.end()
    image = pixmap.toImage()
    # Test rendered text pixels as well as the calculated colour contrast.
    assert sum(image.pixelColor(x, y).name() == theme.text
               for x in range(24, 160) for y in range(9, 30)) > 10
    assert contrast_ratio(theme.text, mix(theme.card, theme.accent, .18)) >= 4.5
    assert panel.timeline.theme == theme


@pytest.mark.parametrize("meter,beats,seconds", [("4/4", 48, "0:24"), ("6/8", 36, "0:18"), ("7/8", 42, "0:21")])
def test_total_length_and_timeline_use_whole_form_meter_and_bpm(meter, beats, seconds):
    _app()
    host = _Host()
    panel = CompositionPlannerPanel(host)
    _form(panel, host)
    panel.meter.setCurrentText(meter)
    assert f"12 bars · {beats} beats · {seconds}" in panel.total_label.text()
    assert panel.timeline.total_bars == 12
    assert not hasattr(panel, "progress")
    host.project.tempo = 60
    panel.update_runtime()
    assert "60 BPM" in panel.total_label.text()
    host.project.composition["enabled"] = True
    host.transport.running = True
    host.engine.clock.position_beats = beats / 2
    panel.update_runtime()
    assert panel.timeline.progress == pytest.approx(.5)
    assert panel.timeline.running
    # Ruler wraps per form; loop count is separate from the bar denominator.
    host.engine.clock.position_beats = beats * 1.25
    panel.update_runtime()
    assert panel.timeline.progress == pytest.approx(.25)
    assert "loop 2" in panel.position_label.text()
    panel.ending.setCurrentIndex(panel.ending.findData("hold"))
    host.engine.clock.position_beats = beats * 2
    panel.update_runtime()
    assert panel.timeline.progress == 1
    assert "bar 12/12" in panel.position_label.text()


def test_name_duration_edits_refresh_full_form_and_selected_timeline_section():
    _app()
    host = _Host()
    panel = CompositionPlannerPanel(host)
    _form(panel, host)
    panel.section_list.setCurrentRow(1)
    panel.section_bars.setValue(8)
    panel.section_name.setText("Long build")
    panel._commit_name()
    assert "16 bars" in panel.total_label.text()
    assert panel.timeline.sections[1][1:3] == ("Long build", 8)
    assert panel.timeline.selected_id == host.project.composition["sections"][1]["id"]


@pytest.mark.parametrize("size", [(1250, 850), (820, 720), (820, 520)])
def test_compact_layout_keeps_timeline_clear_and_captions_next_to_fields(inspector, size):
    _gui, win, _drum, _melody, errors = inspector
    panel = win.composition_panel
    win.tabs.setCurrentWidget(panel)
    _form(panel, win)
    win.resize(*size)
    win.show()
    QTest.qWait(30)
    for label, field in ((panel.name_label, panel.section_name), (panel.type_label, panel.section_type),
                         (panel.duration_label, panel.section_bars)):
        assert label.parentWidget() is field.parentWidget()
        if panel.editor_scroll.viewport().width() >= 1050:
            assert 0 <= field.x() - label.geometry().right() <= 8
        else:
            assert 0 <= field.y() - label.geometry().bottom() <= 5
            assert abs(label.x() - field.x()) <= 1
    scroll_bottom = panel.editor_scroll.mapTo(panel, panel.editor_scroll.rect().bottomLeft()).y()
    status_top = panel.status.mapTo(panel, QPoint(0, 0)).y()
    assert scroll_bottom < status_top
    assert panel.section_list.geometry().bottom() < panel.timeline.y()
    assert panel.timeline.geometry().bottom() < panel.macros_group.y()
    assert panel.editor.width() <= panel.editor_scroll.viewport().width()
    assert panel.timeline.width() > panel.width() * .9
    assert not errors
