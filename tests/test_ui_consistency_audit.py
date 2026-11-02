"""UI size, lifetime, parameter wiring and responsiveness regressions."""
import gc
import threading

import pytest
from PySide6.QtCore import QObject, QCoreApplication, QEvent, QRect
from PySide6.QtWidgets import QComboBox, QCheckBox, QLineEdit

from auricle_catalogs import GENERATORS
from auricle_resources import asset_path
from ui_icons import BLOCK_ICON_NAMES, block_type_icon
from ui_metrics import CARD_HEIGHT, DENSE_HEIGHT, MODE_WIDTH, TAB_ICON_SIZE, initial_window_geometry
from test_midi_learn_runtime_ui import app, editor, wait_for


@pytest.mark.parametrize("available", [QRect(0, 0, 800, 600), QRect(0, 0, 1366, 768),
                                       QRect(1920, 0, 1920, 1080), QRect(-1280, 0, 1280, 720)])
def test_startup_geometry_fits_work_area_and_centers_on_its_monitor(available):
    rect = initial_window_geometry(available)
    assert available.contains(rect)
    assert abs(rect.center().x() - available.center().x()) <= 1
    assert abs(rect.center().y() - available.center().y()) <= 1
    assert rect.height() <= available.height() - 64


def test_block_icons_are_real_bundled_svg_and_cached(editor):
    for kind, filename in BLOCK_ICON_NAMES.items():
        assert asset_path(filename).is_file()
        assert not block_type_icon(kind, "#ffffff", 24).isNull()
        assert block_type_icon(kind, "#ffffff", 24).cacheKey() == block_type_icon(kind, "#ffffff", 24).cacheKey()


def test_all_mode_buttons_are_equal_and_contained_in_their_switch(editor, app):
    gui, win, _ = editor
    for theme in gui.theme_names():
        win._theme_changed(theme)
        app.processEvents()
        for mode in win.findChildren(gui.ModeSwitch):
            assert mode.seq.size() == mode.live.size()
            assert mode.seq.width() == MODE_WIDTH
            assert mode.seq.height() == mode.live.height() == mode.height() == DENSE_HEIGHT
        for index in range(win.block_list.count()):
            card = win.block_list.itemWidget(win.block_list.item(index))
            assert card.mute_button.size().width() == card.mute_button.size().height() == DENSE_HEIGHT
            card.mute_button.setChecked(True)
            app.processEvents()
            assert card.mute_button.size().width() == card.mute_button.size().height() == DENSE_HEIGHT
            card.mute_button.setChecked(False)
    assert win.header_nav.iconSize().width() == TAB_ICON_SIZE
    assert win.composition_panel.play_button.size() == win.play.size()
    assert win.composition_panel.stop_button.size() == win.stop.size()


def test_block_refresh_reuses_cards_and_connections(editor):
    gui, win, _ = editor
    before = [win.block_list.itemWidget(win.block_list.item(i)) for i in range(win.block_list.count())]
    for index in range(12):
        win.project.blocks[0].name = f"Kit {index}"
        win._refresh_blocks()
    after = [win.block_list.itemWidget(win.block_list.item(i)) for i in range(win.block_list.count())]
    assert after == before
    assert after[0].name_label.text() == "Kit 11"
    assert all(card.height() == CARD_HEIGHT for card in after)
    assert all(card.receivers("2mode_changed(int,QString)") == 1 for card in after)


def test_kit_drag_updates_model_without_rebuilding_inspector(editor, app):
    gui, win, _ = editor
    kit = win.drum_kit_layout.itemAt(0).widget()
    page = win.inspector_page
    knob = kit.findChild(gui.Knob, "kit_humanize")
    for value in (.2, .4, .6, .8):
        knob.setValue(value)
    assert len(win.transport.gui_command_queue) == 1
    win.transport_worker.start()
    try:
        wait_for(app, lambda: win.project.blocks[0].parameters.get("kit_humanize") == .8)
        app.processEvents()
        assert win.inspector_page is page
        assert win.drum_kit_layout.itemAt(0).widget() is kit
        assert not win._inspector_refresh_queued
    finally:
        win.transport_worker.stop()


