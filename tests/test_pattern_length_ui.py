"""Length changes preserve drum steps; source edits and piano labels stay usable."""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from auricle_core import load_project, save_project
from test_kit_preview_lifecycle import inspector


def resize_pattern(win, length):
    win.length.setValue(length)
    QTest.qWait(90)
    return win.drum_kit_layout.itemAt(0).widget()


def click_step(lane, local_index):
    x = int((local_index + .5) * lane.width() / len(lane.values))
    QTest.mouseClick(lane, Qt.LeftButton, pos=QPoint(x, 10))
    QTest.qWait(70)


def test_length_updates_all_voices_and_clamps_visible_page(inspector):
    gui, win, drum, melody, errors = inspector
    win.show()
    for length in (1, 8, 16, 24, 32, 64, 128):
        panel = resize_pattern(win, length)
        assert panel.pattern_length == length
        assert all(len(lane.values) == min(32, length) for lane in panel.pattern_lanes.values())
        assert len(drum.drum_voices[0].outputs['rhythm']) == length
    panel.page_selector.setCurrentIndex(3); QTest.qWait(90)
    panel = win.drum_kit_layout.itemAt(0).widget()
    assert panel.pattern_offset == panel.plan_ruler.offset == 96
    panel = resize_pattern(win, 8)
    assert panel.pattern_offset == 0
    assert len(next(iter(panel.pattern_lanes.values())).values) == 8
    assert not errors


def test_step_32_preserves_fractions_chances_and_undo(inspector, tmp_path):
    gui, win, drum, melody, errors = inspector
    voice = drum.drum_voices[0]
    voice.parameters.update(pattern='0.5,0,1,0', pattern_step_chances=[.35, 1, .75, 1])
    win.show(); panel = resize_pattern(win, 32)
    win.history_controller.flush()
    before = win.history_controller.snapshot()
    click_step(panel.pattern_lanes[voice.id], 31)
    win.history_controller.flush()
    assert len(voice.outputs['rhythm']) == 32 and voice.outputs['rhythm'][31] > 0
    values = [float(v) for v in voice.parameters['pattern'].split(',')]
    assert values[:4] == [.5, 0, 1, 0] and values[31] == 1
    assert voice.parameters['pattern_step_chances'] == [.35, 1, .75, 1] * 8
    after = win.history_controller.snapshot()
    win.history_controller.move(); QTest.qWait(60)
    assert win.history_controller.snapshot() == before
    win.history_controller.move(True); QTest.qWait(60)
    assert win.history_controller.snapshot() == after
    path = tmp_path / 'pattern32.json'
    save_project(win.project, str(path))
    saved = load_project(str(path)).blocks[0].drum_voices[0]
    assert saved.parameters['pattern'] == win.get_entity(voice.id).parameters['pattern']
    assert not errors


def test_shortening_keeps_hidden_tail_and_page_2_edits_absolute_step(inspector):
    gui, win, drum, melody, errors = inspector
    voice = drum.drum_voices[0]
    values = [0.] * 64; values[31] = .7; values[63] = .9
    voice.parameters['pattern'] = ','.join(map(str, values))
    win.show(); panel = resize_pattern(win, 8)
    click_step(panel.pattern_lanes[voice.id], 0)
    raw = [float(v) for v in voice.parameters['pattern'].split(',')]
    assert len(raw) == 64 and raw[31:] == values[31:]
    panel = resize_pattern(win, 64)
    panel.page_selector.setCurrentIndex(1); QTest.qWait(90)
    panel = win.drum_kit_layout.itemAt(0).widget()
    click_step(panel.pattern_lanes[voice.id], 31)
    edited = [float(v) for v in voice.parameters['pattern'].split(',')]
    assert edited[:-1] == raw[:-1] and edited[63] == 0
    assert not errors


def test_source_length_and_meter_are_independent_in_seq_and_live(inspector):
    gui, win, drum, melody, errors = inspector
    drum.parameters.update(kit_coordinated=True, kit_meter='7/8')
    drum.drum_voices[1].mode = 'LIVE'
    panel = resize_pattern(win, 32)
    assert all(len(lane.steps) == 32 and lane.bar_starts == (0, 14, 28)
               for lane in panel.plan_lanes.values())
    panel.view_selector.setCurrentIndex(2); QTest.qWait(90)
    panel = win.drum_kit_layout.itemAt(0).widget()
    assert set(panel.pattern_lanes) == {voice.id for voice in drum.drum_voices}
    assert all(len(lane.values) == 32 for lane in panel.pattern_lanes.values())
    assert panel.plan_ruler.steps == 32
    panel.view_selector.setCurrentIndex(0); QTest.qWait(90)
    panel = win.drum_kit_layout.itemAt(0).widget()
    assert panel.plan_ruler.steps == 32
    assert win.project.length == 32 and drum.parameters['kit_meter'] == '7/8'
    assert not errors


