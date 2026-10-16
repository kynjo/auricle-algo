
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI = (ROOT / "auricle_gui.py").read_text(encoding="utf-8")
HELP = (ROOT / "help_content.py").read_text(encoding="utf-8")

def test_new_blocks_receive_persistent_random_color():
    assert "def random_block_color(" in GUI
    assert "color=random_block_color(existing_colors)" in GUI
    assert "_BLOCK_COLOR_PALETTE" in GUI

def test_mute_is_available_in_blocks_and_perform_and_shared():
    assert 'self.mute_button = QPushButton("M")' in GUI
    assert 'self.mute_button = QPushButton("MUTED" if block.muted else "MUTE")' in GUI
    assert GUI.count("mute_changed = Signal(int, bool)") >= 2
    assert "self.transport.set_block_muted(block_id, b.muted)" in GUI
    assert "self.performance.refresh_blocks(self.project)" in GUI

def test_help_documents_phrase_technique_tension_and_motifs_bilingually():
    for token in ("Phrase catalog", "Каталог Phrase", "Common Techniques", "Основные Techniques",
                  "Algorithm-specific Techniques", "Techniques конкретных алгоритмов",
                  "TensionCurve and Motifs", "TensionCurve и Motifs"):
        assert token in HELP
    assert "for phrase in PHRASES" in HELP
    assert "for preset in COMMON" in HELP
    assert "for algorithm, presets in ALGORITHM_GESTURES.items()" in HELP
