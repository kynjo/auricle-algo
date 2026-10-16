from pathlib import Path


def test_block_type_change_is_deferred_and_coalesced():
    src = Path(__file__).parents[1].joinpath("auricle_gui.py").read_text(encoding="utf-8")
    assert "self._block_type_change_pending: dict[int, int] = {}" in src
    start = src.index("    def _set_block_type(self, b, value):")
    end = src.index("    def _card_type_changed", start)
    body = src[start:end]
    assert "QTimer.singleShot(0, apply_change)" in body
    assert "pending.get(block_id) != change_token" in body
    assert "self.transport._release_block_notes(block.id)" in body
    assert "self._refresh_inspector(\"SOURCE\")" in body


def test_dpg_frontend_remains_removed():
    root = Path(__file__).parents[1]
    assert not (root / "gui_dpg.py").exists()
    assert not (root / "run_dpg.py").exists()
