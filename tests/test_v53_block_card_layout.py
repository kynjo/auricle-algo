from pathlib import Path

GUI_SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"


def test_block_card_uses_compact_reference_layout():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    theme_source = (GUI_SOURCE.parent / "ui_themes.py").read_text(encoding="utf-8")
    assert 'self.index_badge = QLabel(str(block.id))' in source
    assert 'self.type_label = QLabel(f"Type: {block.block_type}")' in source
    assert 'self.algorithm_label = QLabel(f"Algorithm: {block.algorithm}")' in source
    assert 'self.midi_label = QLabel(f"MIDI Ch: {int(block.midi_channel)}")' in source
    assert 'self.menu_button = QPushButton("⋮")' in source
    assert 'QLabel#blockIndex' in theme_source
    assert 'QPushButton#cardMenu' in theme_source


def test_mode_switch_is_horizontal():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    theme_source = (GUI_SOURCE.parent / "ui_themes.py").read_text(encoding="utf-8")
    assert 'layout = QHBoxLayout(self)' in source
    assert 'layout.addWidget(self.seq)' in source
    assert 'layout.addWidget(self.live)' in source
    assert 'layout.addWidget(self.seq, 1, 0)' not in source
