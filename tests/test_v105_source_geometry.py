from pathlib import Path
GUI=(Path(__file__).resolve().parents[1]/"auricle_gui.py").read_text(encoding="utf-8")

def test_knob_value_is_real_label_not_painted_text():
    knob=GUI[GUI.index("class Knob(QWidget):"):GUI.index("class ParamKnob")]
    assert "self.value_label = QLabel" in knob
    assert 'setObjectName("knobValue")' in knob
    assert "self.value_label.setText(self._formatted())" in knob
    assert "drawText(0, 51" not in knob

def test_source_generator_grid_is_responsive_not_hardcoded_four_columns():
    start=GUI.index("class _CompactGeneratorForm:")
    end=GUI.index("gform=_CompactGeneratorForm",start)
    form=GUI[start:end]
    assert "def _column_count(self):" in form
    assert "scroll.viewport().width()" in form
    assert "divmod(index,columns)" in form
    assert "divmod(self.index,4)" not in form

def test_scrollbar_width_change_triggers_source_reflow():
    assert "verticalScrollBar().rangeChanged.connect" in GUI
    assert "_reflow_inspector_responsive_forms" in GUI

def test_inspector_reflows_after_final_viewport_geometry():
    marker='page.resize(max(1, viewport_width), max(1, natural_h))'
    pos=GUI.index(marker)
    assert "_reflow_inspector_responsive_forms()" in GUI[pos:pos+700]
    assert "responsive_h" in GUI[pos:pos+900]
