from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI_SOURCE = ROOT / "auricle_gui.py"


def _source():
    return GUI_SOURCE.read_text(encoding="utf-8")


def test_inspector_swap_does_not_touch_stale_qt_wrapper():
    source = _source()
    block = source[source.index("def _refresh_inspector"):source.index("def _remember_group")]
    assert "self.inspector_scroll.setWidget(page)" in block
    assert "old_page.setParent(None)" not in block
    assert "old_page.deleteLater()" not in block
    assert "stale wrapper" in block


def test_dpg_frontend_is_removed_from_repository():
    assert not (ROOT / "gui_dpg.py").exists()
    assert not (ROOT / "run_dpg.py").exists()
    assert not (ROOT / "run_dpg.sh").exists()
    assert not (ROOT / "run_dpg_windows.bat").exists()
    assert not (ROOT / "requirements-dpg.txt").exists()


def test_inspector_scroll_restore_does_not_capture_replaced_page():
    source = _source()
    block = source[source.index("def _refresh_inspector"):source.index("def _remember_group")]
    assert "self._inspector_generation" in block
    assert "generation != getattr(self, \"_inspector_generation\", -1)" in block
    assert "current_page = scroll.widget()" in block
    assert "target.mapTo(current_page, QPoint(0, 0)).y()" in block
    assert "target.mapTo(page, QPoint(0, 0)).y()" not in block


def test_qpoint_is_imported_for_scroll_restore():
    source = _source()
    assert "from PySide6.QtCore import" in source
    assert "QPoint," in source.split("from PySide6.QtCore import", 1)[1].split("\n", 1)[0]


def test_process_type_change_is_deferred_outside_combobox_callback():
    source = _source()
    start = source.index("def _set_process_type")
    end = source.index("def _set_process_target", start)
    block = source[start:end]
    assert "QTimer.singleShot(0, apply_change)" in block
    assert "self._refresh_inspector(\"PROCESS\")" in block
    # The Inspector must only be rebuilt from the deferred callback, not from
    # the QComboBox currentTextChanged stack itself.
    callback = block[block.index("def apply_change"):]
    assert "self._refresh_inspector(\"PROCESS\")" in callback
    outer = block[:block.index("def apply_change")]
    assert "self._refresh_inspector(\"PROCESS\")" not in outer


def test_algorithm_change_is_deferred_outside_combobox_callback():
    source = _source()
    start = source.index("def _set_algorithm")
    end = source.index("def _set_mode", start)
    block = source[start:end]
    assert "QTimer.singleShot(0, apply_change)" in block
    assert 'self._refresh_inspector("SOURCE")' in block
    assert "_algorithm_change_pending" in block
    callback = block[block.index("def apply_change"):]
    assert 'self._refresh_inspector("SOURCE")' in callback
    outer = block[:block.index("def apply_change")]
    assert 'self._refresh_inspector("SOURCE")' not in outer


def test_algorithm_change_coalesces_rapid_combo_changes():
    source = _source()
    start = source.index("def _set_algorithm")
    end = source.index("def _set_mode", start)
    block = source[start:end]
    assert "token = pending.get(b.id, 0) + 1" in block
    assert "current != change_token" in block
    assert "pending.pop(block.id, None)" in block