@pytest.mark.parametrize('meter,length,bars', [('4/4', 32, 1), ('7/8', 32, 1),
                                             ('5/4', 64, 2), ('2/4', 128, 1)])
def test_plan_output_pages_follow_length_across_bars_and_phrases(inspector, meter, length, bars):
    from coordinated_kit import KitCoordinator
    gui, win, drum, melody, errors = inspector
    drum.parameters.update(kit_coordinated=True, kit_meter=meter, kit_phrase_bars=bars, kit_variation=1)
    drum.drum_voices[1].mode = 'LIVE'
    panel = resize_pattern(win, length)
    win.show()
    voice = drum.drum_voices[0]
    history = {i: (i % 9) / 8 for i in range(length * 3)}
    win.transport.drum_output_history[voice.id] = history
    win.transport.running = True
    try:
        for page in range((length + 31) // 32):
            if panel.page_selector.currentIndex() != page:
                panel.page_selector.setCurrentIndex(page); QTest.qWait(90)
                panel = win.drum_kit_layout.itemAt(0).widget()
            count = min(32, length - page * 32)
            for cycle in (0, 1):
                start = cycle * length + page * 32
                for cursor in range(count):
                    win.engine.clock.position_beats = (start + cursor) * .25
                    panel.update_position()
                    assert panel.plan_ruler.cursor == cursor and panel.plan_ruler.steps == count
                    lane = panel.plan_lanes[voice.id]
                    assert lane.cursor == cursor and len(lane.steps) == count
                panel.view_selector.setCurrentIndex(0)
                expected = [KitCoordinator().plan(drum, win.project.seed, (start + i) * .25).at(voice.id, start + i)
                            for i in range(count)]
                assert lane.steps == expected
                panel.view_selector.setCurrentIndex(1)
                assert lane.output_values == [history[start + i] for i in range(count)]
                assert win.drum_kit_layout.itemAt(0).widget() is panel
                assert sum(lane.groups) == count
                assert panel.plan_ruler.offset == page * 32
                assert not errors
    finally:
        win.transport.running = False


def test_generator_preview_matches_rhythm_and_edit_converts_one_step(inspector):
    gui, win, drum, melody, errors = inspector
    voice = drum.drum_voices[0]
    voice.algorithm = 'Euclidean'
    voice.parameters.update(euclidean_steps=16, pulses=3, pattern='1',
                            pattern_rotation=7, pattern_scale=0, pattern_reverse=True)
    win.engine.generate(); win._refresh_inspector(); win.show(); QTest.qWait(80)
    panel = win.drum_kit_layout.itemAt(0).widget()
    lane = panel.pattern_lanes[voice.id]
    expected = list(lane.values)
    assert sum(expected) == 3 and expected == voice.outputs['rhythm']
    index = expected.index(0)
    click_step(lane, index)
    expected[index] = 1
    assert voice.algorithm == 'Pattern' and voice.outputs['rhythm'] == expected
    assert not errors


def test_source_preview_updates_in_place_when_generator_parameters_change(inspector):
    gui, win, drum, melody, errors = inspector
    voice = drum.drum_voices[0]
    voice.algorithm = 'Euclidean'; voice.parameters.update(euclidean_steps=16, pulses=3)
    win.engine.generate(); win._refresh_inspector()
    panel = win.drum_kit_layout.itemAt(0).widget()
    lane = panel.pattern_lanes[voice.id]
    win._set_param(voice, 'pulses', 7); QTest.qWait(90)
    assert win.drum_kit_layout.itemAt(0).widget() is panel
    assert panel.pattern_lanes[voice.id] is lane
    assert sum(lane.values) == 7
    assert not errors


@pytest.mark.parametrize('note, label', [(0, 'C-1'), (61, 'C#4'), (127, 'G9')])
def test_piano_key_hit_testing_and_labels_include_midi_range_edges(inspector, note, label):
    gui, win, drum, melody, errors = inspector
    roll = gui.PianoRollWidget(); roll.resize(500, 190)
    try:
        voice = drum.drum_voices[0]; voice.midi_note = note
        voice.outputs = {'rhythm': [1], 'pitch': [0], 'velocity': [.8]}
        roll.set_data(voice, project=win.project)
        roll.show(); QTest.qWait(30)
        lo, hi, top, height, right = roll._keyboard_geometry
        for key in range(lo, hi + 1):
            y = int(top + (hi - key + .5) * height / (hi - lo + 1))
            QTest.mouseMove(roll, QPoint(right - 5, y))
            assert roll.toolTip() == f'{roll.note_label(key)} · MIDI {key}'
        assert roll.note_label(note) == label
        assert 0 <= lo <= note <= hi <= 127
        assert not errors
    finally:
        roll.close()
