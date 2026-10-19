"""Accepted-output monitoring, per-pass chances and routing-safe voice editing."""
from copy import deepcopy

import pytest

from auricle_core import Block, Process, Mutator, MusicEngine, Project, load_project, save_project
from drum_editing import sound_snapshot, apply_sound
from pattern_chance import step_chances, chance_at
from test_coordinated_kit import kit, setup_transport
from test_kit_preview_lifecycle import inspector


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("gate", ["process", "density", "probability", "voice_mute", "kit_mute", "chance"])
def test_output_records_silence_after_every_gate_even_when_plan_has_anchors(monkeypatch, mode, gate):
    project, drum, voices, engine = kit((mode,), pattern="1", bars=1)
    if gate == "process":
        drum.processes = [Process("Compare", "velocity", 1, {"threshold": 2})]
    elif gate == "density":
        drum.parameters["kit_density"] = 0
    elif gate == "probability":
        voices[0].parameters["event_probability"] = 0
    elif gate == "voice_mute":
        voices[0].muted = True
    elif gate == "kit_mute":
        drum.muted = True
    else:
        voices[0].parameters["pattern_step_chances"] = [0]
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    tick(0); tick(.125)
    assert transport.drum_output_history[voices[0].id] == {0: 0., 1: 0.}
    assert not [msg for _, msg in sent if msg.type == "note_on" and msg.note == voices[0].midi_note]
    assert 2 not in transport.drum_output_history[voices[0].id]
    transport.stop()


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_output_has_actual_midi_onsets_across_bars_and_no_port_still_monitors(monkeypatch, mode):
    project, drum, voices, engine = kit((mode,), pattern="1", bars=1)
    drum.parameters.update(kit_meter="7/8", kit_protect_anchors=False)
    drum.mutators = [Mutator("Rotate", .2, "rhythm")]
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    for i in range(28):tick(i * .125)
    for voice in voices:
        history = transport.drum_output_history[voice.id]
        onsets = {round(t / .125) for t, msg in sent if msg.type == "note_on" and msg.note == voice.midi_note}
        assert {i for i, v in history.items() if v > 0} == onsets
        for t, msg in sent:
            if msg.type == "note_on" and msg.note == voice.midi_note:
                assert abs(msg.velocity / 127. - history[round(t / .125)]) <= 1 / 127.
    transport.stop(); transport.outputs.clear(); transport.start()
    assert not transport.drum_output_history
    tick(3.375)
    assert all(0 in transport.drum_output_history[v.id] for v in voices)
    assert any(transport.drum_output_history[v.id][0] > 0 for v in voices)
    transport.stop()


def test_output_history_is_bounded_and_skipped_slots_are_not_fabricated(monkeypatch):
    project, drum, voices, engine = kit(pattern="1", bars=1)
    transport, _, _, tick = setup_transport(monkeypatch, project, engine)
    tick(0); tick(1)
    assert set(transport.drum_output_history[voices[0].id]) == {0, 8}
    for slot in range(500):
        transport._observe_kit_output(voices[0], slot, {"velocity": .4})
    assert len(transport.drum_output_history[voices[0].id]) == 384
    assert min(transport.drum_output_history[voices[0].id]) == 116
    transport.stop()


def test_chances_are_clamped_default_to_one_and_follow_source_transforms():
    p = {"pattern": "1,1,1,1", "pattern_step_chances": [0, .25, .5, 1]}
    assert [chance_at(p, i, 4) for i in range(4)] == [0, .25, .5, 1]
    p.update(pattern_reverse=True, pattern_rotation=1, structure_rotation=1)
    assert [chance_at(p, i, 4) for i in range(4)] == [.25, 0, 1, .5]
    p["pattern_step_chances"] = [-3, "nan", 9]
    assert step_chances(p) == [0, 1, 1, 1]
    p["pattern_step_chances"] = None
    assert step_chances(p) == [1] * 4


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_step_chance_is_resampled_per_pass_and_reproducible_on_restart(monkeypatch, mode):
    project, drum, voices, engine = kit((mode,), pattern="1,1,1,1", bars=1)
    project.length = 4
    voices[0].parameters.update(kit_role="closed_hat", pattern_step_chances=[1, 0, .25, 0])
    for v in voices[1:]:v.muted = True
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    for i in range(256): tick(i * .125)
    onsets = {round(t / .125) for t, msg in sent if msg.type == "note_on"}
    assert set(range(0, 256, 4)) <= onsets
    assert not any(i % 4 in (1, 3) for i in onsets)
    variable = {i for i in onsets if i % 4 == 2}
    assert 5 < len(variable) < 28
    transport.stop()
    # The seed and absolute slot determine the same future gate after replay.
    assert {i for i in range(256) if engine.pattern_step_allowed(voices[0], i)} == onsets


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_step_chance_works_outside_kit_and_does_not_modify_cached_source(monkeypatch, mode):
    block = Block(1, "Pattern", "MELODY", "Pattern", mode=mode, midi_port="capture",
                  parameters={"pattern": "1,2,3,4", "pattern_step_chances": [1, 0, 1, 0],
                              "live_min_beats": .25, "live_max_beats": .25}, mutators=[])
    project=Project(length=4, tempo=120, blocks=[block]); engine=MusicEngine(project)
    transport, _, sent, tick = setup_transport(monkeypatch, project, engine)
    source = deepcopy(block.outputs)
    for i in range(8): tick(i * .125)
    assert len([msg for _, msg in sent if msg.type == "note_on"]) == 4
    if mode == "SEQ":assert block.outputs == source
    transport.stop()


