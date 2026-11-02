"""Groove-map edits must reach the model and survive transport boundaries."""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from auricle_core import load_project, save_project
from drum_rhythm import MAP_DEFAULTS
from test_midi_learn_runtime_ui import app, editor


@pytest.fixture
def map_editor(editor):
    gui, win, _ = editor
    drum = win.project.blocks[0]
    drum.parameters.update(kit_coordinated=True, kit_engine="map")
    for key in MAP_DEFAULTS:
        drum.parameters.pop(key, None)
    win.selected_block_id = drum.id
    win.selected_drum_voice_id = None
    win._refresh_inspector()
    panel = win.drum_kit_layout.itemAt(0).widget()
    yield gui, win, drum, panel.rhythm_panel
    win.transport.stop(advance=False)


def values(drum):
    return tuple(drum.parameters.get(key, default) for key, default in
                 (("kit_map_x", .25), ("kit_map_y", .25)))


def choose(rhythm, method):
    if method == "preset":
        index = rhythm.map_preset.findText("Broken drive")
        expected = rhythm.map_preset.itemData(index)
        rhythm.map_preset.setCurrentIndex(index)
    else:
        pad = rhythm.map_pad
        QTest.mouseClick(pad, Qt.LeftButton, pos=QPoint(pad.width() - 15, 15))
        # The pad emits coordinates at the control's 0.001 resolution.
        expected = tuple(round(value, 3) for value in pad.coordinates())
    return tuple(expected)


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("method", ["pad", "preset"])
def test_first_map_edit_survives_repeated_play_stop_without_musical_preset(map_editor, mode, method):
    _, win, drum, rhythm = map_editor
    drum.mode = mode
    for voice in drum.drum_voices:
        voice.mode = mode
    assert not any(key in drum.parameters for key in ("kit_map_x", "kit_map_y"))
    expected = choose(rhythm, method)
    assert expected != (.25, .25)
    for _ in range(3):
        win.transport.start(mode="blocks")
        win.transport.tick()
        rhythm.update_state(True)
        assert values(drum) == pytest.approx(expected)
        assert rhythm.map_pad.coordinates() == pytest.approx(expected)
        win.transport.stop(advance=False)
        assert values(drum) == pytest.approx(expected)


@pytest.mark.parametrize("method", ["pad", "preset"])
def test_ui_refresh_cannot_replace_a_pending_map_edit_with_old_coordinates(map_editor, method):
    _, win, drum, rhythm = map_editor
    expected = choose(rhythm, method)
    rhythm.update_state(True)
    assert rhythm.map_pad.coordinates() == pytest.approx(expected)
    if method == "preset":
        assert rhythm.map_preset.currentText() == "Broken drive"
    win.transport.flush_gui_commands(notify=False)
    assert values(drum) == pytest.approx(expected)


def test_latest_drag_position_wins_even_when_returning_to_the_stored_value(map_editor):
    _, win, drum, rhythm = map_editor
    drum.parameters.update(kit_map_x=.25, kit_map_y=.25)
    for x, y in ((.9, .8), (.7, .6), (.4, .3), (.25, .25)):
        rhythm.map_pad.setCoordinates(x, y)
        rhythm.map_pad.coordinatesChanged.emit(x, y)
    assert len(win.transport.gui_command_queue) == 1
    win.transport.start()
    rhythm.update_state(True)
    assert values(drum) == (.25, .25)
    assert rhythm.map_pad.coordinates() == (.25, .25)


def test_two_knob_edits_keep_both_pending_axes_and_survive_composition_start(map_editor):
    _, win, drum, rhythm = map_editor
    knobs = {knob.objectName(): knob for knob in rhythm.knobs}
    knobs["kit_map_x"].setValue(.84)
    knobs["kit_map_y"].setValue(.67)
    rhythm.update_state(True)
    assert rhythm.map_pad.coordinates() == pytest.approx((.84, .67))
    win.transport.start(mode="composition")
    assert values(drum) == pytest.approx((.84, .67))
    win.transport.stop(advance=False)
    win.transport.start(mode="blocks")
    assert values(drum) == pytest.approx((.84, .67))


