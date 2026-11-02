"""Automation uses Inspector units, types and current project boundaries."""
import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest

from auricle_core import Block, Project, MusicEngine, ensure_drum_voices
from auricle_catalogs import GENERATORS
from section_automation import parameter_specs, make_track, curve_range, parameter_curve, operation_range
from test_section_parameter_automation import setup, lane
from test_kit_preview_lifecycle import inspector


@pytest.mark.parametrize('length', [1, 16, 32, 128])
def test_all_inspector_knobs_load_matching_ranges_types_and_values(inspector, length):
    gui, win, _drum, _melody, errors = inspector
    checked = set()
    for role in ('MELODY', 'BASS', 'PAD', 'CHORD', 'DRUM_VOICE', 'KIT'):
        for algorithm in (GENERATORS if role == 'MELODY' else ('Pattern',)):
            if role in ('DRUM_VOICE', 'KIT'):
                block = Block(1, 'Kit', 'DRUM', mutators=[]); ensure_drum_voices(block)
                owner = block.drum_voices[0] if role == 'DRUM_VOICE' else block
                owner.algorithm = algorithm
            else:
                block = owner = Block(1, role, role, algorithm, 'LIVE', parameters={}, mutators=[])
            win._install_project(Project(length=length, root_note=57, scale='Minor', blocks=[block]), None, 'Audit')
            if role == 'DRUM_VOICE': win._select_drum_voice(owner.id)
            win.transport.flush_gui_commands(); gui.QApplication.instance().processEvents()
            specs = parameter_specs(win.engine, owner)
            for knob in win.inspector_page.findChildren(gui.Knob):
                binding = getattr(knob, '_auricle_parameter', None)
                if not binding or binding[0] != owner.id: continue
                key = binding[1]
                # The pinned kit host retains hidden controls from the previous
                # project. They are not controls of the current pitched owner.
                if key.startswith('kit_') and not getattr(owner, 'drum_voices', None): continue
                spec = specs[key]; checked.add(key)
                assert (spec.low, spec.high, spec.integer) == (knob.lo, knob.hi, knob.integer), (role, algorithm, key)
                expected = max(knob.lo, min(knob.hi, knob.value()))
                assert make_track(win.engine, owner, key)['value'] == pytest.approx(expected), (role, algorithm, key)
            for control in win.inspector_page.findChildren(gui.QLineEdit):
                binding = getattr(control, '_auricle_parameter', None)
                if binding and binding[0] == owner.id and specs[binding[1]].text:
                    assert make_track(win.engine, owner, binding[1])['value'] == control.text()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert {'structure_length', 'fill_density', 'euclidean_steps', 'walk_step',
            'geometry_speed', 'ls_iterations', 'kit_map_x', 'kit_density'} <= checked
    assert not errors


def test_inactive_generator_and_numeric_json_types_use_definitions():
    block = Block(1, 'Lead', 'MELODY', 'Pattern', parameters={'walk_step': 7.0, 'velocity_base': 1, 'pulses': 4.0})
    engine = MusicEngine(Project(blocks=[block]))
    specs = parameter_specs(engine, block)
    assert (specs['walk_step'].low, specs['walk_step'].high, specs['walk_step'].integer) == (1, 12, True)
    assert specs['pulses'].integer and not specs['velocity_base'].integer
    assert isinstance(make_track(engine, block, 'pulses')['value'], int)
    assert isinstance(make_track(engine, block, 'velocity_base')['value'], float)
    block.parameters['custom'] = 2.5
    engine.parameter_influence.write(block, 'custom', 1000., 'Composition: test')
    custom = parameter_specs(engine, block)['custom']
    assert (custom.default, custom.low, custom.high) == (2.5, -10., 10.)


@pytest.mark.parametrize('key,low,high,midpoint', [('structure_length', 1, 16, 8), ('fill_density', 0., 1., .5)])
def test_legacy_128_curve_uses_parameter_scale_without_early_saturation(key, low, high, midpoint):
    project, engine, block, section = setup(mode='LIVE')
    track = lane(engine, block, section, key=key, mode='curve', low=0, high=128, timing='bar',
                 curve={'enabled': True, 'shape': 'linear', 'points': [[0, 0], [1, 1]]})
    spec = parameter_specs(engine, block)[key]
    assert curve_range(track, spec) == (low, high)
    engine.section_automation.advance(0)
    assert block.parameters[key] == pytest.approx(low)
    engine.section_automation.advance(4)
    assert block.parameters[key] == pytest.approx(midpoint)
    assert track['low'] == 0 and track['high'] == 128  # Reading does not rewrite the document.