def test_sound_copy_is_detached_and_preserves_all_destination_identity_fields():
    project, drum, voices, engine = kit()
    source, target = voices[:2]
    source.algorithm = "Pattern"
    source.parameters.update(pattern_step_chances=[.25, 1], motif_id="example")
    source.mutators = [Mutator("Rotate", .2, "rhythm")]
    source.processes = [Process("Counter", "velocity", .3, {"length": 9})]
    target.name="Hardware Snare"; target.midi_channel=4; target.midi_channel_override=True
    target.midi_note=7; target.midi_port="Other"; target.muted=True; target.color="#123456"
    preserved = {k: deepcopy(getattr(target, k)) for k in ("id", "parent_id", "name", "mode", "midi_channel",
                 "midi_channel_override", "midi_note", "midi_port", "muted", "color")}
    role=target.parameters["kit_role"]
    snapshot=sound_snapshot(source); apply_sound(target, snapshot)
    assert target.parameters["kit_role"] == role
    assert all(getattr(target,k)==v for k,v in preserved.items())
    assert sound_snapshot(target) == snapshot
    target.parameters["pattern_step_chances"][0] = 0
    target.processes[0].parameters["length"] = 2
    assert source.parameters["pattern_step_chances"][0] == snapshot["parameters"]["pattern_step_chances"][0] == .25
    assert source.processes[0].parameters["length"] == 9


def test_output_view_switches_in_place_and_marks_unknown_vs_rest(inspector):
    gui, win, drum, melody, errors = inspector
    drum.parameters.update(kit_coordinated=True, kit_meter="7/8")
    win._refresh_inspector(); panel=win.drum_kit_layout.itemAt(0).widget()
    voice=drum.drum_voices[0]
    win.transport.drum_output_history[voice.id]={0: .8, 1: 0}
    panel.view_selector.setCurrentIndex(1)
    lane=panel.plan_lanes[voice.id]
    assert lane.output_values[:3] == [.8, 0, None]
    assert len(lane.output_values)==14
    panel.view_selector.setCurrentIndex(0)
    assert lane.output_values is None and lane.steps[0].anchor
    assert win.drum_kit_layout.itemAt(0).widget() is panel
    assert not errors


def test_probability_editor_updates_steps_without_rebuilding_and_round_trips(inspector,tmp_path):
    from PySide6.QtTest import QTest
    gui,win,drum,melody,errors=inspector
    voice=drum.drum_voices[0]
    win._select_drum_voice(voice.id);QTest.qWait(65)
    editor=win.inspector_scroll.widget().findChild(gui.PatternChanceEditor)
    editor.step.setValue(2);editor.chance.setValue(35)
    assert voice.parameters["pattern_step_chances"] == [1,.35,1,1]
    assert win.inspector_scroll.widget().findChild(gui.PatternChanceEditor) is editor
    voice.parameters["pattern"]="1,1";editor.refresh()
    editor.step.setValue(99)
    assert editor.step.value()==2
    assert "pattern_step_chances" not in win.engine.parameter_catalog(voice)
    p=tmp_path/'chances.json';save_project(win.project,str(p))
    assert load_project(str(p)).blocks[0].drum_voices[0].parameters["pattern_step_chances"] == [1,.35,1,1]
    editor.findChild(gui.QPushButton,"patternChanceReset").click()
    assert step_chances(voice.parameters)==[1,1]
    assert not errors


def test_paste_and_undo_keep_target_mode_and_routing_and_do_not_restart_transport(inspector):
    from PySide6.QtTest import QTest
    gui,win,drum,melody,errors=inspector
    source,target=drum.drum_voices
    source.parameters["pattern"]="1,1,0,0";source.mutators=[Mutator("Reverse",.5,"rhythm")]
    target.mode="LIVE";target.midi_note=72
    before=sound_snapshot(target)
    win.engine.clock.position_beats=9.75
    win.engine.live_state[target.id]={"events": 39, "walk_value": 72, "phase_index": 3}
    win._select_drum_voice(source.id);QTest.qWait(65)
    panel=win.drum_kit_layout.itemAt(0).widget()
    assert panel.copy_voice_button.isEnabled()
    panel.copy_voice_button.click()
    win._select_drum_voice(target.id);QTest.qWait(65)
    panel=win.drum_kit_layout.itemAt(0).widget()
    assert panel.paste_voice_button.isEnabled()
    panel.paste_voice_button.click();QTest.qWait(65)
    assert target.parameters["pattern"]=="1,1,0,0" and target.mutators==source.mutators
    assert target.mode=="LIVE" and target.midi_note==72
    assert win.engine.clock.position_beats==9.75
    assert win.engine.live_state[target.id]=={"events": 39, "phase_index": 39}
    panel=win.drum_kit_layout.itemAt(0).widget()
    panel._paste_voice(target,undo=True);QTest.qWait(65)
    assert sound_snapshot(target)==before
    assert target.mode=="LIVE" and target.midi_note==72
    win._install_project(Project(blocks=[Block(2,"New","MELODY",mutators=[])]),None,"New")
    assert win._drum_voice_clipboard is None and win._voice_paste_undo=={}
    assert not errors
