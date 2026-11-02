"""Reference coverage and passive tooltip integration through actual Qt editors."""
from copy import deepcopy
from pathlib import Path
import re
import weakref

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtWidgets import QWidget, QComboBox, QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem
from PySide6.QtTest import QSignalSpy

from auricle_catalogs import BLOCK_TYPES, GENERATORS, PROCESS_TYPES
from help_catalog import CATALOG, GENERATOR_KEYS, PROCESS_KEYS, entry
from help_content import BLOCKS, help_markdown, help_html
from help_tooltips import bind_help, set_help_language, help_language
from test_midi_learn_runtime_ui import app, editor

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("language", ["ru", "en"])
def test_reference_matches_catalogs_and_exported_markdown(language):
    markdown = help_markdown(language)
    assert set(BLOCKS) == set(BLOCK_TYPES)
    assert set(GENERATOR_KEYS) == set(GENERATORS)
    assert set(PROCESS_KEYS) == set(PROCESS_TYPES)
    for scope, entries in CATALOG.items():
        if scope.startswith("process."):
            continue
        for key, item in entries.items():
            assert item.en and item.ru
            # All public scopes are part of the reference, including tooltips.
            assert item.text(language).replace("|", "&#124;") in markdown, (scope, key)
    assert ROOT.joinpath(f"docs/HELP_{language.upper()}.md").read_text() == markdown
    anchors = re.findall(r'<a name="([^"]+)"', markdown)
    assert len(anchors) == len(set(anchors))
    assert all(anchor in anchors for anchor in re.findall(r'\]\(#([^)]+)\)', markdown))
    assert "<table" in help_html(language)


def test_help_loads_lazily_and_supports_links_search_and_language(editor, app):
    gui, win, _ = editor
    assert win._help_rendered_language is None
    assert win.help_view.toPlainText() == ""
    win.resize(1280, 900)
    win.show()
    win.tabs.setCurrentWidget(win.help_tab)
    app.processEvents()
    assert win._help_rendered_language == "ru"
    assert "INSTRUMENTS" in win.help_view.toPlainText()
    # Real QTextDocument anchors are needed, not just Markdown source links.
    assert 'name="composition"' in win.help_view.document().toHtml()
    win.help_view.anchorClicked.emit(QUrl("#composition"))
    assert win.help_view.verticalScrollBar().value() > 0
    win.help_search.setText("Register Center")
    win._find_help()
    assert win.help_view.textCursor().selectedText() == "Register Center"
    win._find_help(True)
    assert win.help_view.textCursor().selectedText() == "Register Center"
    win.help_search.setText("missing-parameter-zzzz")
    win._find_help()
    assert win.help_search_status.text() == "Не найдено"
    win.help_language.setCurrentIndex(0)
    assert win._help_rendered_language == "en"
    assert "Quickstart" in win.help_view.toPlainText()
    assert help_language() == "en"
    win.help_language.setCurrentIndex(1)


@pytest.mark.parametrize("algorithm", GENERATORS)
def test_every_visible_generator_parameter_has_context_help(editor, algorithm):
    gui, win, _ = editor
    block = next(b for b in win.project.blocks if b.block_type != "DRUM")
    block.algorithm = algorithm
    win.selected_block_id = block.id
    win._refresh_inspector()
    group = win.inspector_page.findChild(QWidget, "inspectorGroup_GENERATOR")
    assert group is not None
    keys = {w._auricle_help[1] for w in group.findChildren(QWidget) if hasattr(w, "_auricle_help")}
    assert set(GENERATOR_KEYS[algorithm].split()) <= keys
    for widget in group.findChildren(QWidget):
        if hasattr(widget, "_auricle_help"):
            assert widget.toolTip(), (algorithm, widget.objectName())
            if isinstance(widget, gui.Knob):
                assert "Диапазон" in widget.toolTip()


@pytest.mark.parametrize("kind", PROCESS_TYPES)
def test_every_process_control_is_described(editor, kind):
    gui, win, _ = editor
    block = next(b for b in win.project.blocks if b.block_type != "DRUM")
    process = gui.Process(type=kind)
    controls = gui.ProcessInlineControls(process, win.project, block, win)
    keys = {w._auricle_help[1] for w in controls.findChildren(QWidget) if hasattr(w, "_auricle_help")}
    assert set(PROCESS_KEYS[kind].split()) == keys
    controls.deleteLater()


def test_composition_controls_and_dynamic_voice_coefficients_have_tooltips(editor):
    gui, win, _ = editor
    panel = win.composition_panel
    for key in CATALOG["composition"]:
        widget = getattr(panel, key)
        assert widget.toolTip(), key
        assert widget._auricle_help == ("composition", key, "")
    for macro, controls in panel._macro_widgets.items():
        for key in CATALOG["composition_curve"]:
            assert controls[key]._auricle_help[1] == key
    for key in CATALOG["section_phrase"]:
        assert getattr(panel.phrase_editor, key).toolTip(), key
    from composition_performance_ui import SectionInstrumentCard
    cards = panel.findChildren(SectionInstrumentCard)
    assert cards
    for card in cards:
        card.sync()
        for key in ("active", "technique", "amount", "shape", "fit", "beats", "mode", "mute", "details", "curve"):
            assert getattr(card, key)._auricle_help[:2] == ("section_instrument", key)
        for key, control in card.coefficients.items():
            assert control._auricle_help[:2] == ("section_instrument", key)
    assert panel.block_table.cellWidget(0, 2).toolTip()


def test_language_switch_is_passive_for_table_edits_and_project(editor, app):
    gui, win, _ = editor
    from midi_expression_ui import MidiExpressionEditor
    expression = MidiExpressionEditor({"cc_lanes": [{"controller": 74, "enabled": True}]}, win)
    assert expression.cc_table.rowCount() == 1
    item_spy = QSignalSpy(expression.cc_table.itemChanged)
    changed_spy = QSignalSpy(expression.changed)
    before = deepcopy(expression.config())
    dirty = win._dirty
    queued = len(win.transport.gui_command_queue)
    set_help_language("en")
    assert "Minimum" in expression.cc_table.item(0, 2).toolTip()
    assert item_spy.count() == changed_spy.count() == 0
    assert expression.config() == before
    assert win._dirty == dirty and len(win.transport.gui_command_queue) == queued
    set_help_language("ru")
    expression.deleteLater()


def test_help_bindings_do_not_retain_deleted_controls_or_emit_knob_changes(editor, app):
    gui, win, _ = editor
    knob = gui.RangeKnob(0, 100, 25, default=50)
    spy = QSignalSpy(knob.changed)
    bind_help(knob, "timing_rate")
    before = knob.value()
    set_help_language("en")
    set_help_language("ru")
    assert knob.value() == before and spy.count() == 0
    ref = weakref.ref(knob)
    knob.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    del knob
    import gc
    gc.collect()
    assert ref() is None
    # Updating the weak registry must tolerate deleted C++ table cells too.
    table = QTableWidget(1, 1)
    table.setItem(0, 0, QTableWidgetItem("test"))
    bind_help(table.item(0, 0), "cc", "midi_expression")
    table.clearContents()
    set_help_language("ru")
    table.deleteLater()


def test_every_numeric_engine_parameter_is_documented():
    from auricle_core import Block, MusicEngine
    for kind in BLOCK_TYPES:
        for algorithm in GENERATORS:
            block = Block(1, "Reference audit", kind, algorithm)
            for key in MusicEngine.parameter_catalog(block):
                assert entry("block", key), (kind, algorithm, key)
