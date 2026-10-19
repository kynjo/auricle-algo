"""Shared arrangement, audible MIDI phase, source relations and pinned UI."""
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from auricle_core import Block, MusicEngine, Project, Transport, Mutator, ensure_drum_voices, load_project, save_project
from auricle_catalogs import GENERATORS
from coordinated_kit import CREATIVE_DEFAULTS, KitCoordinator, voice_role
from motif_engine import Motif
from test_kit_preview_lifecycle import inspector


def kit(modes=("SEQ", "LIVE"), pattern="1", bars=2):
    drum = Block(1, "Kit", "DRUM", midi_channel=10, midi_port="capture", mutators=[],
                 parameters={"kit_coordinated": True, "kit_phrase_bars": bars,
                             **dict.fromkeys(CREATIVE_DEFAULTS, 0.)})
    voices = ensure_drum_voices(drum)
    for i, voice in enumerate(voices):
        voice.mode, voice.algorithm = modes[i % len(modes)], "Pattern"
        voice.parameters.update(pattern=pattern, velocity_base=.6, velocity_range=0,
                                velocity_accent=0, gate=1.5, live_gate=1.5,
                                fill_density=1, event_probability=1)
    project = Project(length=7, seed=314, tempo=120, blocks=[drum])
    return project, drum, voices, MusicEngine(project)


@pytest.mark.parametrize("style,anchors,backbeats", [
    ("straight", {0, 8}, {4, 12}), ("half_time", {0, 10}, {8}),
    ("broken", {0, 7, 10}, {4, 12}),
])
def test_shared_roles_keep_anchors_and_exclude_conflicting_hats(style, anchors, backbeats):
    project, drum, voices, engine = kit()
    drum.parameters["kit_style"] = style
    plan = engine.kit_plan(voices[0], 0)
    kick, snare, closed, opened, clap, tom = voices
    assert {i for i in range(16) if plan.at(kick.id, i).force} == anchors
    assert {i for i in range(16) if plan.at(snare.id, i).force or plan.at(clap.id, i).force} == backbeats
    for i in range(plan.length):
        assert not (plan.at(closed.id, i).allowed and plan.at(opened.id, i).allowed)
        assert not (plan.at(snare.id, i).force and plan.at(clap.id, i).force)
    old = deepcopy(plan.rows)
    drum.drum_voices.reverse()
    assert KitCoordinator().plan(drum, project.seed, 0).rows == old


def test_fill_has_one_lead_only_in_last_beat_and_falls_back_to_available_roles():
    project, drum, voices, engine = kit(bars=4)
    drum.parameters["kit_fill"] = 1
    plan = engine.kit_plan(voices[0], 0)
    assert not any(step.fill for row in plan.rows.values() for step in row[:-4])
    for slot in range(60, 64):
        hits = [vid for vid, row in plan.rows.items() if row[slot].allowed]
        assert len(hits) == 1 and plan.at(hits[0], slot).fill
    assert len({vid for vid, row in plan.rows.items() if any(s.fill for s in row)}) >= 2
    for voice in voices[1:]:
        voice.muted = True
    fallback = engine.kit_plan(voices[0], 0)
    assert all(fallback.at(voices[0].id, slot).fill for slot in range(60, 64))
    voices[0].muted = True
    assert not any(step.allowed for row in engine.kit_plan(voices[0], 0).rows.values() for step in row)


def test_duplicate_roles_share_hits_instead_of_layering_every_voice():
    project, drum, voices, engine = kit()
    for voice in voices:
        voice.parameters["kit_role"] = "kick"
    plan = engine.kit_plan(voices[0], 0)
    for i in range(plan.length):
        assert sum(plan.at(v.id, i).allowed for v in voices) <= 1
    assert sum(plan.at(v.id, 0).force for v in voices) == 1


@pytest.mark.parametrize("algorithm", GENERATORS)
@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_every_generator_runs_with_shared_anchors_and_respects_master_silence(algorithm, mode):
    project, drum, voices, engine = kit((mode,), pattern="0", bars=1)
    voice = voices[0]
    voice.algorithm = algorithm
    voice.parameters.update(probability=0, pulses=0, bres_pulses=0, markov_rest=1)
    if mode == "SEQ":
        engine.generate()
        hits = voice.outputs["rhythm"]
    else:
        hits = [bool(engine.live_event(voice, beat=i * .25)) for i in range(16)]
    assert hits[0] and hits[8]
    allowed = {0, 6, 8, 10, 14}
    assert all(not hit or i in allowed for i, hit in enumerate(hits))
    drum.parameters.update(kit_density=0, kit_fill=1)
    if mode == "SEQ":
        engine.generate()
        assert not any(voice.outputs["rhythm"])
    else:
        assert all(engine.live_event(voice, beat=i * .25) is None for i in range(16))


