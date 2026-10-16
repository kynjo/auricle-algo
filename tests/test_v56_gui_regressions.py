from pathlib import Path

GUI_SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"


def test_mute_switch_removed_from_gui():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    assert "class MuteSwitch" not in source
    assert "MuteSwitch(" not in source
    assert "mute_changed = Signal(int, bool)" in source


def test_knobs_are_compact_and_mouse_grabbed():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    assert "self.setFixedSize(54, 74)" in source
    assert "self.grabMouse()" in source
    assert "self.releaseMouse()" in source
    assert "cell.setFixedWidth(82)" in source


def test_pattern_and_timing_are_left_aligned():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    start = source.index('pattern = InspectorGroup("PATTERN"')
    end = source.index("        # MUSICAL", start)
    block = source[start:end]
    assert "pf.setAlignment(Qt.AlignLeft | Qt.AlignTop)" in block
    assert "tf.setAlignment(Qt.AlignLeft | Qt.AlignTop)" in block


def test_inspector_scroll_is_preserved_after_rebuild():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    start = source.index("    def _refresh_inspector(self, restore_anchor=None):")
    end = source.index("    def _remember_group", start)
    block = source[start:end]
    assert "scroll_value = self.inspector_scroll.verticalScrollBar().value()" in block
    assert "bar.setValue" in block


def test_parameter_regeneration_is_deferred():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    start = source.index("    def _set_param(self, b, key, value):")
    end = source.index("    def _set_mutator", start)
    block = source[start:end]
    assert "QTimer.singleShot(0" in block
    assert "def _flush_param_regen" in block


def test_mutators_are_rendered_as_one_vertical_column():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    start = source.index('        for idx,m in enumerate(b.mutators):')
    end = source.index('        add=QPushButton("+ Add mutator")', start)
    block = source[start:end]
    assert "ml.addWidget(wrapper)" in block
    assert "col=idx%3" not in block
    assert "row=idx//3" not in block


def test_process_numeric_controls_use_compact_knob_grid():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    start = source.index("class ProcessInlineControls(QWidget):")
    end = source.index("class MainWindow", start) if "class MainWindow" in source[start:] else source.index("class", start + 10)
    block = source[start:end]
    assert "grid.setHorizontalSpacing(4)" in block
    assert "grid.setVerticalSpacing(4)" in block
    assert "cell.setFixedWidth(82)" in block
    assert "self.grid.addWidget(cell, 0, self.index" in block


def test_inspector_scroll_restore_retries_after_layout_settles():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    start = source.index("    def _refresh_inspector(self, restore_anchor=None):")
    end = source.index("    def _remember_group", start)
    block = source[start:end]
    assert "QTimer.singleShot(0, restore_inspector_scroll)" in block
    assert "QTimer.singleShot(50, restore_inspector_scroll)" in block
    assert "ensureWidgetVisible(target" in block
