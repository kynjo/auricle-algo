"""Native editing, selection, transport and adaptive layout of the merged page."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from copy import deepcopy

import pytest
pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

from composition_planner import make_section, section_color
from test_kit_preview_lifecycle import inspector


def prepare(win, monkeypatch):
    monkeypatch.setattr(win.transport, "refresh_ports", lambda: None)
    win.project.composition.update(enabled=True, sections=[make_section(kind, bars=2, neutral=True) for kind in ("Build", "Drop")])
    panel = win.composition_panel
    panel.sync_from_project()
    win.tabs.setCurrentWidget(panel)
    win.history_controller.reset()
    return panel


def test_one_tab_contains_phrase_curves_instruments_and_shared_panels(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    panel = prepare(win, monkeypatch)
    assert [win.tabs.tabText(i) for i in range(win.tabs.count())] == ["BLOCKS", "COMPOSITION", "RELATIONS", "MIDI MONITOR", "HELP"]
    assert [panel.composition_tabs.tabText(i) for i in range(panel.composition_tabs.count())] == [
        "SECTION", "INSTRUMENTS", "GLOBAL", "AUTOMATION"
    ]
    assert panel.composition_tabs.currentWidget() is panel.section_page
    assert panel.section_page.isAncestorOf(panel.phrase_editor)
    assert panel.instrument_page.isAncestorOf(panel.instrument_grid)
    assert panel.global_page.isAncestorOf(win.performance.director_section)
    assert panel.global_page.isAncestorOf(win.performance.harmonic_section)
    assert len(panel.instrument_grid.cards) == 2
    assert not panel.details_toggle.isChecked()
    assert not win.performance.director_section.header.isChecked()
    assert not win.performance.harmonic_section.header.isChecked()
    assert all(c.curve.size().width() == 140 and c.curve.height() == 100 for c in panel.instrument_grid.cards.values())
    assert not errors


def test_section_specific_phrase_technique_and_coefficients_undo_redo(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    panel = prepare(win, monkeypatch)
    panel.phrase_editor.phrase.setCurrentIndex(panel.phrase_editor.phrase.findData("opening_bloom"))
    card = panel.instrument_grid.cards[melody.id]
    card.technique.setCurrentIndex(card.technique.findData("staccato"))
    card.coefficients["gate"].setValue(.5)
    first = deepcopy(win.project.composition["sections"][0])
    assert first["performance"]["techniques"][str(melody.id)]["preset_id"] == "staccato"
    assert first["blocks"][str(melody.id)]["gate"] == .5
    panel.section_list.setCurrentRow(1)
    assert panel.phrase_editor.phrase.currentData() is None
    assert card.technique.currentData() is None
    assert not win.transport.running
    win.history_controller.flush()
    win.history_controller.move(False)
    assert win.project.composition["sections"][0] != first
    win.history_controller.move(True)
    assert win.project.composition["sections"][0] == first
    assert not errors


def test_form_play_uses_assignment_editor_selection_never_seeks_and_main_is_clean(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    panel = prepare(win, monkeypatch)
    panel.phrase_editor.phrase.setCurrentIndex(panel.phrase_editor.phrase.findData("tension_rise"))
    panel.play_button.click()
    assert win.engine.director.phrase.running and not win.play.isChecked()
    win.transport.seek(3)
    before = deepcopy(win.engine.director.phrase.memory)
    panel.section_list.setCurrentRow(1)
    assert win.engine.clock.position_beats == 3
    assert win.engine.director.phrase.memory == before
    panel.section_list.setCurrentRow(0)
    panel.update_runtime()
    assert any(card.curve.progress is not None for card in panel.instrument_grid.cards.values())
    win.play.click()
    assert win.transport.playback_mode == "blocks" and win.play.isChecked()
    assert not win.engine.performance.active and not win.engine.director.phrase.running
    assert not errors


def test_drum_card_edits_whole_kit_but_details_keep_individual_values(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    panel = prepare(win, monkeypatch)
    card = panel.instrument_grid.cards[drum.id]
    card.coefficients["density"].setValue(.3)
    section = panel._selected_section()
    assert all(section["blocks"][str(v.id)]["density"] == .3 for v in drum.drum_voices)
    voice = drum.drum_voices[0]
    panel.show_block_details(drum)
    assert panel.composition_tabs.currentWidget() is panel.instrument_page
    assert panel.details_toggle.isChecked()
    panel._set_block_setting(section["id"], voice.id, "density", .1)
    assert "Mixed" in card.coefficients["density"].toolTip()
    assert section["blocks"][str(drum.drum_voices[1].id)]["density"] == .3
    assert not errors


def test_fit_updates_on_meter_duration_and_custom_beats_stay_saved(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    panel = prepare(win, monkeypatch)
    editor = panel.phrase_editor
    editor.phrase.setCurrentIndex(editor.phrase.findData("breath"))
    assert editor.duration.value() == 8
    panel.meter.setCurrentText("7/8")
    assert editor.duration.value() == 7
    panel.section_bars.setValue(3)
    assert editor.duration.value() == 10.5
    editor.fit.setChecked(False)
    editor.duration.setValue(6)
    editor.fit.setChecked(True)
    editor.fit.setChecked(False)
    assert editor.duration.value() == 6
    assert not errors


def test_custom_color_duplicate_drag_and_roundtrip_preserve_identity(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    panel = prepare(win, monkeypatch)
    monkeypatch.setattr("composition_planner_ui.QColorDialog.getColor", lambda *args: QColor("#12abcf"))
    panel.color_button.click()
    original = deepcopy(panel._selected_section())
    assert section_color(original) == "#12abcf"
    panel.duplicate_section()
    duplicate = panel._selected_section()
    assert section_color(duplicate) != section_color(original)
    assert duplicate["performance"] == original["performance"]
    panel.move_section(1)
    assert section_color(next(s for s in win.project.composition["sections"] if s["id"] == original["id"])) == "#12abcf"
    assert not errors


def test_manual_audition_is_explicit_and_switches_from_form(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    panel = prepare(win, monkeypatch)
    panel._open_manual_audition()
    dialog = panel._manual_dialog
    assert dialog.isVisible() and not win.transport.running
    panel.play_button.click()
    win.performance.phrase_panel._start()
    assert win.transport.playback_mode == "perform" and win.engine.director.phrase.running
    assert not win.engine.director.phrase.memory.get("section_owner")
    dialog.close()
    assert win.transport.running and not dialog.isVisible()
    panel._open_manual_audition()
    assert panel._manual_dialog is dialog
    assert not errors


@pytest.mark.parametrize("theme", ["Midnight", "Solar"])
def test_two_columns_to_one_resize_without_clipping_or_card_rebuild(inspector, monkeypatch, theme):
    gui, win, drum, melody, errors = inspector
    panel = prepare(win, monkeypatch)
    for i, kind in enumerate(("BASS", "CHORD", "PAD", "MELODY"), 3):
        win.project.blocks.append(gui.Block(i, kind, kind, "Pattern", mutators=[]))
    panel.sync_from_project()
    panel.phrase_editor.phrase.setCurrentIndex(panel.phrase_editor.phrase.findData("tension_rise"))
    for card in panel.instrument_grid.cards.values():
        card.technique.setCurrentIndex(card.technique.findData("staccato"))
    if win.theme_combo.findText(theme) >= 0:
        win.theme_combo.setCurrentText(theme)
    win.resize(1600, 1200); win.show(); QTest.qWait(70)
    cards = dict(panel.instrument_grid.cards)
    assert len(cards) == 6 and panel.instrument_grid.columns == 2
    win.resize(820, 720)
    for _ in range(60):
        QTest.qWait(10)
        if panel.instrument_grid.columns == 1 and panel.editor.width() <= panel.editor_scroll.viewport().width():
            break
    assert panel.instrument_grid.columns == 1
    assert panel.editor.width() <= panel.editor_scroll.viewport().width()
    assert all(panel.instrument_grid.cards[bid] is card for bid, card in cards.items())
    assert not errors
