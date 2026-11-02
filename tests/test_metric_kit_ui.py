"""Actual retained Qt controls and queued edits, with a stopped test worker."""
from copy import deepcopy

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
import mido

from midi_learn import normalize_mapping
from parameter_sources_ui import ParameterSourceLabel

from test_kit_preview_lifecycle import inspector


def commit(win):
    win.transport.flush_gui_commands(notify=True)
    QTest.qWait(80)
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QCoreApplication.processEvents()


def metric_panel(win):
    panel = win.drum_kit_layout.itemAt(0).widget()
    panel._set_config("kit_coordinated", True)
    commit(win)
    panel = win.drum_kit_layout.itemAt(0).widget()
    selector = panel.rhythm_panel.engine_selector
    selector.setCurrentIndex(selector.findData("metric"))
    commit(win)
    panel = win.drum_kit_layout.itemAt(0).widget()
    panel.rhythm_panel.more.setChecked(True)
    QCoreApplication.processEvents()
    return panel


def test_engine_switch_uses_a_compact_metric_panel_and_preserves_map_and_sources(inspector):
    gui, win, drum, melody, errors = inspector
    source = deepcopy([voice.parameters for voice in drum.drum_voices])
    drum.parameters.update(kit_map_x=.82, kit_map_y=.17)
    panel = metric_panel(win)
    rhythm = panel.rhythm_panel
    assert drum.parameters["kit_engine"] == "metric"
    assert rhythm.metric_preview.isVisibleTo(panel)
    assert not rhythm.map_pad.isVisibleTo(panel)
    assert all(knob.isEnabled() for knob in rhythm.metric_knobs)
    assert rhythm.activate.text() == "Metric kit"
    assert rhythm.body.sizeHint().height() < 190
    sizes = []
    for _ in range(12):
        panel.update_position()
        QCoreApplication.processEvents()
        sizes.append(rhythm.sizeHint().height())
    assert max(sizes) == min(sizes)
    rhythm.engine_selector.setCurrentIndex(rhythm.engine_selector.findData("map"))
    commit(win)
    panel = win.drum_kit_layout.itemAt(0).widget()
    assert panel.rhythm_panel.map_pad.isVisibleTo(panel)
    assert not panel.rhythm_panel.metric_preview.isVisibleTo(panel)
    assert (drum.parameters["kit_map_x"], drum.parameters["kit_map_y"]) == (.82, .17)
    assert [voice.parameters for voice in drum.drum_voices] == source
    assert not errors


def test_native_ranges_queued_edits_and_influence_feedback(inspector):
    gui, win, drum, melody, errors = inspector
    panel = metric_panel(win)
    before = [voice.midi_note for voice in drum.drum_voices]
    fragment = panel.findChild(gui.RangeKnob, "kit_metric_fragment")
    assert (fragment.lo, fragment.hi, fragment.integer) == (1, 8, True)
    fragment.setValue(7)
    density = panel.findChild(gui.ParamKnob, "kit_metric_density")
    strength = panel.findChild(gui.ParamKnob, "kit_metric_strength")
    density.setValue(.31); strength.setValue(.77)
    # One heartbeat before the queued write must not reset an edited control.
    panel.update_position()
    commit(win)
    assert drum.parameters["kit_metric_fragment"] == 7
    assert type(drum.parameters["kit_metric_fragment"]) is int
    assert drum.parameters["kit_metric_density"] == .31
    assert drum.parameters["kit_metric_strength"] == .77
    assert win.drum_kit_layout.itemAt(0).widget() is panel
    assert not win.transport.running
    assert before == [voice.midi_note for voice in drum.drum_voices]
    assert win.engine.set_parameter(drum, "kit_metric_density", .8,
                                    source="Relations", source_id="metric-test")
    win.engine.generate()
    win._update_parameter_sources(force=True)
    assert win.engine.parameter_influence.base_value(drum, "kit_metric_density", 0) == .31
    assert density._auricle_parameter == (drum.id, "kit_metric_density")
    assert density._auricle_has_midi_learn_menu
    assert density.displayValue() == .8
    caption = next(label for label in panel.findChildren(ParameterSourceLabel)
                   if label.binding == (drum.id, "kit_metric_density"))
    assert any(mark.source == "Relations" and mark.active for mark in caption.source_marks)
    assert not errors


def test_midi_cc_reaches_all_metric_knobs_in_native_ranges_without_rebuild(inspector):
    gui, win, drum, melody, errors = inspector
    panel = metric_panel(win)
    for key in ("kit_metric_density", "kit_metric_strength", "kit_metric_fragment"):
        knob = panel.findChild(gui.Knob, key)
        win.project.midi_mappings = [normalize_mapping({
            "source": {"type": "cc", "number": 74},
            "target": {"kind": "block_parameter", "block_id": drum.id,
                       "parameter": key, "integer": knob.integer},
            "min": knob.lo, "max": knob.hi, "pickup": False,
        })]
        for raw in (127, 32, 0):
            win._handle_midi_input("", mido.Message("control_change", control=74, value=raw))
            commit(win)
            expected = knob.lo + (knob.hi - knob.lo) * raw / 127
            if knob.integer:
                expected = round(expected)
            assert abs(drum.parameters[key] - expected) < 1e-10
            assert abs(knob.displayValue() - expected) < 1e-10
            assert knob.value_label.text() == knob._formatted()
            assert win.drum_kit_layout.itemAt(0).widget() is panel
    assert not errors