def test_final_mask_survives_rhythm_mutation_and_free_voice_remains_independent():
    project, drum, voices, engine = kit(("SEQ",))
    for voice in voices:
        voice.mutators = [Mutator("Rotate", .25, "rhythm")]
    voices[-1].parameters["kit_role"] = "free"
    engine.generate()
    plan = engine.kit_plan(voices[0], 0)
    for voice in voices[:-1]:
        assert all(not hit or plan.at(voice.id, i).allowed for i, hit in enumerate(voice.outputs["rhythm"]))
    assert len(voices[-1].outputs["rhythm"]) == project.length
    assert all(voices[-1].outputs["rhythm"])
    assert engine.coordinated_drum(voices[-1]) is None


@pytest.mark.parametrize("cycle", [7, 32])
def test_source_cycle_keeps_phase_across_shared_phrase_boundaries(cycle):
    source_hits = {0, 3, 17, 22}
    pattern = ",".join(str(int(i in source_hits)) for i in range(cycle))
    project, drum, voices, engine = kit(("SEQ",), pattern=pattern, bars=1)
    project.length = cycle
    voice = voices[0]
    live_voice = deepcopy(voice)
    live_voice.mode = "LIVE"
    for phrase in range(3):
        engine.generate_block(voice, motif_beat=phrase * 4)
        seq_hits = list(voice.outputs["rhythm"])
        live_hits = [bool(engine.live_event(live_voice, beat=(phrase * 16 + i) * .25)) for i in range(16)]
        expected = [i in (0, 8) or (i in (6, 10, 14) and (phrase * 16 + i) % cycle in source_hits) for i in range(16)]
        assert seq_hits == live_hits == expected


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_voice_density_zero_suppresses_forced_anchors_and_fill(mode):
    project, drum, voices, engine = kit((mode,))
    drum.parameters["kit_fill"] = 1
    for voice in voices:
        voice.parameters["fill_density"] = 0
        if mode == "SEQ":
            engine.generate_block(voice)
            assert not any(voice.outputs["rhythm"])
        else:
            assert all(engine.live_event(voice, beat=i * .25) is None for i in range(32))


def setup_transport(monkeypatch, project, engine):
    now, sent, errors = [100.0], [], []
    monkeypatch.setattr("auricle_transport.time.monotonic", lambda: now[0])
    app = SimpleNamespace(project=project, engine=engine, set_message=lambda _: None,
                          record_generated_event=lambda *_: None, log_midi_message=lambda *_: None)
    transport = Transport(app)
    transport.refresh_ports = lambda: None
    transport._log_error = lambda context, exc: errors.append((context, exc))
    transport.outputs["capture"] = SimpleNamespace(send=lambda msg: sent.append((round(now[0] - 100, 5), msg)))
    transport.start()
    def tick(seconds):
        now[0] = 100 + seconds
        transport.tick()
        assert not errors
    return transport, now, sent, tick


def test_mixed_modes_emit_the_same_shared_plan_and_fill(monkeypatch):
    project, drum, voices, engine = kit(bars=2)
    drum.parameters["kit_fill"] = 1
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    expected = []
    for slot in range(64):
        plan = engine.kit_plan(voices[0], slot * .25)
        expected.extend((round(slot * .125, 5), v.midi_note) for v in voices if plan.at(v.id, slot).allowed)
        tick(slot * .125)
    actual = [(t, m.note) for t, m in sent if m.type == "note_on"]
    assert sorted(actual) == sorted(expected)
    assert all(m.channel == 9 for t, m in sent if m.type == "note_on")


def test_mode_regeneration_bpm_edit_and_worker_stall_preserve_kit_phase(monkeypatch):
    project, drum, voices, engine = kit()
    drum.drum_voices = [voices[0]]
    voice = voices[0]
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    tick(.005)
    tick(.1)
    voice.mode = "LIVE"
    engine.reset_live()
    engine.regenerate(voice)
    tick(.11)
    tick(.75)  # slot 6, not a new downbeat or a catch-up burst
    voice.mode = "SEQ"
    tick(.76)
    now[0] = 100.8
    transport.set_tempo(60)
    tick(1.199)  # beat 1.999: kick at beat 2 has not arrived
    assert [(t, m.note) for t, m in sent if m.type == "note_on"] == [(.005, 36), (.75, 36)]
    tick(1.2)
    assert [(t, m.note) for t, m in sent if m.type == "note_on"][-1] == (1.2, 36)
    before = len([m for t, m in sent if m.type == "note_on"])
    tick(5.2)  # skip old slots; at most one onset for this voice
    assert len([m for t, m in sent if m.type == "note_on"]) <= before + 1
    transport.stop()
    assert transport.active_notes == []


def test_hat_choke_releases_only_this_kits_hat_notes_and_honors_channel_override(monkeypatch):
    project, drum, voices, engine = kit(("SEQ",), bars=1)
    kick, snare, closed, opened, clap, tom = voices
    opened.midi_channel, opened.midi_channel_override = 4, True
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    tick(1.75)  # open hat at slot 14
    assert any(m.type == "note_on" and m.note == opened.midi_note and m.channel == 3 for _, m in sent)
    marker = len(sent)
    tick(1.875)  # closed hat chokes open while the kick continues its gate
    messages = [m for _, m in sent[marker:]]
    off = next(i for i, m in enumerate(messages) if m.type == "note_off" and m.note == opened.midi_note)
    on = next(i for i, m in enumerate(messages) if m.type == "note_on" and m.note == closed.midi_note)
    assert off < on
    assert not any(m.type == "note_off" and m.note == kick.midi_note for m in messages)
    assert not any(m.type == "control_change" for _, m in sent)