def test_map_edit_updates_manual_base_even_if_it_equals_an_automatic_value(map_editor):
    _, win, drum, rhythm = map_editor
    drum.parameters.update(kit_map_x=.25, kit_map_y=.25)
    win.engine.set_parameter(drum, "kit_map_x", .8, source="Technique:test", source_id="technique:test")
    rhythm.map_pad.setCoordinates(.8, .6)
    rhythm.map_pad.coordinatesChanged.emit(.8, .6)
    win.transport.start()
    assert values(drum) == pytest.approx((.8, .6))
    assert win.engine.parameter_influence.base_value(drum, "kit_map_x") == .8


def test_map_coordinates_round_trip_through_project_save_and_reload(map_editor, tmp_path):
    _, win, drum, rhythm = map_editor
    expected = choose(rhythm, "preset")
    win.transport.flush_gui_commands(notify=False)
    path = tmp_path / "groove.json"
    save_project(win.project, str(path))
    restored = load_project(str(path))
    assert values(restored.blocks[0]) == pytest.approx(expected)
    win._install_project(restored, str(path), "Groove reload")
    win.transport.start()
    assert values(win.project.blocks[0]) == pytest.approx(expected)


def test_runtime_readback_shows_automatic_modulation_without_editing_the_manual_map(map_editor):
    _, win, drum, rhythm = map_editor
    drum.parameters.update(kit_map_x=.3, kit_map_y=.4)
    assert win.engine.set_parameter(drum, "kit_map_y", .9, source="Relations", source_id="test-map")
    rhythm.update_state(True)
    assert rhythm.map_pad.coordinates() == pytest.approx((.3, .9))
    assert win.engine.parameter_influence.base_value(drum, "kit_map_y") == .4
    assert len(win.transport.gui_command_queue) == 0


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_map_stays_authored_across_pattern_wraps(map_editor, monkeypatch, mode):
    import time
    _, win, drum, rhythm = map_editor
    drum.mode = mode
    for voice in drum.drum_voices:
        voice.mode = mode
    expected = choose(rhythm, "preset")
    now = [time.monotonic()]
    with monkeypatch.context() as patch:
        patch.setattr("auricle_transport.time.monotonic", lambda: now[0])
        win.transport.start()
        cycle = win.engine.kit_plan(drum.drum_voices[0], 0).length
        for slot in range(cycle * 3 + 1):
            now[0] += .125
            win.transport.tick()
            if slot % cycle == 0:
                rhythm.update_state(True)
                assert values(drum) == pytest.approx(expected)
                assert rhythm.map_pad.coordinates() == pytest.approx(expected)
        win.transport.stop(advance=False)


def test_live_worker_and_midi_readback_keep_the_same_map_controls(map_editor, app):
    from midi_learn import normalize_mapping
    from test_midi_learn_runtime_ui import cc, target, wait_for
    _, win, drum, rhythm = map_editor
    win.transport_worker.start()
    try:
        expected = choose(rhythm, "preset")
        win._play_clicked(True)
        wait_for(app, lambda: values(drum) == pytest.approx(expected))
        win.project.midi_mappings = [normalize_mapping({
            "source": {"type": "cc", "number": 74},
            "target": target(drum, "kit_map_x"), "pickup": False,
        })]
        win._handle_midi_input("Controller", cc(64))
        wait_for(app, lambda: values(drum)[0] == pytest.approx(64 / 127))
        rhythm.update_state(True)
        assert rhythm.map_pad.coordinates() == pytest.approx((64 / 127, expected[1]))
        win._stop_clicked(False)
        win._play_clicked(True)
        assert values(drum) == pytest.approx((64 / 127, expected[1]))
    finally:
        win.transport_worker.stop()
