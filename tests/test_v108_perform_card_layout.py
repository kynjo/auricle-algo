from pathlib import Path
GUI=(Path(__file__).resolve().parents[1]/"auricle_gui.py").read_text(encoding="utf-8")

def test_perform_card_has_block_like_split_layout():
    sec=GUI[GUI.index("class PerformanceBlockCard"):GUI.index("class PerformancePanel")]
    assert "lay = QHBoxLayout(self)" in sec
    assert "GENERATOR" in sec
    assert "PERFORMANCE" in sec

def test_perform_description_stays_with_generator_side():
    sec=GUI[GUI.index("class PerformanceBlockCard"):GUI.index("class PerformancePanel")]
    assert "self.description = QLabel" in sec
    assert "left.addWidget(self.description)" in sec
    assert "self.technique_curve = TechniqueCurveWidget()" in sec

def test_perform_keeps_functional_controls():
    sec=GUI[GUI.index("class PerformanceBlockCard"):GUI.index("class PerformancePanel")]
    for token in ("self.mode_switch = ModeSwitch(block.mode)", "self.mute_button = QPushButton", "self.enable = QPushButton", "self.restart = QPushButton"):
        assert token in sec
