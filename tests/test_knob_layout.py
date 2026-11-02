"""Compact knob geometry and wrapping layout (no Qt required)."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI = (ROOT / "auricle_gui.py").read_text(encoding="utf-8")


def _function(name):
    tree = ast.parse(GUI)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = {}
    exec(compile(ast.Module([node], []), "auricle_gui", "exec"), namespace)
    return namespace[name]


def test_flow_columns_fit_available_width():
    columns = _function("knob_flow_columns")
    assert columns(700, 62, 6, 8) == 8       # all eight knobs in one row
    assert columns(400, 62, 6, 8) == 5       # wraps instead of overflowing
    assert columns(40, 62, 6, 8) == 1        # never zero columns
    assert columns(2000, 62, 6, 3) == 3      # never more columns than cells
    assert columns(500, 62, 6, 0) == 1


def test_knob_is_compact_and_readout_fits():
    assert "KNOB_W, KNOB_H = 46, 62" in GUI
    assert "self.setFixedSize(KNOB_W, KNOB_H)" in GUI
    assert "self.value_label.setGeometry(0, KNOB_H - 15, KNOB_W, 15)" in GUI
    # dial (centre 25, radius 19, 5 px pen) must end above the readout row
    assert 25 + 19 + 2.5 < 62 - 15


def test_no_stale_fixed_knob_widths():
    assert "setFixedWidth(74)" not in GUI
    assert "knob.setFixedWidth(54)" not in GUI
    assert "self.amount.setFixedWidth(54)" not in GUI
    rhythm = (ROOT / "drum_rhythm_ui.py").read_text(encoding="utf-8")
    assert "setFixedWidth(54)" not in rhythm and "setFixedWidth(74)" not in rhythm


def test_kit_panel_uses_one_wrapping_knob_field():
    start = GUI.index("def labelled_knob(label, knob):")
    end = GUI.index("self.rhythm_panel = DrumRhythmPanel(")
    block = GUI[start:end]
    assert block.count("KnobFlow(") == 1
    assert block.count("knob_flow.addWidget(") == 2          # kit loop + creative loop
    assert "creative = QHBoxLayout" not in block
    for name in ("copy_voice_button", "paste_voice_button", "keep_beat", "new_variant"):
        assert f"self.{name}" in block


def test_role_group_is_limited_to_five_cells_per_row():
    start = GUI.index("role_cols = 5")
    end = GUI.index("harmony = InspectorGroup(")
    block = GUI[start:end]
    assert "rof.addWidget(follow_plan, 2, 0, 1, 4)" not in block
    assert block.count("role_cell()") >= 4
