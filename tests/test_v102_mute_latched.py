from pathlib import Path
GUI=(Path(__file__).resolve().parents[1]/"auricle_gui.py").read_text(encoding="utf-8")
def test_mute_buttons_have_explicit_checked_visual_state():
    assert "QPushButton#blockMute:checked" in GUI
    assert "performMute" in GUI
    assert 'setText("MUTED" if checked else "MUTE")' in GUI
