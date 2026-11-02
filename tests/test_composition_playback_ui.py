"""Native Composition transport, timeline and ending editor interactions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from composition_planner import make_section, CONTROLLED_PARAMETERS
from test_kit_preview_lifecycle import inspector


def form(win):
    win.project.composition["sections"] = [make_section(kind, bars=2, neutral=True)
                                           for kind in ("Intro", "Build", "Drop")]
    win.composition_panel.sync_from_project()


def test_composition_play_enables_form_starts_selected_without_pressing_header(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    monkeypatch.setattr(win.transport, "refresh_ports", lambda: None)
    form(win)
    panel = win.composition_panel
    panel.section_list.setCurrentRow(1)
    win.project.composition["enabled"] = False
    panel.sync_from_project()
    selected = panel._selected_section()["id"]
    panel.play_button.click()
    assert win.transport.running and not win.play.isChecked()
    assert panel.play_button.isChecked()
    assert win.project.composition["enabled"] and panel.enabled.isChecked()
    assert win.engine.clock.position_beats == 8
    assert panel._selected_section()["id"] == selected
    panel.stop_button.click()
    assert not win.transport.running and not win.play.isChecked()
    panel.play_from.setCurrentIndex(panel.play_from.findData("start"))
    panel.play_button.click()
    assert win.engine.clock.position_beats == 0
    panel.stop_button.click()
    assert not errors


def test_timeline_drag_seeks_once_on_release_does_not_edit_selection_or_history(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    form(win)
    panel = win.composition_panel
    win.tabs.setCurrentWidget(panel)
    win.show()
    QTest.qWait(20)
    selected = panel._selected_section()["id"]
    calls = []
    original = win.transport.seek
    def seek(position):
        calls.append(position)
        return original(position)
    monkeypatch.setattr(win.transport, "seek", seek)
    win.history_controller.reset()
    timeline = panel.timeline
    track = timeline.track_rect()
    start = track.topLeft().toPoint()
    end = (track.topLeft() + (track.topRight() - track.topLeft()) * .5).toPoint()
    QTest.mousePress(timeline, Qt.LeftButton, pos=start)
    QTest.mouseMove(timeline, end)
    panel.update_runtime()  # heartbeat must not replace a drag preview
    assert not calls and timeline.dragging
    QTest.mouseRelease(timeline, Qt.LeftButton, pos=end)
    assert calls == [12.]
    assert not timeline.dragging
    assert win.engine.clock.position_beats == 12
    assert not win.transport.running
    assert panel._selected_section()["id"] == selected
    assert panel.play_from.currentData() == "cursor"
    assert win.history_controller.history.index == 0
    monkeypatch.setattr(win.transport, "refresh_ports", lambda: None)
    panel.play_button.click()
    assert win.engine.clock.position_beats == 12
    panel.stop_button.click()
    assert not errors


def test_end_choice_is_persistent_and_undo_redo_updates_the_widget(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.composition_panel
    win.history_controller.reset()
    panel.ending.setCurrentIndex(panel.ending.findData("stop"))
    win.history_controller.flush()
    assert not win.project.composition["loop"]
    assert win.project.composition["end_action"] == "stop"
    win.history_controller.move()
    assert panel.ending.currentData() == "loop"
    win.history_controller.move(True)
    assert panel.ending.currentData() == "stop"
    panel.ending.setCurrentIndex(panel.ending.findData("hold"))
    assert win.project.composition["end_action"] == "hold"
    assert not errors


def test_parameter_reference_expands_without_changing_the_project(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.composition_panel
    win.tabs.setCurrentWidget(panel)
    win.show()
    win.history_controller.reset()
    assert panel.parameter_list.isHidden()
    panel.parameter_list_toggle.click()
    assert not panel.parameter_list.isHidden()
    for _category, values in CONTROLLED_PARAMETERS:
        for value in values.split(" · "):
            assert value in panel.parameter_list.text()
    panel.parameter_list_toggle.click()
    assert panel.parameter_list.isHidden()
    assert win.history_controller.history.index == 0
    assert not errors


@pytest.mark.parametrize("theme,light", [("Midnight", False), ("Solar", True)])
def test_composition_icons_follow_the_same_dark_light_contrast_rule(inspector, theme, light):
    gui, win, drum, melody, errors = inspector
    win.theme_combo.setCurrentText(theme)
    win.composition_panel._theme_changed()
    for button in (win.composition_panel.play_button, win.composition_panel.stop_button):
        image = button.icon().pixmap(20, 20).toImage()
        pixels = [image.pixelColor(x, y) for x in range(20) for y in range(20)
                  if image.pixelColor(x, y).alpha() > 240]
        assert pixels
        assert all(color.red() < 40 if light else color.red() > 230 for color in pixels)
    assert not errors


def test_worker_finishes_form_and_ui_stops_without_a_second_transport(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    monkeypatch.setattr(win.transport, "refresh_ports", lambda: None)
    panel = win.composition_panel
    win.project.tempo = 240
    win.project.composition.update(meter="2/4", loop=False, end_action="stop",
                                  sections=[make_section("Outro", bars=1, neutral=True)])
    panel.sync_from_project()
    win.transport_worker.start()
    win.performance_timer.start()
    try:
        panel.play_button.click()
        QTest.qWait(850)
        assert not win.transport.running and not win.engine.clock.running
        assert win.engine.clock.position_beats == 2.
        assert not win.play.isChecked()
        assert not panel.stop_button.isEnabled()
        assert panel.status.text().startswith("FINISHED")
        assert win.transport_worker.error_count == 0
    finally:
        win.performance_timer.stop()
        win.transport_worker.stop()
        win.transport.stop()
    assert not errors