def test_project_length_change_invalidates_runtime_limits_and_zero_width_is_safe():
    project, engine, block, section = setup()
    track = lane(engine, block, section, key='structure_length', value=128)
    engine.section_automation.advance(0)
    assert block.parameters['structure_length'] == 16
    project.length = 8
    engine.section_automation.advance(4)
    assert block.parameters['structure_length'] == 8
    project.length = 1
    spec = parameter_specs(engine, block)['structure_rotation']
    assert (spec.low, spec.high) == (0, 0)
    track.update(parameter='structure_rotation', mode='curve')
    assert curve_range(track, spec) == (0, 0)
    assert all(y == .5 for x, y in parameter_curve(track, spec)['points'])


def test_subrange_and_relative_operations_keep_their_units():
    project, engine, block, section = setup()
    track = lane(engine, block, section, key='structure_length', low=4, high=12)
    spec = parameter_specs(engine, block)['structure_length']
    assert curve_range(track, spec) == (4, 12)
    assert spec.unit == 'steps' and spec.decimals() == 0 and spec.step() == 1
    assert operation_range(spec, 'add') == (-15, 15)
    assert spec.operand_unit('add') == 'steps'
    assert spec.operand_unit('multiply') == '×' and spec.decimals('multiply') == 5
    swing = parameter_specs(engine, block)['timing_swing']
    assert operation_range(swing, 'add') == (-.5, .5)


def test_boolean_point_threshold_matches_the_parameter_switch():
    project, engine, block, section = setup()
    track = lane(engine, block, section, key='pattern_reverse', mode='curve', low=0, high=1,
                 curve={'enabled': True, 'shape': 'linear', 'points': [[0, .5], [1, .5]]})
    spec = parameter_specs(engine, block)['pattern_reverse']
    assert parameter_curve(track, spec)['points'] == [[0, 1.], [1, 1.]]
    engine.section_automation.advance(0)
    assert block.parameters['pattern_reverse'] is True


def test_editor_adapts_legacy_limits_and_persists_edited_integer_points(inspector, tmp_path):
    gui, win, drum, melody, errors = inspector
    win._assign_composition_automation(melody.id, 'structure_length')
    win.show(); panel = win.composition_panel.automation_panel
    track = panel.track(); track.update(mode='curve', low=0, high=128)
    panel._details_signature = None; panel.load_details()
    assert (panel.low.value(), panel.high.value()) == (1, 16)
    assert panel.value.decimals() == panel.low.decimals() == panel.high.decimals() == panel.point_value.decimals() == 0
    assert panel.point_value.singleStep() == 1 and panel.point_value.suffix() == ' steps'
    assert '1…16 steps' in panel.destination.text()
    panel._preset_curve(False)
    assert (track['low'], track['high']) == (1, 16)
    panel.curve.resize(600, 104); panel.curve.selected = 1
    panel.curve._move(panel.curve.point_position((1, .51)))
    assert panel.point_value.value() == 9
    assert (track['curve']['points'][1][1] * 15 + 1) == pytest.approx(9)
    win.project.length = 8; panel.update_runtime()
    assert (panel.low.minimum(), panel.high.maximum()) == (1, 8)
    assert panel.point_value.maximum() == 8
    panel.full_range.click()
    assert (track['low'], track['high']) == (1, 8)
    assert win._write_project(tmp_path / 'ranges.json')
    from auricle_persistence import load_project
    saved = load_project(tmp_path / 'ranges.json').composition['sections'][0]['parameter_automation'][0]
    assert (saved['low'], saved['high']) == (1, 8)
    assert not errors


def test_multiply_editor_uses_fractional_dimensionless_factors(inspector):
    gui, win, drum, melody, errors = inspector
    panel = win.composition_panel.automation_panel
    panel.assign(melody.id, 'structure_length')
    panel.operation.setCurrentIndex(panel.operation.findData('multiply'))
    assert panel.value.decimals() > 0 and panel.value.suffix() == ' ×'
    assert (panel.low.minimum(), panel.high.maximum()) == (0, 4)
    assert not errors
