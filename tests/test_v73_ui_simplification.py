from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"


def test_output_and_block_state_removed_from_block_inspector():
    source = SOURCE.read_text(encoding="utf-8")
    assert 'make_layer("OUTPUT"' not in source
    assert 'InspectorGroup("OUTPUT PORTS"' not in source
    monitor = source[source.index("# MONITOR / diagnostics"):source.index("    def _remember_group")]
    assert 'BlockStatePanel' not in monitor
    assert 'piano roll' in monitor.lower()


def test_only_top_level_layers_are_collapsible():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("class InspectorGroup(QGroupBox):")
    end = source.index("class LayerGroup(QGroupBox):", start)
    nested = source[start:end]
    assert 'Non-collapsible nested inspector group' in nested
    assert 'self.accordion_toggled.emit' not in nested
    assert '▾' not in nested and '▸' not in nested
    layer = source[source.index("class LayerGroup(QGroupBox):"):source.index("class PatchNode", source.index("class LayerGroup(QGroupBox):"))]
    assert 'self.accordion_toggled.emit(self._expanded)' in layer


def test_block_card_has_compact_midi_activity_indicator():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("class BlockCard(QFrame):")
    end = source.index("class ", start + 10) if "class " in source[start + 10:] else len(source)
    card = source[start:end]
    assert 'self.midi_indicator = QLabel()' in card
    assert 'setObjectName("midiSendIndicator")' in card
    assert 'setFixedSize(7, 7)' in card
    assert 'MIDI activity' in card


def test_midi_pulse_resolves_card_by_stable_block_id():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("def _pulse_midi_indicator")
    end = source.index("def _set_midi_indicator", start)
    block = source[start:end]
    assert 'QTimer.singleShot(85, lambda bid=block_id' in block
    assert 'self._set_midi_indicator(block_id, True)' in block


def test_midi_indicator_is_pulsed_for_any_outbound_message():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("def log_midi_message")
    end = source.index("def _pulse_midi_indicator", start)
    block = source[start:end]
    assert 'self._midi_message_signal.emit' in block
    assert 'def _handle_midi_message' in block
    assert 'self._pulse_midi_indicator(int(block_id))' in block
    assert block.index('self._pulse_midi_indicator(int(block_id))') < block.index('if message.type == "note_on"')
