"""Explicit source composition, lifecycle, persistence and emitted LIVE data."""
from copy import deepcopy
from itertools import permutations

import pytest

from auricle_core import Block, Project, MusicEngine, Process, load_project
from performance_presets import preset_for_entity
from project_history import document_state
from test_coordinated_kit import kit, setup_transport
from test_cross_system_interactions import lead
from test_kit_preview_lifecycle import inspector


@pytest.mark.parametrize('order', list(permutations(('Macro: A', 'Technique: crescendo', 'Parameter Modulation'))))
@pytest.mark.parametrize('mode,expected', [('priority', .8), ('blend', .5), ('manual', .2)])
def test_resolution_is_independent_of_arrival_order(order, mode, expected):
    block = lead(); block.parameters['fill_density'] = .2
    engine = MusicEngine(Project(blocks=[block]))
    engine.parameter_influence.set_policy(block, 'fill_density', {'mode': mode})
    targets = {'Macro: A': .4, 'Technique: crescendo': .8, 'Parameter Modulation': .6}
    for source in order: engine.set_parameter(block, 'fill_density', targets[source], source=source)
    assert block.parameters['fill_density'] == pytest.approx(expected)
    assert document_state(engine.project, engine)['blocks'][0]['parameters']['fill_density'] == .2


def test_priority_weights_expose_lower_layers_and_manual_edits_keep_automation():
    block = lead(); block.parameters['fill_density'] = .2
    engine = MusicEngine(Project(blocks=[block])); influence = engine.parameter_influence
    engine.set_parameter(block, 'fill_density', .4, source='Macro: A')
    engine.set_parameter(block, 'fill_density', .8, source='Technique: A')
    influence.set_policy(block, 'fill_density', {'weights': {'Technique': .5}})
    assert block.parameters['fill_density'] == pytest.approx(.6)
    influence.set_policy(block, 'fill_density', {'priority': ['Macro', 'Technique', 'Modulation']})
    assert block.parameters['fill_density'] == .4
    influence.manual(block, 'fill_density', .9)
    assert block.parameters['fill_density'] == .4
    assert influence.describe(block, 'fill_density')['base'] == .9
    influence.remove(block, source_id='Macro: A'); influence.remove(block, source_id='Technique: A')
    assert block.parameters['fill_density'] == .9


def test_blend_normalizes_weights_by_category_and_bounds_integer_parameters():
    block = lead(); block.algorithm = 'Euclidean'; block.parameters['pulses'] = 4
    engine = MusicEngine(Project(blocks=[block]))
    influence = engine.parameter_influence
    influence.set_policy(block, 'pulses', {'mode': 'blend', 'weights': {'Manual': 0}})
    for i in range(10): engine.set_parameter(block, 'pulses', 2, source='Macro: same name', source_id=f'macro:{i}')
    engine.set_parameter(block, 'pulses', 8, source='Technique: X')
    assert block.parameters['pulses'] == 5 and isinstance(block.parameters['pulses'], int)
    influence.set_policy(block, 'pulses', {'mode': 'blend', 'weights': dict.fromkeys(('Manual', 'Macro', 'Technique', 'Modulation'), 0)})
    assert block.parameters['pulses'] == 4


@pytest.mark.parametrize('reverse', [False, True])
def test_multiple_macro_and_modulation_routes_are_averaged_not_overwritten(reverse):
    block = lead()
    project = Project(blocks=[block], macros=[{'name': 'Same', 'value': v, 'routes': [
        {'block_id': block.id, 'parameter': 'fill_density', 'min': 0, 'max': 1}]} for v in (.2, .8)])
    if reverse: project.macros.reverse()
    engine = MusicEngine(project); engine.generate()
    assert block.parameters['fill_density'] == pytest.approx(.5)
    sources = [lead(3), lead(4)]
    project.blocks.extend(sources)
    for source, value in zip(sources, (.3, .9)):
        process = Process('Parameter Modulation', 'rhythm', 1, {'destination_block': block.id,
            'destination_parameter': 'fill_density', 'source_min': 0, 'source_max': 1, 'min': 0, 'max': 1})
        source.processes = [process]
        source.outputs['rhythm'] = [value]
    for source in reversed(sources) if reverse else sources: engine.collect_parameter_modulations(source)
    engine.apply_pending_parameter_modulations()
    assert block.parameters['fill_density'] == pytest.approx(.6)
    assert len(engine.parameter_influence.describe(block, 'fill_density')['writes']) == 4
    for source in sources: source.processes.clear()
    engine.regenerate(sources[0])
    assert block.parameters['fill_density'] == pytest.approx(.5)
    project.macros.clear(); engine.generate()
    assert block.parameters['fill_density'] == 1  # authored base


