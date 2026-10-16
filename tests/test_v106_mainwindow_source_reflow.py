from pathlib import Path
import ast

GUI_PATH=Path(__file__).resolve().parents[1]/"auricle_gui.py"

def test_source_reflow_helper_belongs_to_mainwindow():
    tree=ast.parse(GUI_PATH.read_text(encoding="utf-8"))
    owners={}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            owners[node.name]={n.name for n in node.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    assert "_reflow_inspector_responsive_forms" in owners["MainWindow"]
    assert "_reflow_inspector_responsive_forms" not in owners["Knob"]

def test_mainwindow_scrollbar_callback_targets_existing_method():
    source=GUI_PATH.read_text(encoding="utf-8")
    mw=source[source.index("class MainWindow"):]
    assert "def _reflow_inspector_responsive_forms(self):" in mw
    assert "verticalScrollBar().rangeChanged.connect" in mw
    assert "self._reflow_inspector_responsive_forms()" in mw
