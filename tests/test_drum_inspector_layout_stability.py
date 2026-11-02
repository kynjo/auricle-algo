"""Expanded Kit and Inspector accordions must settle, including scrollbar range."""
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from test_midi_learn_runtime_ui import app, editor


@pytest.mark.parametrize("width", [900, 1100, 1366])
@pytest.mark.parametrize("settings_open", [False, True])
def test_kit_and_other_layers_settle_without_refit_feedback(editor, app, width, settings_open):
    gui, win, _ = editor
    win.resize(width, 800)
    win.show()
    kit = win.drum_kit_layout.itemAt(0).widget()
    kit.setChecked(True)
    kit.rhythm_panel.more.setChecked(settings_open)
    layers = [win.inspector_page.findChild(gui.LayerGroup, "inspectorLayer_" + name)
              for name in ("STRUCTURE", "MUSICAL", "MOTION", "MONITOR")]
    for layer in layers:
        layer.setChecked(False)
    QTest.qWait(100)
    fits = []
    win._inspector_fit_timer.timeout.connect(lambda: fits.append(1))
    for layer in layers[:2]:
        layer.setChecked(True)
    QTest.qWait(120)
    settled_fits = len(fits)
    bar = win.inspector_scroll.verticalScrollBar()
    bar.setValue(min(kit.height(), bar.maximum()))
    samples = []
    for _ in range(12):
        QTest.qWait(15)
        samples.append((bar.maximum(), bar.value(), kit.height(),
                        *[layer.mapTo(win.inspector_scroll.viewport(), QPoint()).y()
                          for layer in layers]))
    assert len(set(samples)) == 1
    assert len(fits) == settled_fits
    assert not win._inspector_fit_timer.isActive()
    assert win.drum_kit_layout.itemAt(0).widget() is kit
    for layer in layers[2:]:
        layer.setChecked(True)
    QTest.qWait(120)
    bar.setValue(bar.maximum())
    QTest.qWait(30)
    assert win.inspector_page.height() <= bar.value() + win.inspector_scroll.viewport().height() + 3
    expanded = bar.maximum()
    for layer in layers:
        layer.setChecked(False)
    QTest.qWait(120)
    assert bar.maximum() < expanded
    assert win.drum_kit_layout.itemAt(0).widget() is kit
