from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'auricle_gui.py').read_text(encoding='utf-8')


def method(name, end=None):
    start = SOURCE.rfind(f'    def {name}')
    if end:
        stop = SOURCE.index(f'    def {end}', start)
        return SOURCE[start:stop]
    return SOURCE[start:]


def test_inspector_refresh_is_queued_for_channel_and_note_changes():
    block = method('_set_channel', '_set_port')
    assert '_queue_inspector_refresh("SOURCE")' in block
    assert '_refresh_inspector()' not in block


def test_mode_change_is_deferred():
    block = method('_set_mode', '_set_channel')
    assert 'QTimer.singleShot(0, apply_change)' in block
    assert '_refresh_inspector("SOURCE")' in block[block.index('def apply_change'):]
    assert '_refresh_inspector("SOURCE")' not in block[:block.index('def apply_change')]


def test_inspector_parameter_changes_do_not_rebuild_synchronously():
    block = method('_set_param', '_flush_param_regen')
    assert 'QTimer.singleShot(0, lambda bid=b.id: self._flush_param_regen(bid))' in block
    assert '_refresh_inspector(' not in block


def test_card_callbacks_do_not_destroy_the_emitting_card_synchronously():
    for name, end in [
        ('_card_rename_requested', '_card_mode_changed'),
        ('_card_mode_changed', '_rename_block'),
        ('_card_color_changed', '_block_colors_changed'),
    ]:
        block = method(name, end)
        assert 'QTimer.singleShot(0' in block


def test_destructive_inspector_actions_use_queued_refresh():
    for name, end in [
        ('add_process', 'remove_process'),
        ('remove_process', 'remove_mutator'),
        ('remove_mutator', '_tempo_changed'),
        ('add_mutator', 'add_relation'),
    ]:
        block = method(name, end)
        assert '_queue_inspector_refresh' in block
        assert '_refresh_inspector(' not in block


def test_queue_inspector_refresh_coalesces_rebuilds():
    block = method('_queue_inspector_refresh', '_refresh_inspector')
    assert '_inspector_refresh_queued' in block
    assert 'QTimer.singleShot(0, apply)' in block
    assert '_pending_inspector_anchor' in block
