"""Regressions for fragmented custom-note kits and the sixteen-step playhead."""
from dataclasses import asdict

import pytest

from auricle_core import Block, DrumVoice, MusicEngine, Mutator, Process, Project, ensure_drum_voices, load_project, save_project
from coordinated_kit import voice_role
from test_coordinated_kit import setup_transport
from test_kit_preview_lifecycle import inspector


def hardware_kit(mode="SEQ"):
    drum = Block(1, "Hardware", "DRUM", midi_channel=10, midi_port="capture", mutators=[],
                 parameters={"kit_coordinated": True, "kit_phrase_bars": 4, "kit_fill": 1})
    voices = []
    for i, voice in enumerate(ensure_drum_voices(drum)):
        data = asdict(voice)
        data["midi_note"], data["mode"] = i, mode
        data["parameters"].pop("kit_role")  # existing project before roles were introduced
        voices.append(DrumVoice(**data))
    drum.drum_voices = voices
    project = Project(blocks=[drum], seed=314)
    return project, drum, voices, MusicEngine(project)


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_non_gm_kit_has_an_audible_foundation_in_every_bar(monkeypatch, mode):
    project, drum, voices, engine = hardware_kit(mode)
    assert [voice_role(v) for v in voices] == ["kick", "snare", "closed_hat", "open_hat", "clap", "perc"]
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    for slot in range(64):
        tick(slot * .125)
    onsets = {(round(t / .125), message.note) for t, message in sent if message.type == "note_on"}
    for bar in range(4):
        assert {(bar * 16, 0), (bar * 16 + 8, 0)} <= onsets
        assert {(bar * 16 + 4, 1), (bar * 16 + 12, 1)} <= onsets
        for step in (0, 2, 4, 6, 8, 10):
            assert (bar * 16 + step, 2) in onsets
    assert all(message.channel == 9 for _, message in sent if message.type == "note_on")


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
@pytest.mark.parametrize("modifier", ["Rotate", "Invert", "Compare"])
def test_rhythm_modifiers_do_not_erase_kit_anchors(mode, modifier):
    project, drum, voices, engine = hardware_kit(mode)
    drum.parameters["kit_fill"] = 0
    for voice in voices:
        voice.algorithm = "Pattern"
        voice.parameters.update(pattern="0", velocity_base=.65, velocity_accent=0)
        if modifier == "Compare":
            voice.processes = [Process("Compare", "rhythm", 1, {"threshold": 2})]
        else:
            voice.mutators = [Mutator(modifier, .3, "rhythm")]
        plan = engine.kit_plan(voice, 0)
        if mode == "SEQ":
            engine.generate_block(voice)
            hits = voice.outputs["rhythm"]
        else:
            hits = [bool(engine.live_event(voice, i * .25)) for i in range(64)]
        assert all(not plan.at(voice.id, i).anchor or hit for i, hit in enumerate(hits))
        assert all(not hit or plan.at(voice.id, i).allowed for i, hit in enumerate(hits))
        voice.parameters["fill_density"] = 0
        if mode == "SEQ":
            engine.generate_block(voice)
            assert not any(voice.outputs["rhythm"])
        else:
            assert all(engine.live_event(voice, i * .25) is None for i in range(64))


def test_explicit_roles_survive_loading_and_renaming(tmp_path):
    project, drum, voices, engine = hardware_kit()
    voices[0].parameters["kit_role"] = "free"
    path = tmp_path / "hardware.json"
    save_project(project, str(path))
    loaded = load_project(str(path))
    assert voice_role(loaded.blocks[0].drum_voices[0]) == "free"
    loaded.blocks[0].drum_voices[1].name = "My hardware pad"
    loaded.blocks[0].drum_voices[1].midi_note = 101
    assert voice_role(loaded.blocks[0].drum_voices[1]) == "snare"


def test_auto_roles_repairs_saved_perc_misclassification_without_changing_routing(inspector):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = inspector
    drum.parameters["kit_coordinated"] = True
    for i, voice in enumerate(drum.drum_voices):
        voice.parameters["kit_role"] = "perc"
        voice.midi_note = i
        voice.midi_channel = i + 3
        voice.midi_channel_override = True
        voice.midi_port = "hardware"
    routing = [(v.midi_note, v.midi_channel, v.midi_port) for v in drum.drum_voices]
    win._refresh_inspector()
    panel = win.drum_kit_layout.itemAt(0).widget()
    assert "Kick" in panel.role_warning.text()
    panel.findChild(gui.QPushButton, "kitAutoRoles").click()
    QTest.qWait(65)
    assert [voice_role(v) for v in drum.drum_voices] == ["kick", "snare"]
    assert routing == [(v.midi_note, v.midi_channel, v.midi_port) for v in drum.drum_voices]
    assert not errors


def test_ruler_and_every_lane_traverse_all_sixteen_steps_even_when_silent(inspector):
    gui, win, drum, melody, errors = inspector
    drum.parameters.update(kit_coordinated=True, kit_phrase_bars=4)
    for voice in drum.drum_voices:
        voice.muted = True
    win._refresh_inspector()
    panel = win.drum_kit_layout.itemAt(0).widget()
    win.transport.running = True
    try:
        for bar in (0, 3, 4):
            for step in range(16):
                win.engine.clock.position_beats = bar * 4 + step * .25
                panel.update_position()
                assert panel.plan_ruler.cursor == step
                for lane in panel.plan_lanes.values():
                    assert lane.cursor == step and len(lane.steps) == 16
                    assert not any(s.allowed for s in lane.steps)
                    frame = lane.grab().toImage()
                    color = frame.pixelColor(int((step + .5) * lane.width() / 16), 1)
                    assert color.red() > 230 and color.green() > 150  # visible cursor on a REST
    finally:
        win.transport.running = False
    assert not errors
