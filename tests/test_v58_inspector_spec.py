from pathlib import Path

GUI_SOURCE = Path(__file__).resolve().parents[1] / "auricle_gui.py"


def test_inspector_layers_are_single_vertical_workflow():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    assert 'layer.setObjectName(f"inspectorLayer_{key}")' in source


def test_only_source_is_expanded_by_default():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    assert 'make_layer("SOURCE","SOURCE",' in source
    assert 'make_layer("SOURCE","SOURCE",f"{b.algorithm} · generator parameters",True)' in source
    for layer in ("STRUCTURE", "MUSICAL", "MOTION", "MONITOR"):
        marker = f'"{layer}", "{layer}"' if layer in ("STRUCTURE", "MUSICAL") else f'make_layer("{layer}"'
        start = source.index(marker)
        end = source.find('\n\n', start)
        assert 'False)' in source[start:end]


def test_block_header_is_not_a_collapsible_layer():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    start = source.index('general = QFrame()')
    end = source.index('# SOURCE', start)
    block = source[start:end]
    assert 'setObjectName("inspectorBlockHeader")' in block
    assert 'InspectorGroup("BLOCK"' not in block


def test_targeted_scroll_restore_uses_stable_group_identity():
    source = GUI_SOURCE.read_text(encoding="utf-8")
    assert 'anchor if anchor.startswith("inspector") else ("inspectorGroup_" + anchor)' in source
    assert 'target.mapTo(current_page, QPoint(0, 0)).y()' in source
    assert 'self._queue_inspector_refresh("PROCESS")' in source
    assert 'self._queue_inspector_refresh("MUTATION")' in source
