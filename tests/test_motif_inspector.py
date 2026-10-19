"""Select motifs without disturbing the pinned kit or replacing live widgets."""
from motif_engine import Motif
from test_kit_preview_lifecycle import inspector


def prepare(inspector):
    gui, win, drum, melody, errors = inspector
    win.engine.director.motifs.register(Motif("mel", "Melodic theme", notes=[0, 4, 7], step_beats=.5))
    win.engine.director.motifs.register(Motif("kick", "Kick motif", role="DRUM", rhythm=[1, 0, 0, 1]))
    win.selected_block_id, win.selected_drum_voice_id = melody.id, None
    win._refresh_inspector()
    return gui, win, drum, melody, errors


def test_select_step_and_disable_motif_in_current_inspector(inspector):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = prepare(inspector)
    choice = win.inspector_scroll.widget().findChild(gui.QComboBox, "motifChoice")
    assert choice.findData("mel") >= 0
    assert choice.findData("kick") < 0
    choice.setCurrentIndex(choice.findData("mel"))
    QTest.qWait(100)
    assert melody.parameters["motif_id"] == "mel"
    page = win.inspector_scroll.widget()
    step = page.findChild(gui.ValueStepper, "motifStepBeats")
    assert step.isEnabled() and step.value() == .5
    step.setValue(.75)
    assert win.engine.motif_step_beats(melody) == .75
    assert win.inspector_scroll.widget() is page
    choice = page.findChild(gui.QComboBox, "motifChoice")
    choice.setCurrentIndex(choice.findData(""))
    QTest.qWait(100)
    assert win.engine.active_motif(melody) is None
    assert not win.inspector_scroll.widget().findChild(gui.ValueStepper, "motifStepBeats").isEnabled()
    assert not errors


def test_phrase_auto_updates_without_inspector_rebuild(inspector):
    gui, win, drum, melody, errors = prepare(inspector)
    page = win.inspector_scroll.widget()
    step = page.findChild(gui.ValueStepper, "motifStepBeats")
    assert not step.isEnabled()
    win.engine.performance.start_phrase(win.project, "opening_bloom", [melody.id])
    win.engine.clock.position_beats = 1
    win._update_motif_status()
    assert win.inspector_scroll.widget() is page
    assert step.isEnabled() and step.value() == .5
    assert "Step 3/3" in page.findChild(gui.QLabel, "motifPosition").text()
    assert "motif_step_beats" not in melody.parameters  # display refresh isn't an edit
    win.engine.performance.stop_phrase("opening_bloom")
    win._update_motif_status()
    assert not step.isEnabled()
    assert not errors


def test_drum_voice_binding_keeps_kit_pinned(inspector):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = prepare(inspector)
    win.selected_block_id, win.selected_drum_voice_id = drum.id, None
    win._refresh_inspector()
    voice = drum.drum_voices[0]
    win._select_drum_voice(voice.id)
    QTest.qWait(100)
    page = win.inspector_scroll.widget()
    choice = page.findChild(gui.QComboBox, "motifChoice")
    assert choice.findData("mel") < 0
    choice.setCurrentIndex(choice.findData("kick"))
    QTest.qWait(100)
    assert win._selected_inspector_entity() is voice
    assert win.drum_kit_layout.count() == 1
    assert voice.parameters["motif_id"] == "kick"
    assert "motif_id" not in drum.parameters
    assert "motif_id" not in drum.drum_voices[1].parameters
    assert not errors