def test_switching_blocks_keeps_one_kit_and_no_growing_widget_tree(editor, app):
    _, win, _ = editor
    kit = win.drum_kit_layout.itemAt(0).widget()
    counts = []
    for cycle in range(4):
        for block in win.project.blocks:
            win.selected_block_id = block.id
            win._refresh_inspector()
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        gc.collect()
        counts.append(len(win.findChildren(QObject)))
        assert win.drum_kit_layout.itemAt(0).widget() is kit
        assert kit.isHidden() or not win.drum_kit_host.isVisible()
    assert counts[-1] <= counts[0] + 4


def test_resize_reflows_existing_inspector_controls(editor, app):
    gui, win, _ = editor
    win.selected_block_id = win.project.blocks[1].id
    win._refresh_inspector()
    page = win.inspector_page
    knobs = page.findChildren(gui.Knob)
    win.show()
    for width in (820, 1440, 900, 1440):
        win.resize(width, 800)
        app.processEvents()
        win._fit_inspector_page()
        app.processEvents()
        assert win.inspector_page is page
        assert page.findChildren(gui.Knob) == knobs
    pairs = [form for form in page._auricle_reflow_forms if hasattr(form, "groups")]
    assert pairs and all(pair.columns == 2 for pair in pairs)


def test_ui_heartbeat_does_not_wait_for_legacy_state_lock(editor, monkeypatch):
    _, win, _ = editor
    ready, release = threading.Event(), threading.Event()
    def hold():
        with win.transport._state_lock:
            ready.set()
            release.wait(2)
    thread = threading.Thread(target=hold)
    thread.start()
    try:
        assert ready.wait(1)
        called = []
        monkeypatch.setattr(win, "_update_parameter_sources", lambda **_: called.append(True))
        win._idle_view_refresh_at = 0
        win._refresh_runtime_ui()
        assert not called
        assert not release.is_set()
    finally:
        release.set(); thread.join(2)


def test_instrument_cards_fit_their_controls(editor, app):
    _, win, _ = editor
    win.resize(1440, 900); win.show()
    win.tabs.setCurrentWidget(win.composition_panel)
    win.composition_panel.composition_tabs.setCurrentIndex(1)
    app.processEvents()
    for card in win.composition_panel.instrument_grid.cards.values():
        assert card.height() >= card.minimumSizeHint().height()
        assert not card.type_icon.pixmap().isNull()


@pytest.mark.parametrize("kind", ["BASS", "MELODY", "PAD", "CHORD", "DRUM_VOICE"])
def test_type_specific_and_live_parameter_controls_are_connected(editor, kind):
    gui, win, _ = editor
    if kind == "DRUM_VOICE":
        block = win.project.blocks[0].drum_voices[0]
        win.selected_block_id, win.selected_drum_voice_id = win.project.blocks[0].id, block.id
    else:
        block = win.project.blocks[1]
        block.block_type = kind
        win.selected_block_id, win.selected_drum_voice_id = block.id, None
    block.algorithm, block.mode, block.parameters = "Pattern", "LIVE", {"pattern": "1,0,1,0"}
    win.engine.regenerate(block)
    win._refresh_inspector()
    expected = {}
    for knob in win.inspector_page.findChildren(gui.Knob):
        binding = getattr(knob, "_auricle_parameter", None)
        if binding is None or binding[0] != block.id or not knob.isEnabled():
            continue
        value = knob.lo + (knob.hi - knob.lo) * (.65 if knob.value() < (knob.lo + knob.hi) / 2 else .35)
        value = round(value) if knob.integer else value
        if value == knob.value():
            continue
        knob.setValue(value)
        expected[binding[1]] = value
    win.transport.flush_gui_commands(notify=False)
    assert not win.transport.gui_command_errors
    assert "live_min_beats" in expected
    for key, value in expected.items():
        assert win.engine.parameter_influence.base_value(block, key) == value


