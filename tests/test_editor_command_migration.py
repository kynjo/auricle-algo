"""Static regression checks for editor -> transport command queue migration."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _method(path, class_name, method_name):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return next(n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name)


def _calls(node, attribute):
    return [n for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == attribute]


def _direct_nodes(node):
    """Walk a method body but do not descend into its nested commit callback."""
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield from ast.walk(child)


def test_composition_planner_commits_through_transport_queue():
    method = _method("composition_planner_ui.py", "CompositionPlannerPanel", "_mark_changed")
    assert _calls(method, "enqueue_gui_command")
    assert not any(isinstance(n, ast.Attribute) and n.attr == "generate" for n in _direct_nodes(method))
    callback = next(n for n in ast.walk(method) if isinstance(n, ast.FunctionDef) and n.name == "apply_composition")
    assert any(isinstance(n, ast.Attribute) and n.attr == "composition" for n in ast.walk(callback))


def test_harmonic_plan_mutations_are_queued():
    method = _method("harmonic_plan_ui.py", "HarmonicPlanPanel", "apply")
    assert _calls(method, "enqueue_gui_command")
    callback = next(n for n in ast.walk(method) if isinstance(n, ast.FunctionDef) and n.name == "commit")
    assert any(isinstance(n, ast.Attribute) and n.attr == "harmonic_plan" for n in ast.walk(callback))


def test_instrument_dialogue_mutations_are_queued():
    method = _method("instrument_dialogue_ui.py", "DialogueControls", "changed")
    assert _calls(method, "enqueue_gui_command")
    callback = next(n for n in ast.walk(method) if isinstance(n, ast.FunctionDef) and n.name == "commit")
    assert any(isinstance(n, ast.Attribute) and n.attr == "parameters" for n in ast.walk(callback))
    assert any(isinstance(n, ast.Attribute) and n.attr == "apply_relations" for n in ast.walk(callback))


def test_parameter_influence_mutations_are_queued():
    changed = _method("parameter_influence_ui.py", "InfluenceDialog", "_changed")
    regenerate = _method("parameter_influence_ui.py", "InfluenceDialog", "_regenerate")
    assert _calls(changed, "enqueue_gui_command")
    assert _calls(regenerate, "enqueue_gui_command")
    assert not any(isinstance(n, ast.Attribute) and n.attr == "set_policy" for n in _direct_nodes(changed))
    assert not any(isinstance(n, ast.Attribute) and n.attr == "regenerate" for n in _direct_nodes(regenerate))
