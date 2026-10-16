from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_transport_mute_is_output_gate_not_scheduler_pause():
    src = (ROOT / 'auricle_transport.py').read_text()
    assert 'port = None if block.muted else' in src
    assert 'self.next_due.pop(block.id, None)' not in src
    assert 'self.next_live.pop(block.id, None)' not in src


def test_voice_smooth_ui_mapping_is_direct():
    src = (ROOT / 'auricle_gui.py').read_text()
    assert 'voice_leading.smoothness=max(0.0, min(1.0, float(value)/100.0))' in src
    assert 'director.voice_smooth=max(0.0, min(1.0, float(value)/100.0))' in src


def test_voice_leading_documents_semantics():
    src = (ROOT / 'voice_leading.py').read_text()
    assert '0.0 = free movement' in src