def test_zero_route_depth_bypasses_and_deleted_delayed_routes_do_not_return():
    source, block = lead(1), lead(2)
    process = Process('Parameter Modulation', 'rhythm', 1, {'destination_block': 2,
        'destination_parameter': 'fill_density', 'source_min': 0, 'source_max': 1,
        'min': 0, 'max': 1, 'delay': 4})
    source.processes = [process]
    engine = MusicEngine(Project(blocks=[source, block]))
    engine.queue_parameter_modulation(source, 0, process)
    process.amount = 0
    for _ in range(7): engine.apply_pending_parameter_modulations()
    assert block.parameters['fill_density'] == 1
    assert not engine.delayed_parameter_modulations


@pytest.mark.parametrize('mode', ['SEQ', 'LIVE'])
def test_stopping_technique_reveals_latest_macro_in_both_modes(mode):
    block = lead(mode=mode)
    project = Project(blocks=[block], macros=[{'name': 'Gate', 'value': .2, 'routes': [
        {'block_id': block.id, 'parameter': 'gate', 'min': .2, 'max': 1}]}])
    engine = MusicEngine(project); engine.generate()
    engine.performance.start(block, 'staccato', beats=8)
    engine.performance.tick(True, beat_delta=2)
    technique = block.parameters['gate']
    project.macros[0]['value'] = .9; engine.generate()
    assert block.parameters['gate'] == technique
    engine.performance.stop(block.id)
    assert block.parameters['gate'] == pytest.approx(.92)
    if mode == 'SEQ': assert block.outputs['duration'][0] == pytest.approx(.92)
    else: assert engine.live_event(block)['duration'] == pytest.approx(.92)


def test_phrase_release_fades_to_current_lower_layers_and_preserves_manual_document():
    block = lead(); block.parameters['velocity_base'] = .6
    project = Project(blocks=[block], macros=[{'name': 'Dynamics', 'value': .3, 'routes': [
        {'block_id': block.id, 'parameter': 'velocity_base', 'min': 0, 'max': 1}]}])
    engine = MusicEngine(project); engine.generate()
    before = document_state(project, engine)
    engine.performance.start_phrase(project, 'opening_bloom', duration_beats=16)
    engine.performance.tick(True, beat_delta=1)
    engine.performance.stop_phrase('opening_bloom')
    project.macros[0]['value'] = .8; engine.apply_macros()
    engine.performance.tick(True, beat_delta=.5)
    assert .3 < block.parameters['velocity_base'] < .8
    engine.performance.tick(True, beat_delta=3)
    assert block.parameters['velocity_base'] == pytest.approx(.8)
    assert not engine.performance.active_phrase_releases
    assert document_state(project, engine)['blocks'] == before['blocks']
    assert not any(row['kind'] == 'Technique' for row in engine.parameter_influence.describe(block, 'velocity_base')['writes'])


def test_live_technique_transient_map_cannot_bypass_priority_or_manual_policy():
    block = lead(mode='LIVE')
    engine = MusicEngine(Project(blocks=[block]))
    engine.performance.start(block, 'staccato', beats=8)
    engine.performance.tick(True, beat_delta=2)
    engine.set_parameter(block, 'gate', .4, source='Macro: Gate')
    engine.parameter_influence.set_policy(block, 'gate', {'priority': ['Macro', 'Technique', 'Modulation']})
    assert engine.live_event(block)['duration'] == pytest.approx(.4)
    engine.parameter_influence.set_policy(block, 'gate', {'mode': 'manual'})
    assert engine.live_event(block)['duration'] == pytest.approx(.8)


def test_influence_controls_save_undo_redo_and_keep_dialog_bound_to_current_engine(inspector, tmp_path):
    from PySide6.QtTest import QTest
    from parameter_influence_ui import InfluenceDialog
    gui, win, drum, melody, errors = inspector
    dialog = InfluenceDialog(win, melody.id, 'velocity_base')
    dialog.show()
    dialog.mode.setCurrentIndex(dialog.mode.findData('blend'))
    dialog.weights['Technique'].setValue(.25)
    QTest.qWait(60)
    policy = deepcopy(win.project.parameter_policies)
    assert policy[str(melody.id)]['velocity_base']['mode'] == 'blend'
    assert policy[str(melody.id)]['velocity_base']['weights']['Technique'] == .25
    path = tmp_path / 'policies.json'
    assert win._write_project(str(path))
    assert load_project(str(path)).parameter_policies == policy
    dialog.mode.setCurrentIndex(dialog.mode.findData('manual')); QTest.qWait(60)
    win.history_controller.move(); dialog.refresh()
    assert win.project.parameter_policies == policy and dialog.mode.currentData() == 'blend'
    win.history_controller.move(True); dialog.refresh()
    assert dialog.mode.currentData() == 'manual'
    dialog.close()
    assert not errors
