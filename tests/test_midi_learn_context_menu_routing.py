from pathlib import Path


def test_knob_context_menu_is_not_consumed_by_parameter_influence_filter():
    source = Path(__file__).parents[1].joinpath("project_history_ui.py").read_text(encoding="utf-8")
    guard = "if parameter and kind == QEvent.ContextMenu and getattr(obj, '_auricle_has_midi_learn_menu', False):\n            return False"
    generic = "or kind == QEvent.ContextMenu):\n            self.flush()\n            self.show_influences(*parameter)"
    assert guard in source
    assert generic in source
    assert source.index(guard) < source.index(generic)


def test_bound_knobs_advertise_their_midi_learn_context_menu():
    source = Path(__file__).parents[1].joinpath("auricle_gui.py").read_text(encoding="utf-8")
    bind_start = source.index("    def bind_parameter(self, block_id, key):")
    bind_end = source.index("    def contextMenuEvent(self, event):", bind_start)
    bind = source[bind_start:bind_end]
    assert "self._auricle_has_midi_learn_menu = True" in bind
    assert "Right-click: MIDI Learn / clear mapping" in bind