def test_continuous_process_and_mutator_edits_keep_their_controls(editor, app):
    gui, win, _ = editor
    block = win.project.blocks[1]
    block.processes = [gui.Process("Delay", "velocity", .5)]
    win.selected_block_id = block.id
    win._refresh_inspector()
    page = win.inspector_page
    process_row = page.findChild(gui.ProcessInlineControls)
    process_knob = process_row.findChild(gui.Knob)
    mutator_row = page.findChild(gui.MutatorInlineControls)
    win.transport_worker.start()
    try:
        for value in (.2, .4, .6):
            mutator_row.amount.setValue(value)
            process_knob.setValue(process_knob.lo + (process_knob.hi - process_knob.lo) * value)
            wait_for(app, lambda: block.mutators[0].amount == value)
            app.processEvents()
            assert win.inspector_page is page
            assert page.findChild(gui.ProcessInlineControls) is process_row
            assert page.findChild(gui.MutatorInlineControls) is mutator_row
        assert not win.transport.gui_command_errors
    finally:
        win.transport_worker.stop()


def test_every_process_parameter_control_reaches_its_process(editor, app):
    gui, win, _ = editor
    block = win.project.blocks[1]
    win.selected_block_id = block.id
    requests = []
    original = win._set_process_parameter
    def capture(entity, process, key, value):
        requests.append((process, key, value))
        original(entity, process, key, value)
    win._set_process_parameter = capture
    for kind in gui.PROCESS_TYPES:
        process = gui.Process(kind, "velocity", .5)
        block.processes = [process]
        win._refresh_inspector()
        row = win.inspector_page.findChild(gui.ProcessInlineControls)
        assert row is not None
        for knob in row.findChildren(gui.Knob):
            value = knob.lo + (knob.hi - knob.lo) * (.65 if knob.value() < (knob.lo + knob.hi) / 2 else .35)
            value = round(value) if knob.integer else value
            if value == knob.value():
                continue
            old = len(requests); knob.setValue(value)
            assert len(requests) > old
        for combo in row.findChildren(QComboBox):
            if combo.count() > 1:
                old = len(requests)
                combo.setCurrentIndex((combo.currentIndex() + 1) % combo.count())
                assert len(requests) > old
        for checkbox in row.findChildren(QCheckBox):
            old = len(requests); checkbox.setChecked(not checkbox.isChecked())
            assert len(requests) > old
        expected = {key: value for obj, key, value in requests if obj is process}
        win.transport.flush_gui_commands(notify=False)
        assert not win.transport.gui_command_errors, kind
        assert all(process.parameters.get(key) == value for key, value in expected.items()), kind
        requests.clear()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.mark.parametrize("algorithm", GENERATORS)
def test_generator_and_common_controls_reach_the_correct_model_parameter(editor, app, algorithm):
    gui, win, _ = editor
    block = win.project.blocks[1]
    block.algorithm, block.parameters = algorithm, {}
    win.project.relations = []
    win.engine.regenerate(block)
    win.selected_block_id = block.id
    win._refresh_inspector()
    requests = []
    original = win._set_param
    def capture(entity, key, value):
        requests.append((entity, key, value))
        original(entity, key, value)
    win._set_param = capture
    for knob in win.inspector_page.findChildren(gui.Knob):
        binding = getattr(knob, "_auricle_parameter", None)
        if binding is None or binding[0] != block.id or not knob.isEnabled():
            continue
        value = knob.lo + (knob.hi - knob.lo) * (.65 if knob.value() < (knob.lo + knob.hi) / 2 else .35)
        value = round(value) if knob.integer else value
        if knob.value() == value:
            continue
        old = len(requests)
        knob.setValue(value)
        assert len(requests) == old + 1
        assert requests[-1][:2] == (block, binding[1])
    generator = win.inspector_page.findChild(gui.InspectorGroup, "inspectorGroup_GENERATOR")
    for combo in generator.findChildren(QComboBox):
        if combo.count() > 1:
            old = len(requests)
            combo.setCurrentIndex((combo.currentIndex() + 1) % combo.count())
            assert len(requests) > old
    for checkbox in generator.findChildren(QCheckBox):
        old = len(requests)
        checkbox.setChecked(not checkbox.isChecked())
        assert len(requests) > old
    for field in generator.findChildren(QLineEdit):
        if field.accessibleName() and field.accessibleName() != "Numeric value input":
            old = len(requests)
            field.setText("1,0,1,0"); field.editingFinished.emit()
            assert len(requests) > old
    expected = {key: value for entity, key, value in requests if entity is block}
    win.transport.flush_gui_commands(notify=False)
    assert not win.transport.gui_command_errors
    for key, value in expected.items():
        assert win.engine.parameter_influence.base_value(block, key) == value
