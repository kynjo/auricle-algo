from pathlib import Path

GUI_SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"

def test_inspector_uses_one_persistent_page():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    start = source.index("    def _new_inspector_page(self):")
    end = source.index("    def _refresh_inspector(self, restore_anchor=None):", start)
    block = source[start:end]
    assert "page = QWidget()" in block
    assert "self.inspector_scroll.setWidget(page)" not in block
    assert "self.inspector_stack" not in block
    assert "old.deleteLater()" not in block

def test_knobs_are_fixed_width_and_compact():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    assert "self.setFixedSize(54, 74)" in source
    assert "self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)" in source
    assert "cell.setFixedWidth(82)" in source

def test_mute_switch_is_removed_from_gui():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    assert "class MuteSwitch" not in source
    assert "MuteSwitch(" not in source
    assert "mute_changed = Signal(int, bool)" in source

def test_inspector_scroll_position_is_restored_after_rebuild():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    start = source.index("    def _refresh_inspector(self, restore_anchor=None):")
    end = source.index("    def _remember_group", start)
    block = source[start:end]
    assert "scroll_value = self.inspector_scroll.verticalScrollBar().value()" in block
    assert "bar.setValue" in block


def test_inspector_refresh_keeps_geometry_pass_but_no_page_swap():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    start = source.index("    def _refresh_inspector(self, restore_anchor=None):")
    end = source.index("    def _remember_group", start)
    block = source[start:end]
    assert "layout.activate()" in block
    assert "self.inspector_scroll.updateGeometry()" in block
    assert "page.setMinimumHeight(required_h)" in block
    assert "old.deleteLater()" not in block
