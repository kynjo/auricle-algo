"""Real Qt controls for capture, cycle settings, holds and history recall."""
from test_kit_preview_lifecycle import inspector
from test_motif_inspector import prepare


def test_capture_and_save_variant_create_selectable_themes(inspector):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = prepare(inspector)
    page = win.inspector_scroll.widget()
    page.findChild(gui.QPushButton, "motifCapture").click()
    QTest.qWait(100)
    first_id = melody.parameters["motif_id"]
    assert first_id in win.project.motifs
    page = win.inspector_scroll.widget()
    assert page.findChild(gui.QComboBox, "motifChoice").currentData() == first_id
    assert page.findChild(gui.QPushButton, "motifSaveVariant").isEnabled()
    page.findChild(gui.QPushButton, "motifSaveVariant").click()
    QTest.qWait(100)
    assert melody.parameters["motif_id"] != first_id
    assert melody.parameters["motif_id"] in win.project.motifs
    assert not errors


def test_edits_hold_and_recall_keep_current_inspector_and_announce_boundary(inspector):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = prepare(inspector)
    win._set_motif_binding(melody, "mel")
    QTest.qWait(100)
    page = win.inspector_scroll.widget()
    development = page.findChild(gui.QComboBox, "motifDevelopment")
    development.setCurrentIndex(development.findData("combined"))
    page.findChild(gui.ValueStepper, "motifAmount").setValue(.8)
    win.transport.running = True
    win.engine.clock.start(100, 120)
    win.engine.clock.position_beats = 1.5
    variant = win.engine.motif_variant(melody)
    win._update_motif_status()
    page.findChild(gui.ValueStepper, "motifEvery").setValue(2)
    assert "changes next cycle" in page.findChild(gui.QLabel, "motifPosition").text()
    assert win.engine.motif_variant(melody) is variant
    page.findChild(gui.QCheckBox, "motifHold").setChecked(True)
    assert melody.parameters["motif_hold"]["source_id"] == "mel"
    win.engine.clock.position_beats = 3
    assert win.engine.motif_variant(melody).token == variant.token
    win._update_motif_status()
    assert win.inspector_scroll.widget() is page
    history = page.findChild(gui.QComboBox, "motifHistory")
    assert history.count() >= 2
    history.setCurrentIndex(history.count() - 1)
    page.findChild(gui.QPushButton, "motifRecall").click()
    assert page.findChild(gui.QCheckBox, "motifHold").isChecked()
    win.engine.clock.position_beats = 4.5
    recalled = win.engine.motif_variant(melody)
    assert recalled.motif.notes == [0, 4, 7]
    page.findChild(gui.QCheckBox, "motifHold").setChecked(False)
    assert "motif_hold" not in melody.parameters
    assert not errors
    win.transport.running = False
    win.engine.clock.running = False


def test_drum_voice_capture_does_not_change_siblings_or_pinned_selection(inspector):
    from PySide6.QtTest import QTest
    gui, win, drum, melody, errors = prepare(inspector)
    win.selected_block_id, win.selected_drum_voice_id = drum.id, drum.drum_voices[0].id
    win._refresh_inspector()
    voice = drum.drum_voices[0]
    win.inspector_scroll.widget().findChild(gui.QPushButton, "motifCapture").click()
    QTest.qWait(100)
    assert win._selected_inspector_entity() is voice
    assert win.drum_kit_layout.count() == 1
    assert win.engine.active_motif(voice).role == "DRUM"
    assert "motif_id" not in drum.parameters
    assert "motif_id" not in drum.drum_voices[1].parameters
    assert not errors
