"""Compact attribution survives themes, inspector replacement and project history."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from auricle_core import Relation
from parameter_sources import SOURCE_COLORS, SourceMark
from parameter_sources_ui import DOT_SIZE, ParameterSourceLabel
from test_kit_preview_lifecycle import inspector
from ui_themes import theme_names, theme_palette


def app():
    return QApplication.instance() or QApplication([])


def labels(win, block_id, key):
    return [label for label in win.findChildren(ParameterSourceLabel) if label.binding == (block_id, key)]


@pytest.mark.parametrize("theme_name", theme_names())
def test_three_eight_pixel_dots_fit_existing_caption_in_every_theme(theme_name):
    app()
    theme = theme_palette(theme_name)
    label = ParameterSourceLabel("Density")
    label.setAlignment(Qt.AlignCenter)
    label.setFixedSize(74, 18)
    label.setStyleSheet(f"background:{theme.card}; color:{theme.text}; font-size:11px;")
    label.show()
    app().processEvents()
    before = (label.size(), label.sizeHint(), label.minimumSizeHint())
    label.set_sources(tuple(SourceMark(source, True, ("Example",)) for source in SOURCE_COLORS))
    app().processEvents()
    image = label.grab().toImage()
    assert DOT_SIZE == 8
    assert label.text() == "Density"
    assert before == (label.size(), label.sizeHint(), label.minimumSizeHint())
    for source, color in SOURCE_COLORS.items():
        pixels = [(x, y) for y in range(image.height()) for x in range(image.width())
                  if image.pixelColor(x, y).name() == color]
        assert pixels, source
        xs, ys = zip(*pixels)
        assert 3 <= max(xs) - min(xs) + 1 <= 8
        assert 3 <= max(ys) - min(ys) + 1 <= 8
    label.close()


def test_tooltip_is_escaped_and_base_hint_restored_when_last_source_removed():
    app()
    label = ParameterSourceLabel("Density")
    label.set_base_tooltip("Original hint")
    label.set_sources((SourceMark("Relations", True, ("<Source> → <Destination>",)),), (.8, .6))
    assert "&lt;Source&gt;" in label.toolTip() and "<Source>" not in label.toolTip()
    assert "Relations" in label.accessibleDescription()
    assert "Manual: 0.8" in label.toolTip()
    label.set_base_tooltip("Updated hint")
    label.set_sources(())
    assert label.toolTip() == "Updated hint"
    assert not label.accessibleDescription()


def test_global_dot_does_not_clip_variation_or_overlap_slider_at_minimum_width(inspector):
    gui, win, drum, melody, errors = inspector
    win.show()
    for width in (820, 1250):
        win.resize(width, 850)
        QTest.qWait(40)
        bar = win.global_macro_bar
        for label, slider, value in zip(bar.labels, bar.sliders, bar.values):
            label.set_sources((SourceMark("Composition", True, ("Example",)),))
            assert label.fontMetrics().horizontalAdvance(label.text()) + 11 <= label.width()
            assert label.geometry().right() < slider.geometry().left()
            assert slider.geometry().right() < value.geometry().left()
    assert not errors


def test_markers_follow_perform_and_relation_lifecycle_without_editing_knobs(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    win.selected_block_id = melody.id
    win._refresh_inspector()
    knob = next(w for w in win.inspector_page.findChildren(gui.Knob)
                if getattr(w, "_auricle_parameter", None) == (melody.id, "gate"))
    original_value = knob.value()
    changes = []
    knob.changed.connect(changes.append)
    win.engine.performance.start(melody, "staccato", beats=8)
    win.engine.performance.tick(True, beat_delta=1)
    win.project.relations = [Relation(drum.id, "duration", melody.id, "duration", "Mix", .5)]
    gate = labels(win, melody.id, "gate")[0]
    def unexpected(*args, **kwargs):
        pytest.fail("A UI source refresh must not regenerate or write a parameter")
    with monkeypatch.context() as scoped:
        for method in ("generate", "regenerate", "set_parameter", "apply_relations"):
            scoped.setattr(win.engine, method, unexpected)
        for _ in range(5):
            win._update_parameter_sources(force=True)
    assert [m.source for m in gate.source_marks] == ["Perform", "Relations"]
    assert knob.value() == original_value and not changes
    assert "generator setting is unchanged" in gate.toolTip()
    win.engine.performance.stop(melody.id)
    win.project.relations[0].enabled = False
    win._update_parameter_sources(force=True)
    assert not gate.source_marks
    assert not errors


def test_global_macro_and_kit_voice_markers_follow_composition_and_engine_replacement(inspector):
    gui, win, drum, melody, errors = inspector
    form = win.engine.composition_runtime.config()
    form["enabled"] = True
    section = form["sections"][0]
    section["macros"]["density"] = .2
    section["blocks"][str(drum.drum_voices[0].id)] = {"density": .3}
    win._select_drum_voice(drum.drum_voices[0].id)
    QTest.qWait(65)
    win._update_parameter_sources(force=True)
    assert labels(win, None, "density")[0].source_marks[0].source == "Composition"
    assert labels(win, drum.id, "kit_density")[0].source_marks[0].source == "Composition"
    voice_label = labels(win, drum.drum_voices[0].id, "fill_density")[0]
    assert voice_label.source_marks[0].source == "Composition"
    win.global_macro_bar.refresh_from_project()
    win._update_parameter_sources(force=True)
    assert "Section override" in labels(win, None, "density")[0].toolTip()
    win.history_controller.reset()
    form["enabled"] = False
    win._mark_dirty()
    win.history_controller.flush()
    win._update_parameter_sources(force=True)
    assert not labels(win, None, "density")[0].source_marks
    win.history_controller.move()
    QTest.qWait(65)
    win._update_parameter_sources(force=True)
    assert labels(win, None, "density")[0].source_marks[0].source == "Composition"
    win.history_controller.move(True)
    QTest.qWait(65)
    win._update_parameter_sources(force=True)
    assert not labels(win, None, "density")[0].source_marks
    assert not errors


def test_refresh_skips_busy_transport_and_survives_deleted_inspectors(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    class BusyLock:
        def acquire(self, *, blocking):
            assert blocking is False
            return False
        def release(self):
            pytest.fail("An unacquired lock must not be released")
    with monkeypatch.context() as scoped:
        scoped.setattr(win.transport, "_state_lock", BusyLock())
        win._update_parameter_sources(force=True)
    for block in (melody, drum, melody):
        win.selected_block_id, win.selected_drum_voice_id = block.id, None
        win._refresh_inspector()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        win._update_parameter_sources(force=True)
    assert not errors