@pytest.mark.parametrize("parent_mode", ["SEQ", "LIVE"])
def test_live_kit_relation_snapshot_uses_actual_slot_not_repeated_hit(monkeypatch, parent_mode):
    project, drum, voices, engine = kit(("LIVE",), pattern="0", bars=1)
    drum.mode = parent_mode
    drum.drum_voices = [voices[1]]  # snare backbeats 4,12
    bass = Block(2, "Bass", "BASS", "Pattern", "LIVE", midi_port="capture", midi_channel=2,
                 mutators=[], parameters={"pattern": "1", "live_min_beats": .25, "live_max_beats": .25,
                                          "groove_follow": 1, "groove_mode": "Replace", "fill_density": 1})
    project.blocks.insert(0, bass)  # source must run first despite project order
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    for slot in range(16):
        tick(slot * .125)
    assert [t for t, m in sent if m.type == "note_on" and m.channel == 1] == [.5, 1.5]
    assert not any(drum.outputs["rhythm"])


def test_motif_development_is_sampled_at_shared_grid_even_for_odd_motif_length(monkeypatch):
    project, drum, voices, engine = kit(("SEQ", "LIVE"), bars=1)
    motif = Motif("hat", "Odd hat", role="DRUM", notes=[0] * 7,
                  rhythm=[1, 0, 1, 0, 1, 1, 0], velocity=[.7] * 7, step_beats=2)
    project.motifs[motif.id] = asdict(motif)
    for voice in voices:
        voice.parameters.update(motif_id=motif.id, motif_development="rhythmic", motif_amount=.8)
    engine = MusicEngine(project)
    transport, now, sent, tick = setup_transport(monkeypatch, project, engine)
    for slot in range(48):
        tick(slot * .125)
        assert all(engine.motif_step_beats(v) == .25 for v in voices)
        for voice in voices:
            variant = engine.motif_development.current(voice.id)
            assert variant.cycle == slot // 7
    assert any(len(items) > 1 for items in engine.motif_development.history.values())
    assert project.motifs[motif.id] == asdict(motif)


def test_live_technique_dynamics_still_affect_coordinated_voices():
    project, drum, voices, engine = kit(("LIVE",))
    voice = voices[0]
    quiet = engine.live_event(voice, beat=0)["velocity"]
    engine.performance.active[voice.id] = SimpleNamespace(current_values={"velocity_base": .9, "gate": .1})
    loud = engine.live_event(voice, beat=0)
    assert loud["velocity"] > quiet
    assert loud["duration"] < .2


def test_configuration_and_named_roles_round_trip(tmp_path):
    project, drum, voices, engine = kit()
    voices[0].name, voices[0].midi_note = "External low drum", 75
    voices[-1].parameters["kit_role"] = "free"
    drum.parameters.update(kit_style="broken", kit_fill=.75)
    path = tmp_path / "coordinated.json"
    save_project(project, str(path))
    restored = load_project(str(path))
    assert restored.blocks[0].parameters["kit_style"] == "broken"
    assert voice_role(restored.blocks[0].drum_voices[0]) == "kick"
    assert voice_role(restored.blocks[0].drum_voices[-1]) == "free"
    new_engine = MusicEngine(restored)
    engine.generate(); new_engine.generate()
    assert [v.outputs for v in restored.blocks[0].drum_voices] == [v.outputs for v in voices]


def test_pinned_configuration_role_switch_and_knob_edits_survive_ui_refresh(inspector):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = inspector
    panel = win.drum_kit_layout.itemAt(0).widget()
    panel.findChild(gui.QCheckBox, "kitCoordinated").setChecked(True)
    QTest.qWait(65)
    panel = win.drum_kit_layout.itemAt(0).widget()
    assert len(panel.plan_lanes) == len(drum.drum_voices)
    panel.phrase_length.setValue(3)
    panel.style_selector.setCurrentIndex(panel.style_selector.findData("broken"))
    panel.findChild(gui.ParamKnob, "kit_fill").setValue(1)
    QTest.qWait(65)
    assert win.drum_kit_layout.itemAt(0).widget() is panel
    assert drum.parameters["kit_phrase_bars"] == 3
    assert len(drum.drum_voices[0].outputs["rhythm"]) == 48
    first = drum.drum_voices[0]
    role = panel.findChild(gui.QComboBox, f"kitRole_{first.id}")
    role.setCurrentIndex(role.findData("free"))
    QTest.qWait(65)
    panel = win.drum_kit_layout.itemAt(0).widget()
    assert first.id not in panel.plan_lanes
    win._select_drum_voice(first.id)
    QTest.qWait(65)
    assert win.drum_kit_layout.count() == 1
    assert not errors
