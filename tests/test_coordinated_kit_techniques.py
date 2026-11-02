from statistics import mean

import pytest

from performance_presets import preset_for_entity
from test_coordinated_kit import kit, setup_transport


@pytest.mark.parametrize('technique', ['accelerando', 'ritardando'])
@pytest.mark.parametrize('mode', ['SEQ', 'LIVE'])
@pytest.mark.parametrize('meter', ['4/4', '3/4', '6/8', '7/8'])
def test_kit_agogics_change_subdivisions_and_preserve_time_and_anchors(technique, mode, meter):
    project, drum, voices, engine = kit((mode,), pattern='0', bars=1)
    drum.parameters['kit_meter'] = meter
    preset = preset_for_entity(drum, technique)
    assert 'timing_rate' not in {move.parameter for move in preset.moves}
    engine.performance.start(drum, technique, beats=16)
    engine.performance.tick(True, beat_delta=.1)
    first = engine.kit_plan(voices[0], 0)
    engine.performance.tick(True, beat_delta=14)
    last = engine.kit_plan(voices[0], 0)
    anchors = lambda plan: {(voice.id, i) for voice in voices[:2] for i in range(plan.length) if plan.at(voice.id, i).anchor}
    assert anchors(first) == anchors(last)
    count = lambda plan: sum(step.allowed for row in plan.rows.values() for step in row)
    assert count(first) < count(last) if technique == 'accelerando' else count(first) > count(last)
    assert project.tempo == 120
    assert all(engine.sequence_step_beats(voice) == .25 for voice in voices)
    if mode == 'SEQ':
        engine.generate_block(drum)
        assert all(voices[0].outputs['rhythm'][i] for i in range(last.length) if last.at(voices[0].id, i).anchor)
    else:
        for i in range(last.length):
            hit = engine.live_event(voices[0], beat=i*.25)
            if last.at(voices[0].id, i).anchor: assert hit is not None


@pytest.mark.parametrize('technique', ['accelerando', 'ritardando'])
@pytest.mark.parametrize('mode', ['SEQ', 'LIVE'])
def test_audible_subdivision_change_stays_on_shared_midi_grid(monkeypatch, technique, mode):
    project, drum, voices, engine = kit((mode,), pattern='0', bars=1)
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    engine.performance.start(drum, technique, beats=32)
    for i in range(128): tick(i*.125)
    onsets = [t for t, message in sent if message.type == 'note_on']
    early = sum(0 <= t < 4 for t in onsets); late = sum(12 <= t < 16 for t in onsets)
    assert early < late if technique == 'accelerando' else early > late
    assert all(abs(t/.125 - round(t/.125)) < 1e-6 for t in onsets)
    assert {message.note for _, message in sent if message.type == 'note_on'} <= {voice.midi_note for voice in voices}
    transport.stop()


def test_independent_kit_retains_tempo_gestures_and_coordinated_stop_restores_settings():
    project, drum, voices, engine = kit(('SEQ',), bars=1)
    drum.parameters['kit_coordinated'] = False
    assert {move.parameter for move in preset_for_entity(drum, 'accelerando').moves} == {'timing_rate'}
    drum.parameters['kit_coordinated'] = True
    original = dict(drum.parameters)
    engine.performance.start(drum, 'accelerando', beats=16); engine.performance.tick(True, beat_delta=8)
    assert drum.parameters['kit_complexity'] != original['kit_complexity']
    engine.performance.stop(drum.id)
    assert drum.parameters == original
