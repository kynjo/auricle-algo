"""Real Qt integration for musical kit activation, inline links and history."""
from copy import deepcopy

import pytest

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QPushButton

from test_kit_preview_lifecycle import inspector


def settle():
    QTest.qWait(80)
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_one_click_enables_all_three_directions_and_keeps_the_kit_pinned(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.drum_kit_layout.itemAt(0).widget()
    source = deepcopy([v.parameters for v in drum.drum_voices])
    panel.findChild(QPushButton, "kitMusicalPreset").click(); settle()
    panel = win.drum_kit_layout.itemAt(0).widget()
    assert drum.parameters["kit_engine"] == "map"
    assert drum.parameters["kit_motif_enabled"] and drum.parameters["kit_links_enabled"]
    assert panel.rhythm_panel.engine_selector.currentData() == "map"
    assert panel.rhythm_panel.body.isVisibleTo(panel)
    assert panel.rhythm_panel.motifs.isEnabled()
    knob = panel.findChild(gui.ParamKnob, "kit_map_x")
    knob.setValue(.9); settle()
    assert drum.parameters["kit_map_x"] == .9
    assert win.drum_kit_layout.itemAt(0).widget() is panel
    win._select_drum_voice(drum.drum_voices[0].id); settle()
    assert win.drum_kit_layout.count() == 1
    assert [v.parameters for v in drum.drum_voices] == source
    assert not errors


def test_add_edits_and_removes_a_coloured_inline_link_without_dialog(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.drum_kit_layout.itemAt(0).widget()
    panel._set_config("kit_coordinated", True); settle()
    panel = win.drum_kit_layout.itemAt(0).widget()
    rhythm = panel.rhythm_panel
    rhythm.more.setChecked(True)
    rhythm.add_link.click(); settle()
    assert drum.parameters["kit_links_enabled"]
    source = rhythm.findChild(QComboBox, "kitLink_0_source")
    destination = rhythm.findChild(QComboBox, "kitLink_0_destination")
    assert not source.itemIcon(0).isNull() and not destination.itemIcon(1).isNull()
    operation = rhythm.findChild(QComboBox, "kitLink_0_operation")
    operation.setCurrentIndex(operation.findData("answer")); settle()
    assert drum.parameters["kit_voice_links"][0]["delay"] == 2
    amount = rhythm.findChild(QDoubleSpinBox, "kitLink_0_amount")
    amount.setValue(.35); settle()
    assert drum.parameters["kit_voice_links"][0]["amount"] == .35
    phase = rhythm.findChild(gui.ValueStepper, "kitLink_0_phase")
    phase.setValue(-2); settle()
    assert drum.parameters["kit_voice_links"][0]["phase"] == -2
    chance = rhythm.findChild(QDoubleSpinBox, "kitLink_0_probability")
    chance.setValue(.6); settle()
    assert drum.parameters["kit_voice_links"][0]["probability"] == .6
    assert win.drum_kit_layout.itemAt(0).widget() is panel
    source.setCurrentIndex(source.findData(destination.currentData())); settle()
    assert "different" in rhythm.link_warning.text()
    rhythm.findChild(QPushButton, "kitLink_0_remove").click(); settle()
    assert drum.parameters["kit_voice_links"] == []
    assert not errors



def test_rhythm_map_pad_and_presets_update_the_existing_map_parameters(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.drum_kit_layout.itemAt(0).widget()
    panel.findChild(QPushButton, "kitMusicalPreset").click(); settle()
    panel = win.drum_kit_layout.itemAt(0).widget()
    rhythm = panel.rhythm_panel
    pad = rhythm.findChild(gui.QWidget, "kitRhythmMapPad")
    assert pad is not None
    QTest.mouseClick(pad, Qt.LeftButton, pos=QPoint(pad.width() - 10, 10)); settle()
    assert drum.parameters["kit_map_x"] > .95 and drum.parameters["kit_map_y"] > .95
    rhythm.map_preset.setCurrentIndex(rhythm.map_preset.findText("Broken drive")); settle()
    assert drum.parameters["kit_map_x"] == pytest.approx(.95)
    assert drum.parameters["kit_map_y"] == pytest.approx(.95)
    assert not errors


def test_suggested_relations_add_role_aware_links_once(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.drum_kit_layout.itemAt(0).widget()
    panel.findChild(QPushButton, "kitMusicalPreset").click(); settle()
    panel = win.drum_kit_layout.itemAt(0).widget()
    rhythm = panel.rhythm_panel
    rhythm.suggest_links.click(); settle()
    first = list(drum.parameters.get("kit_voice_links", []))
    rhythm.suggest_links.click(); settle()
    assert drum.parameters.get("kit_voice_links", []) == first
    assert all("probability" in link and "phase" in link for link in first)
    assert not errors

def test_new_parameter_controls_follow_actual_modulation_without_editing_base(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.drum_kit_layout.itemAt(0).widget()
    panel.findChild(QPushButton, "kitMusicalPreset").click(); settle()
    panel = win.drum_kit_layout.itemAt(0).widget()
    # The engine catalog exposes all new continuous controls to normal routes.
    assert win.engine.set_parameter(drum, "kit_map_y", .8, source="Relations", source_id="test")
    win.engine.generate()
    assert win.engine.kit_plan(drum.drum_voices[0], 0).engine == "map"
    assert win.drum_kit_layout.itemAt(0).widget() is panel
    assert not errors


def test_musical_kit_and_inline_links_participate_in_undo_redo(inspector):
    gui, win, drum, melody, errors = inspector
    history = win.history_controller
    history.flush()
    original = deepcopy(drum.parameters)
    panel = win.drum_kit_layout.itemAt(0).widget()
    panel.findChild(QPushButton, "kitMusicalPreset").click(); settle(); history.flush()
    musical = deepcopy(win.project.blocks[0].parameters)
    history.move(False); settle()
    assert win.project.blocks[0].parameters == original
    history.move(True); settle()
    assert win.project.blocks[0].parameters == musical
    panel = win.drum_kit_layout.itemAt(0).widget()
    panel.rhythm_panel.add_link.click(); settle(); history.flush()
    assert len(win.project.blocks[0].parameters["kit_voice_links"]) == len(musical["kit_voice_links"]) + 1
    history.move(False); settle()
    assert win.project.blocks[0].parameters == musical
    assert not errors
