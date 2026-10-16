from pathlib import Path
GUI=(Path(__file__).resolve().parents[1]/"auricle_gui.py").read_text(encoding="utf-8")

def test_perform_uses_functional_mode_switch_not_passive_label():
    section=GUI[GUI.index("class PerformanceBlockCard"):GUI.index("class PerformancePanel")]
    assert "self.mode_switch = ModeSwitch(block.mode)" in section
    assert "self.mode_switch.changed.connect(self._mode_changed)" in section
    assert "mode_changed = Signal(int, str)" in section
    assert 'self.mode_changed.emit(self.block_id, mode)' in section
    assert "mode = QLabel(block.mode)" not in section

def test_perform_mode_is_connected_to_shared_host_handler():
    panel=GUI[GUI.index("class PerformancePanel"):GUI.index("class BlockCard")]
    assert "card.mode_changed.connect(self.host._card_mode_changed)" in panel

def test_shared_mode_handler_regenerates_and_refreshes_both_views():
    start=GUI.index("def _card_mode_changed")
    end=GUI.index("def _rename_block", start)
    handler=GUI[start:end]
    assert "self.engine.reset_live()" in handler
    assert "self.engine.generate()" in handler
    assert "self._refresh_blocks()" in handler
    assert "self.performance.refresh_blocks(self.project)" in handler
