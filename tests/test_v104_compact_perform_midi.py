from pathlib import Path
GUI=(Path(__file__).resolve().parents[1]/"auricle_gui.py").read_text(encoding="utf-8")
def test_perform_card_v3_keeps_midi_activity():
    card=GUI[GUI.index("class PerformanceBlockCard"):GUI.index("class PerformancePanel")]
    assert "self.midi_indicator = QLabel()" in card
    assert "midi_on = bool(active) and not bool(self.block.muted)" in GUI

def test_perform_card_is_block_like_not_old_compact():
    card=GUI[GUI.index("class PerformanceBlockCard"):GUI.index("class PerformancePanel")]
    assert "lay = QHBoxLayout(self)" in card
    assert "GENERATOR" in card
    assert "PERFORMANCE" in card

def test_perform_grid_remains_multi_column():
    panel=GUI[GUI.index("class PerformancePanel"):GUI.index("class BlockCard")]
    assert "Qt.AlignLeft | Qt.AlignTop" in panel or "grid" in panel.lower()
