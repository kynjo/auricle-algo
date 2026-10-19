"""Kit edits must survive missing/replaced native Inspector previews."""
import gc
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from auricle_core import Block, Project, ensure_drum_voices


@pytest.fixture
def inspector(monkeypatch):
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    import auricle_gui as gui

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(gui, "get_midi_output_names", lambda: ([], None))
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda kind, value, tb: errors.append(value))
    win = gui.MainWindow()
    win.performance_timer.stop()
    win.transport_worker.stop()
    drum = Block(1, "Kit", "DRUM", mutators=[])
    drum.drum_voices = ensure_drum_voices(drum)[:2]
    for voice in drum.drum_voices:
        voice.algorithm = "Pattern"
        voice.parameters["pattern"] = "1,0,0,0"
    melody = Block(2, "Melody", "MELODY", "Pattern", parameters={"pattern": "1"}, mutators=[])
    win.selected_drum_voice_id = None
    win._install_project(Project(blocks=[drum, melody]), None, "Preview lifetime")
    QTest.qWait(65)
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    try:
        assert not errors
        yield gui, win, drum, melody, errors
    finally:
        QTest.qWait(65)
        win.hide()
        win.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()


@pytest.mark.parametrize("key,value", [
    ("kit_density", 0.0), ("kit_humanize", .8), ("kit_fill", 1.0),
])
def test_knobs_work_with_parent_kit_selected(inspector, key, value):
    from PySide6.QtTest import QTest

    gui, win, drum, melody, errors = inspector
    assert win._selected_inspector_entity() is drum
    panel = win.drum_kit_layout.itemAt(0).widget()
    panel.findChild(gui.ParamKnob, key).setValue(value)
    QTest.qWait(65)
    assert not errors
    assert drum.parameters[key] == value
    assert win.drum_kit_layout.itemAt(0).widget() is panel
    assert not win.inspector_scroll.widget().findChildren(gui.AlgorithmPreviewWidget)
    if key == "kit_density":
        assert all(not any(v.outputs["rhythm"]) for v in drum.drum_voices)
    elif key == "kit_fill":
        assert all(all(v.outputs["rhythm"][-4:]) for v in drum.drum_voices)


@pytest.mark.parametrize("destination", ["kit", "voice", "melody", "empty"])
def test_pending_kit_edit_survives_inspector_replacement(inspector, destination, monkeypatch):
    from PySide6.QtTest import QTest
    from shiboken6 import isValid

    gui, win, drum, melody, errors = inspector
    first, second = drum.drum_voices
    win._select_drum_voice(first.id)
    QTest.qWait(65)
    old_preview = win.inspector_scroll.widget().findChild(gui.AlgorithmPreviewWidget)
    assert old_preview.block is first
    calls = []
    original = gui.AlgorithmPreviewWidget.set_block
    def set_block(preview, block, project):
        calls.append((preview, block))
        original(preview, block, project)
    monkeypatch.setattr(gui.AlgorithmPreviewWidget, "set_block", set_block)
    win._set_drum_kit_parameter(drum, "kit_density", 0)
    if destination == "kit":
        win.selected_drum_voice_id = None
        win._refresh_inspector()
    elif destination == "voice":
        win._select_drum_voice(second.id)
    elif destination == "melody":
        win.selected_block_id, win.selected_drum_voice_id = melody.id, None
        win._refresh_inspector()
    else:
        win.selected_block_id, win.selected_drum_voice_id = None, None
        win._refresh_inspector()
    gc.collect()
    QTest.qWait(65)
    # A queued Inspector rebuild can occupy the complete wait interval. Wait
    # for the actual coalesced edit, not for a machine-speed assumption.
    for _ in range(100):
        if id(drum) not in win._kit_regen_pending:
            break
        QTest.qWait(10)
    assert id(drum) not in win._kit_regen_pending
    assert not errors
    assert not isValid(old_preview)
    assert all(not any(v.outputs["rhythm"]) for v in drum.drum_voices)
    preview = win.inspector_scroll.widget().findChild(gui.AlgorithmPreviewWidget)
    assert not any(item is old_preview for item, _ in calls)
    if destination == "voice":
        assert preview.block is second
        assert sum(item is preview and block is second for item, block in calls) >= 2
    elif destination == "melody":
        assert preview.block is melody
        assert all(block is melody for _, block in calls)
    else:
        assert preview is None


def test_other_parent_parameter_and_mutator_edits_do_not_use_deleted_preview(inspector):
    from PySide6.QtTest import QTest

    gui, win, drum, melody, errors = inspector
    win._set_param(drum, "velocity_base", .7)
    win._mutator_editor_changed(drum)
    QTest.qWait(65)
    assert not errors


def test_project_switch_during_pending_kit_edit(inspector):
    from PySide6.QtTest import QTest

    gui, win, drum, melody, errors = inspector
    win._set_drum_kit_parameter(drum, "kit_density", 0)
    replacement = Block(drum.id, "Replacement kit", "DRUM", mutators=[])
    ensure_drum_voices(replacement)
    win._install_project(Project(blocks=[replacement]), None, "Replacement")
    win._set_drum_kit_parameter(replacement, "kit_density", 0)
    gc.collect()
    QTest.qWait(65)
    assert not errors
    assert all(not any(v.outputs["rhythm"]) for v in replacement.drum_voices)
