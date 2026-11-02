from pathlib import Path
from test_midi_learn_runtime_ui import app, editor
from ui_metrics import CARD_HEIGHT

GUI_SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"


def test_block_card_uses_compact_reference_layout(editor):
    _, win, _ = editor
    block = win.project.blocks[0]
    card = win.block_list.itemWidget(win.block_list.item(0))
    assert card.index_badge.text() == str(block.id)
    assert card.type_label.text() == block.block_type
    assert card.algorithm_label.text() == block.algorithm
    assert card.midi_label.text() == f"CH {block.midi_channel}"
    assert not card.type_icon.pixmap().isNull()
    assert card.menu_button.text() == "⋮"
    assert card.height() == CARD_HEIGHT


def test_mode_switch_is_horizontal():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    theme_source = (GUI_SOURCE.parent / "ui_themes.py").read_text(encoding="utf-8")
    assert 'layout = QHBoxLayout(self)' in source
    assert 'layout.addWidget(self.seq)' in source
    assert 'layout.addWidget(self.live)' in source
    assert 'layout.addWidget(self.seq, 1, 0)' not in source
