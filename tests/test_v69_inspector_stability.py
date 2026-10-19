from pathlib import Path

GUI_SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"

def _source():
    return GUI_SOURCE.read_text(encoding="utf-8")

def test_inspector_build_is_atomic_and_does_not_clear_live_page_first():
    source = _source()
    block = source[source.index("def _new_inspector_page"):source.index("def _remember_group")]
    assert "Build the next Inspector completely off-screen" in block
    assert "self.inspector_scroll.setWidget(page)" in block
    # The previous implementation removed every child before building the next page.
    assert "layout.takeAt(0)" not in block

def test_knob_has_room_for_numeric_readout():
    source = _source()
    assert "self.setFixedSize(54, 74)" in source
    assert 'self.value_label.setObjectName("knobValue")' in source

