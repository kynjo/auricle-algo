"""Exercise the editable rows, model ownership and deferred Qt lifecycle."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from auricle_core import Block, Project, ensure_drum_voices
from auricle_persistence import load_project


@pytest.fixture(scope="module")
def window():
    from PySide6.QtWidgets import QApplication
    import auricle_gui as gui

    app = QApplication.instance() or QApplication([])
    patch = pytest.MonkeyPatch()
    patch.setattr(gui, "get_midi_output_names", lambda: ([], None))
    patch.setattr(gui.QDialog, "exec", lambda self: pytest.fail("Inline addition must not open a dialog"))
    win = gui.MainWindow()
    win.performance_timer.stop()
    win.transport_worker.stop()
    yield gui, app, win
    win.hide()
    win.deleteLater()
    app.processEvents()
    patch.undo()


def drain(app):
    for _ in range(6):
        app.processEvents()


@pytest.fixture
def editor(window):
    gui, app, win = window
    blocks = [Block(i, role, role, "Pattern", parameters={"pattern": "1,0,1,0"}, mutators=[])
              for i, role in enumerate(("DRUM", "BASS", "MELODY", "PAD", "CHORD"), 1)]
    ensure_drum_voices(blocks[0])
    win.selected_drum_voice_id = None
    win._install_project(Project(blocks=blocks), None, "Inline editor test")
    drain(app)
    return gui, app, win, win.relation_graph


@pytest.mark.parametrize("role", ["DRUM", "BASS", "MELODY", "PAD", "CHORD"])
def test_mutator_add_type_target_and_amount_in_place(editor, role):
    gui, app, win, panel = editor
    block = next(block for block in win.project.blocks if block.block_type == role)
    win.selected_block_id = block.id
    win.selected_drum_voice_id = None
    win._inspector_state[(block.id, "MOTION")] = True
    win._refresh_inspector()
    add = next(button for button in win.inspector_page.findChildren(gui.QPushButton) if button.accessibleName() == "Add mutator")
    add.click(); drain(app)
    assert len(block.mutators) == 1
    row = win.inspector_page.findChild(gui.MutatorInlineControls)
    assert row.mutator is block.mutators[0]
    row.kind.setCurrentText("Humanize")
    row.target.setCurrentText("timing")
    row.amount.setValue(.81)
    assert (row.mutator.name, row.mutator.target, row.mutator.amount) == ("Humanize", "timing", .81)
    assert win.inspector_page.findChild(gui.MutatorInlineControls) is row
    row.remove.click(); drain(app)
    assert not block.mutators
    assert not win.inspector_page.findChildren(gui.MutatorInlineControls)


def test_mutator_and_process_add_to_the_selected_drum_voice(editor, tmp_path):
    gui, app, win, panel = editor
    drum = win.project.blocks[0]
    voice = drum.drum_voices[0]
    win.selected_block_id = drum.id
    win.selected_drum_voice_id = voice.id
    win.add_mutator()
    win.add_process()
    drain(app)
    assert not drum.mutators and not drum.processes
    assert len(voice.mutators) == len(voice.processes) == 1
    win._set_process_type(voice, 0, "Delay")
    drain(app)
    assert voice.processes[0].type == "Delay"
    row = win.inspector_page.findChild(gui.MutatorInlineControls)
    row.kind.setCurrentText("Shuffle")
    path = tmp_path / "voice_edits.json"
    assert win._write_project(str(path))
    loaded_voice = load_project(str(path)).blocks[0].drum_voices[0]
    assert loaded_voice.mutators[0].name == "Shuffle"
    assert loaded_voice.processes[0].type == "Delay"
    win._install_project(load_project(str(path)), str(path), "Restored voice")
    drain(app)
    assert win.inspector_page.findChild(gui.MutatorInlineControls).kind.currentText() == "Shuffle"


def test_deleted_and_retyped_default_mutators_stay_that_way_after_loading(editor, tmp_path):
    gui, app, win, panel = editor
    block = Block(8, "Default chain", "MELODY", "Pattern")
    assert [m.name for m in block.mutators] == ["Transpose", "Scale", "Octave"]
    win._install_project(Project(blocks=[block]), None, "Defaults")
    rows = win.inspector_page.findChildren(gui.MutatorInlineControls)
    rows[0].kind.setCurrentText("Reverse")
    rows[1].remove.click()
    rows[2].remove.click()
    drain(app)
    path = tmp_path / "chain.json"
    assert win._write_project(str(path))
    restored = load_project(str(path))
    assert [m.name for m in restored.blocks[0].mutators] == ["Reverse"]
    win._install_project(restored, str(path), "Restored chain")
    win.inspector_page.findChild(gui.MutatorInlineControls).remove.click()
    drain(app)
    assert win._write_project(str(path))
    assert load_project(str(path)).blocks[0].mutators == []


