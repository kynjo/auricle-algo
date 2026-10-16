"""v104 regressions retained for the v105 stability release."""
from pathlib import Path

from auricle_core import Block, MusicEngine, Project, apply_role_defaults
from music_director import PerformanceState


ROOT = Path(__file__).resolve().parents[1]


def block(block_id, name, role, algorithm, mode="SEQ", **parameters):
    item = Block(block_id, name, role, algorithm, mode, parameters=parameters)
    apply_role_defaults(item)
    return item


def test_director_dataclass_updates_musical_context():
    engine = MusicEngine(Project())
    engine.director.energy = 0.93
    engine.director._last_state = PerformanceState(.93, .87, .7, 0, 1, 1, .2, 0)
    engine.update_musical_context()
    assert engine.musical_context.energy == .93
    assert engine.musical_context.tension != .2


def test_bass_selected_drum_source_controls_groove_shaping():
    durations = []
    for pulses in (1, 8):
        project = Project(length=16)
        source = block(1, "D1", "DRUM", "Pattern", pattern="1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
        unrelated = block(2, "D2", "DRUM", "Euclidean", pulses=pulses)
        bass = block(3, "B", "BASS", "Pattern", pattern="1", groove_follow=1.0,
                     groove_accent=0.0, relation_drum_source=1)
        project.blocks = [source, unrelated, bass]
        MusicEngine(project).generate()
        durations.append(bass.outputs["duration"][0])
    assert durations[0] == durations[1]


def test_groove_resets_when_no_drums_remain():
    project = Project(length=16)
    drum = block(1, "D", "DRUM", "Euclidean", pulses=8)
    bass = block(2, "B", "BASS", "Pattern", pattern="1")
    project.blocks = [drum, bass]
    engine = MusicEngine(project)
    engine.generate()
    assert engine.musical_context.groove > 0
    project.blocks = [bass]
    engine.update_musical_context()
    assert engine.musical_context.groove == 0.0
    assert engine.musical_context.values["groove_sources"] == []


def test_regenerating_drum_rebuilds_dependents_like_full_generate():
    project = Project(length=16)
    drum = block(1, "D", "DRUM", "Euclidean", pulses=1)
    bass = block(2, "B", "BASS", "Pattern", pattern="1", groove_follow=1.0, groove_accent=0.0)
    project.blocks = [drum, bass]
    engine = MusicEngine(project)
    engine.generate()
    drum.parameters["pulses"] = 16
    engine.regenerate(drum)
    regenerated = list(bass.outputs["duration"])
    engine.generate()
    assert regenerated == bass.outputs["duration"]


def test_live_rest_stays_zero_after_role_relations():
    project = Project(length=16)
    drum = block(1, "D", "DRUM", "Pattern", pattern="1")
    bass = block(2, "B", "BASS", "Pattern", "LIVE", pattern="0", groove_follow=1.0, groove_accent=0.0)
    project.blocks = [drum, bass]
    engine = MusicEngine(project)
    engine.generate()
    engine.reset_live()
    assert engine.live_event(bass) is None
    assert bass.outputs["rhythm"] == [0.0]
    assert bass.outputs["velocity"] == [0.0]


def test_chord_anchor_does_not_use_future_chord_step():
    project = Project(root_note=60, scale="Major")
    chord = block(1, "C", "CHORD", "Pattern", scale_root=60)
    melody = block(2, "M", "MELODY", "Pattern", scale_root=60, harmony_anchor=1.0)
    project.blocks = [chord, melody]
    engine = MusicEngine(project)
    chord.outputs = {"rhythm": [0.0, 1.0], "pitch": [0.0, 2.0], "velocity": [0.0, .8],
                     "duration": [0.0, 1.0], "density": [0.0, 1.0], "accent": [0.0, 0.0]}
    melody.outputs = {"rhythm": [1.0, 1.0], "pitch": [7.0, 7.0], "velocity": [.8, .8],
                      "duration": [1.0, 1.0], "density": [1.0, 1.0], "accent": [0.0, 0.0]}
    engine._apply_chord_to_melody(chord, melody)
    assert melody.outputs["pitch"][0] == 7.0


def test_gui_transport_diagnostics_are_marshaled_to_qt_thread():
    source = (ROOT / "auricle_gui.py").read_text(encoding="utf-8")
    assert "_midi_message_signal = Signal" in source
    assert "self._midi_message_signal.emit" in source
    assert "def _handle_midi_message" in source
    assert "_status_message_signal = Signal" in source


def test_editing_actions_mark_project_dirty():
    source = (ROOT / "auricle_gui.py").read_text(encoding="utf-8")
    randomize = source[source.index("    def apply_randomize"):source.index("class ModeSwitch")]
    assert "self.host._mark_dirty()" in randomize
    add_mutator = source[source.index("    def add_mutator"):source.rindex("    def add_relation")]
    assert "self._mark_dirty()" in add_mutator


def test_wheel_controls_work_when_hovered():
    source = (ROOT / "auricle_gui.py").read_text(encoding="utf-8")
    knob = source[source.index("    def wheelEvent(self, event):"):source.index("    def focusInEvent", source.index("    def wheelEvent(self, event):"))]
    stepper_start = source.index("class ValueStepper")
    stepper = source[source.index("    def wheelEvent(self, event):", stepper_start):source.index("    def keyPressEvent", stepper_start)]
    assert "if not self.hasFocus()" not in knob
    assert "if not self.hasFocus()" not in stepper
