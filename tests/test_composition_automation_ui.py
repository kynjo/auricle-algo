"""Native curve editing, live feedback and section-safe MIDI releases."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest

from auricle_transport import Transport
from composition_planner import make_section
from composition_automation import normalize_curve
from composition_planner_ui import CompositionPlannerPanel
from test_composition_planner_ui import _app, _Host
from test_kit_preview_lifecycle import inspector


@pytest.mark.parametrize("enabled", [False, True])
def test_editing_future_section_never_releases_current_notes(enabled):
    _app()
    host = _Host()
    block = host.project.blocks[1]
    first, second = [make_section(name, [block], bars=4) for name in ("Verse", "Break")]
    host.project.composition.update(enabled=enabled, sections=[first, second])
    panel = CompositionPlannerPanel(host)
    host.transport.running = True
    host.engine.clock.position_beats = 1
    panel.section_list.setCurrentRow(1)
    panel._set_block_setting(second["id"], block.id, "enabled", False)
    assert host.transport.released == []
    panel._set_block_setting(first["id"], block.id, "enabled", False)
    assert host.transport.released == ([block.id] if enabled else [])


def test_future_section_edit_preserves_actual_active_midi_note_then_current_edit_sends_note_off():
    _app()
    host = _Host()
    block = host.project.blocks[1]
    host.transport = Transport(host)
    host.transport.running = True
    sent = []
    class Port:
        def send(self, message):
            sent.append(message)
    port = Port()
    first, second = [make_section(name, [block], bars=4) for name in ("Verse", "Break")]
    host.project.composition.update(enabled=True, sections=[first, second])
    panel = CompositionPlannerPanel(host)
    host.transport._send_note(block, {"pitch": 0, "velocity": .6, "duration": 1.5}, port, .5)
    held = list(host.transport.active_notes)
    panel._set_block_setting(second["id"], block.id, "enabled", False)
    assert host.transport.active_notes == held
    assert [m.type for m in sent] == ["note_on"]
    panel._set_block_setting(first["id"], block.id, "enabled", False)
    assert host.transport.active_notes == []
    assert [m.type for m in sent] == ["note_on", "note_off"]


def test_curve_controls_keep_project_points_and_emit_silent_runtime_updates():
    app = _app()
    host = _Host()
    panel = CompositionPlannerPanel(host)
    widgets = panel._macro_widgets["energy"]
    widgets["enabled"].setChecked(True)
    widgets["curve_toggle"].setChecked(True)
    assert widgets["curve"].isEnabled() and not widgets["slider"].isEnabled()
    lane = normalize_curve({"points": [[0, .2], [.5, .8], [1, .4]]})
    panel._set_macro_curve("energy", lane)
    panel._load_selected()
    assert panel._selected_section()["macro_curves"]["energy"] == lane
    host.project.composition["enabled"] = True
    host.transport.running = True
    host.engine.clock.position_beats = 16.
    before = deepcopy(host.project.composition)
    dirty = host.dirty_count
    panel.update_runtime()
    assert widgets["curve"].position == .5
    assert widgets["curve"].current_value == pytest.approx(.8)
    assert widgets["value"].text() == "80% · live"
    assert host.project.composition == before and host.dirty_count == dirty
    widgets["enabled"].setChecked(False)
    assert not widgets["curve"].isEnabled()
    assert panel.runtime.effective_macros(panel._selected_section(), host.engine.director.global_macro_values)["energy"] == .5


def test_curve_mouse_and_keyboard_edit_endpoints_and_interior_points():
    app = _app()
    host = _Host()
    panel = CompositionPlannerPanel(host)
    panel.resize(1100, 850)
    panel.show()
    widgets = panel._macro_widgets["energy"]
    widgets["enabled"].setChecked(True)
    widgets["curve_toggle"].setChecked(True)
    editor = widgets["curve"]
    app.processEvents()
    added = editor.point_position((.5, .8)).toPoint()
    QTest.mouseDClick(editor, Qt.LeftButton, pos=added)
    assert len(editor.curve["points"]) == 3
    assert len(panel._selected_section()["macro_curves"]["energy"]["points"]) == 3
    QTest.keyClick(editor, Qt.Key_Down)
    assert editor.curve["points"][1][1] < .8
    QTest.keyClick(editor, Qt.Key_Delete)
    assert len(editor.curve["points"]) == 2
    editor.selected = 0
    QTest.keyClick(editor, Qt.Key_Right)
    assert editor.curve["points"][0][0] == 0.
    QTest.keyClick(editor, Qt.Key_Delete)
    assert len(editor.curve["points"]) == 2
    panel.close()


def test_expression_selection_changes_only_selected_entity_and_hides_irrelevant_pitch_controls():
    _app()
    host = _Host()
    panel = CompositionPlannerPanel(host)
    first_id = panel._expression_entity[1]
    assert not panel._expression_widgets["octave_spread"].isEnabled()
    assert not panel._expression_widgets["harmony"].isEnabled()
    panel._expression_widgets["gate"].setValue(.5)
    section = panel._selected_section()
    assert section["blocks"][str(first_id)]["gate"] == .5
    panel.block_table.selectRow(panel.block_table.rowCount() - 1)
    lead_id = panel._expression_entity[1]
    assert lead_id != first_id
    assert panel._expression_widgets["harmony"].isEnabled()
    assert panel._expression_widgets["octave_spread"].isEnabled()
    assert panel._expression_widgets["gate"].value() == 1.
    panel._expression_widgets["accent"].setValue(.6)
    assert section["blocks"][str(lead_id)]["accent"] == .6
    assert section["blocks"][str(first_id)]["accent"] == 0.


def test_one_curve_drag_is_one_undo_redo_step_and_duplicates_are_independent(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.composition_panel
    widgets = panel._macro_widgets["energy"]
    widgets["enabled"].setChecked(True)
    widgets["curve_toggle"].setChecked(True)
    win.tabs.setCurrentWidget(panel)
    win.resize(1200, 900)
    win.show()
    QTest.qWait(20)
    win.history_controller.reset()
    original = deepcopy(panel._selected_section()["macro_curves"]["energy"])
    editor = widgets["curve"]
    start = editor.point_position(original["points"][0]).toPoint()
    end = editor.point_position((0., .9)).toPoint()
    QTest.mousePress(editor, Qt.LeftButton, pos=start)
    QTest.mouseMove(editor, end, delay=10)
    QTest.mouseRelease(editor, Qt.LeftButton, pos=end)
    QTest.qWait(20)
    win.history_controller.flush()
    changed = deepcopy(panel._selected_section()["macro_curves"]["energy"])
    assert changed != original
    assert win.history_controller.history.index == 1
    win.history_controller.move()
    assert win.project.composition["sections"][0]["macro_curves"]["energy"] == original
    win.history_controller.move(True)
    assert win.project.composition["sections"][0]["macro_curves"]["energy"] == changed
    panel.duplicate_section()
    sections = win.project.composition["sections"]
    assert sections[0]["macro_curves"] == sections[1]["macro_curves"]
    sections[1]["macro_curves"]["energy"]["points"][0][1] = .05
    assert sections[0]["macro_curves"] != sections[1]["macro_curves"]
    assert not errors


def test_curve_updates_global_header_and_knob_feedback_without_history_changes(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.composition_panel
    win.selected_block_id = melody.id
    win._refresh_inspector()
    section = win.project.composition["sections"][0]
    section["macros"]["energy"] = .5
    section["macro_curves"] = {"energy": normalize_curve({"points": [[0, .1], [1, .9]]})}
    win.project.composition["enabled"] = True
    panel.sync_from_project()
    win.history_controller.reset()
    values = []
    for beat, expected in ((0., 10), (16., 50), (31.9, 90)):
        win.engine.clock.position_beats = beat
        panel.update_runtime()
        win._update_parameter_sources(force=True)
        assert win.global_macro_bar.sliders[0].value() == expected
        knob = next(k for k in win.findChildren(gui.Knob)
                    if getattr(k, "_auricle_parameter", None) == (melody.id, "velocity_base"))
        values.append(knob.displayValue())
    assert values[0] < values[1] < values[2]
    assert win.history_controller.history.index == 0
    assert not errors
