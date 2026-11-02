"""Real-time feedback must never become a musical edit or lose Composition."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from copy import deepcopy
from types import SimpleNamespace
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from auricle_core import Block, Project, MusicEngine, Relation, Transport
from composition_planner import default_composition, make_section
from parameter_sources import SourceSnapshot, feedback_value
from parameter_sources_ui import ParameterSourceLabel
from project_history import document_state
from test_kit_preview_lifecycle import inspector


def setup(mode="SEQ"):
    blocks = [Block(i, name, "MELODY", "Pattern", mode, parameters={
        "pattern": "1,1,1,1", "velocity_base": velocity, "velocity_range": 0.,
        "velocity_random": 0., "velocity_accent": 0., "fill_density": 1., "gate": .8,
    }, mutators=[]) for i, name, velocity in ((1, "Source", .2), (2, "Lead", .8))]
    engine = MusicEngine(Project(blocks=blocks, composition=default_composition()))
    engine.generate()
    return engine, *blocks


def read(engine, block_id, key):
    snapshot = SourceSnapshot(engine)
    return feedback_value(snapshot, block_id, key, snapshot.marks(block_id, key))


def controls(gui, win, block_id, key):
    return [c for c in win.findChildren(gui.Knob) if getattr(c, "_auricle_parameter", None) == (block_id, key)]


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_composition_effective_values_keep_authored_values_and_follow_sections(mode):
    engine, source, lead = setup(mode)
    form = engine.project.composition
    form["enabled"] = True
    section = form["sections"][0]
    section["macros"].update(density=.3, energy=.5, variation=.5)
    section["blocks"][str(lead.id)] = {"density": .5, "velocity": .5, "register_center": 7}
    before = document_state(engine.project, engine)
    assert read(engine, lead.id, "fill_density").effective == pytest.approx(.35)
    assert read(engine, lead.id, "velocity_base").effective == pytest.approx(.4)
    center = read(engine, lead.id, "role_center")
    assert center.effective == center.parameter + 7
    assert read(engine, lead.id, "transpose").effective == 0
    assert read(engine, None, "density").effective == .3
    assert document_state(engine.project, engine) == before
    section["blocks"][str(lead.id)]["enabled"] = False
    assert read(engine, lead.id, "fill_density").effective == 0
    assert read(engine, lead.id, "velocity_base").effective == 0
    form["enabled"] = False
    assert read(engine, lead.id, "fill_density").effective == 1
    assert read(engine, lead.id, "velocity_base").effective == .8


@pytest.mark.parametrize("mode", ["SEQ", "LIVE"])
def test_relation_feedback_uses_real_processed_streams(mode):
    engine, source, lead = setup(mode)
    engine.project.relations = [Relation(source.id, "velocity", lead.id, "velocity", "Copy", 1.)]
    if mode == "LIVE":
        engine.live_event(source)
        engine.live_event(lead)
    else:
        engine.generate()
    state = read(engine, lead.id, "velocity_base")
    assert state.manual == state.parameter == .8
    expected = .8 * lead.outputs["velocity"][0] / engine._base_outputs[lead.id]["velocity"][0]
    assert state.effective == pytest.approx(expected)
    assert state.effective < state.manual
    assert state.mode == "Output equivalent"
    engine.project.relations.clear()
    engine.generate()
    assert read(engine, lead.id, "velocity_base").effective == .8


def test_feedback_observation_does_not_change_rng_clock_outputs_or_project(monkeypatch):
    engine, source, lead = setup()
    engine.project.composition["enabled"] = True
    engine.project.composition["sections"][0]["blocks"][str(lead.id)] = {"variation": .7}
    engine.project.relations = [Relation(source.id, "duration", lead.id, "duration", "Mix", .5)]
    engine.generate()
    before = deepcopy((engine.project, engine.clock.__dict__, engine.parameter_influence.entries,
                       engine.live_state, engine.harmonic_runtime.voicings))
    def fail(*args, **kwargs):
        pytest.fail("Display observation invoked a write or musical regeneration")
    for name in ("generate", "regenerate", "set_parameter", "live_event", "harmonize_event"):
        monkeypatch.setattr(engine, name, fail)
    for _ in range(10):
        for key in ("fill_density", "velocity_base", "gate", "transpose"):
            read(engine, lead.id, key)
    after = (engine.project, engine.clock.__dict__, engine.parameter_influence.entries,
             engine.live_state, engine.harmonic_runtime.voicings)
    assert before == after


def test_play_from_neutral_first_section_keeps_composition_markers(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    import auricle_transport
    monkeypatch.setattr(auricle_transport, "get_midi_output_names", lambda: ([], None))
    sections = [make_section("Intro", neutral=True, bars=1), make_section("Build", bars=1)]
    win.project.composition.update(enabled=True, sections=sections)
    win.composition_panel.sync_from_project()
    win.engine.clock.position_beats = 4
    win._update_parameter_sources(force=True)
    label = win.global_macro_bar.labels[2]
    assert label.source_marks[0].active
    win.composition_panel.play_from.setCurrentIndex(win.composition_panel.play_from.findData("start"))
    win.composition_panel.play_button.click()
    try:
        win._update_parameter_sources(force=True)
        assert win.project.composition["enabled"]
        assert win.composition_panel.enabled.isChecked()
        assert win.engine.clock.position_beats == 0
        assert label.source_marks[0].source == "Composition"
        assert not label.source_marks[0].active
        assert "follows Global" in label.toolTip()
    finally:
        win.transport.stop()
    assert not errors


def test_perform_rotates_needle_and_readout_without_changed_signal_or_undo(inspector):
    gui, win, drum, melody, errors = inspector
    win.selected_block_id = melody.id
    win._refresh_inspector()
    knob = controls(gui, win, melody.id, "gate")[0]
    manual = knob.value()
    history = win.history_controller.snapshot()
    changes = []
    knob.changed.connect(changes.append)
    win.engine.performance.start(melody, "staccato", beats=8)
    win.engine.performance.tick(True, beat_delta=1)
    win._update_parameter_sources(force=True)
    first = knob.displayValue()
    assert first == pytest.approx(melody.parameters["gate"])
    win.engine.performance.tick(True, beat_delta=2)
    win._update_parameter_sources(force=True)
    assert knob.displayValue() != first
    assert knob.value_label.text() == knob._formatted()
    assert knob.value() == manual
    assert not changes
    assert win.history_controller.snapshot() == history
    win.engine.performance.stop(melody.id)
    win._update_parameter_sources(force=True)
    assert knob.displayValue() == knob.value() == manual
    assert not errors


def test_composition_moves_knob_and_header_silently_then_restores_manual(inspector):
    gui, win, drum, melody, errors = inspector
    win.selected_block_id = melody.id
    win._refresh_inspector()
    knob = controls(gui, win, melody.id, "fill_density")[0]
    form = win.project.composition
    form["enabled"] = True
    form["sections"][0]["macros"]["density"] = .3
    form["sections"][0]["blocks"][str(melody.id)] = {"density": .5}
    before = win.history_controller.snapshot()
    changes = []
    knob.changed.connect(changes.append)
    win.global_macro_bar.sliders[2].valueChanged.connect(changes.append)
    win._update_parameter_sources(force=True)
    assert knob.displayValue() == pytest.approx(knob.value() * .35)
    assert win.global_macro_bar.sliders[2].value() == 30
    assert win.project.macros[2]["value"] == .5
    assert win.history_controller.snapshot() == before
    assert not changes
    form["enabled"] = False
    win._update_parameter_sources(force=True)
    assert knob.displayValue() == knob.value()
    assert win.global_macro_bar.sliders[2].value() == 50
    assert not errors


def test_runtime_feedback_respects_mouse_drag_and_manual_edit_semantics():
    app = QApplication.instance() or QApplication([])
    from auricle_gui import ParamKnob
    knob = ParamKnob(.7)
    changes = []
    knob.changed.connect(changes.append)
    knob.set_runtime_value(.7, .2)
    assert knob.value() == .7 and knob.displayValue() == .2
    assert not changes
    knob.show()
    QTest.mousePress(knob, Qt.LeftButton, pos=QPoint(25, 25))
    knob.set_runtime_value(.1, .9)
    assert knob.value() == .7 and knob.displayValue() == .2
    QTest.mouseRelease(knob, Qt.LeftButton, pos=QPoint(25, 25))
    knob.setValue(.8)
    assert changes == [.8]
    assert knob.displayValue() == knob.value() == .8
    knob.close()


def test_live_worker_keeps_composition_and_refreshes_knobs_without_rebuild(inspector, monkeypatch):
    gui, win, drum, melody, errors = inspector
    import auricle_transport
    monkeypatch.setattr(auricle_transport, "get_midi_output_names", lambda: ([], None))
    win.selected_block_id = melody.id
    win._refresh_inspector()
    win.project.composition.update(enabled=True, sections=[make_section("Build", [melody], bars=4)])
    win.composition_panel.sync_from_project()
    page = win.inspector_page
    win.transport_worker.start()
    win.performance_timer.start()
    win.composition_panel.play_button.click()
    try:
        QTest.qWait(300)
        win._update_parameter_sources(force=True)
        # A nonblocking read may coincide with a worker generation tick.
        # Wait for a delivered UI frame, rather than requiring a lucky lock slot.
        for _ in range(20):
            candidate = controls(gui, win, melody.id, "fill_density")[0]
            if candidate.displayValue() < candidate.value():
                break
            QTest.qWait(20)
            win._update_parameter_sources(force=True)
        assert win.transport.running and win.engine.clock.position_beats > 0
        assert win.composition_panel.enabled.isChecked()
        assert win.inspector_page is page
        knob = controls(gui, win, melody.id, "fill_density")[0]
        assert knob.displayValue() < knob.value()
        assert win.global_macro_bar.labels[2].source_marks[0].source == "Composition"
        assert win.global_macro_bar.sliders[2].value() == 76
        assert win.transport_worker.error_count == 0
    finally:
        win.performance_timer.stop()
        win.transport_worker.stop()
        win.transport.stop()
    assert not errors


def test_dispatched_section_feedback_is_not_applied_twice_and_expires():
    engine, source, lead = setup()
    engine.project.composition["enabled"] = True
    engine.project.composition["sections"][0]["blocks"][str(lead.id)] = {"velocity": .5, "register_center": 7}
    app = SimpleNamespace(engine=engine, project=engine.project,
                          record_generated_event=lambda *args: None)
    transport = Transport(app)
    event = {"pitch": lead.outputs["pitch"][0], "velocity": .8, "duration": .8}
    delivered = transport._dispatch_event(lead, event, None, .125, 0.)
    assert delivered["velocity"] == pytest.approx(.4)
    assert read(engine, lead.id, "velocity_base").effective == pytest.approx(.4)
    assert read(engine, lead.id, "role_center").effective == 7
    assert read(engine, lead.id, "transpose").effective == 0
    engine.clock.position_beats = 1.
    assert read(engine, lead.id, "velocity_base").effective == pytest.approx(.4)
    engine.project.composition["enabled"] = False
    assert read(engine, lead.id, "velocity_base").effective == .8
    assert read(engine, lead.id, "transpose").effective == 0


def test_harmonic_plan_feedback_marks_center_without_moving_manual_transpose():
    from harmonic_plan import preset
    engine, source, lead = setup()
    engine.project.harmonic_plan = preset()
    lead.parameters["harmonic_strength"] = 1.
    lead.outputs["pitch"] = [2.]
    raw = {"pitch": 2., "velocity": .8, "duration": .8}
    shaped = engine.harmonize_event(lead, raw, 0.)
    transport = Transport(SimpleNamespace(engine=engine, project=engine.project,
                                          record_generated_event=lambda *args: None))
    delivered = transport._dispatch_event(lead, shaped, None, .125, 0.)
    assert delivered["pitch"] != raw["pitch"]
    assert read(engine, lead.id, "transpose").effective == 0
    assert read(engine, lead.id, "role_center").effective == 0
    assert SourceSnapshot(engine).marks(lead.id, "role_center")[0].source == "Perform"


def test_dialogue_activity_feedback_follows_the_turn_instead_of_random_notes():
    engine, source, lead = setup()
    engine.project.relations = [Relation(source.id, "pitch", lead.id, "pitch", "Dialogue", 1.)]
    assert read(engine, lead.id, "fill_density").effective == 0
    assert read(engine, source.id, "fill_density").effective == 1
    engine.clock.position_beats = 4.
    assert read(engine, lead.id, "fill_density").effective == 1
    assert read(engine, source.id, "fill_density").effective == 0
