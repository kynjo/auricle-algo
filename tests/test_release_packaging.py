"""Packaging regressions: runtime inventory, platform resources and release tags."""
import ast
import importlib.util
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_all_local_runtime_imports_are_included_in_wheel():
    tomllib = pytest.importorskip("tomllib")
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    modules = set(config["tool"]["setuptools"]["py-modules"])
    local = {path.stem for path in ROOT.glob("*.py")}
    for name in modules:
        path = ROOT / f"{name}.py"
        assert path.is_file(), name
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports = [node.module.split(".")[0]]
            for dependency in imports:
                if dependency in local:
                    assert dependency in modules, (name, dependency)


@pytest.mark.parametrize("platform,extension", [("win32", ".ico"), ("darwin", ".icns"), ("linux", None)])
def test_spec_builds_native_bundle_with_all_artwork(platform, extension, monkeypatch, tmp_path):
    # Execute the spec with recording build primitives; do not require PyInstaller.
    calls = {}
    def stage(name):
        def record(*args, **kwargs):
            calls[name] = (args, kwargs)
            return SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[])
        return record
    primitives = {name: stage(name) for name in ("Analysis", "PYZ", "EXE", "COLLECT", "BUNDLE")}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "platform", platform)
    runpy.run_path(str(ROOT / "Auricle.spec"), init_globals={"SPECPATH": str(ROOT), **primitives})
    data = dict(calls["Analysis"][1]["datas"])
    assert data[str(ROOT / "assets")] == "assets"
    assert all(Path(path).exists() for path in data)
    icon = calls["EXE"][1]["icon"]
    if extension:
        assert Path(icon).is_file() and Path(icon).suffix == extension
    else:
        assert icon is None
    assert ("BUNDLE" in calls) == (platform == "darwin")
    if platform == "darwin":
        assert calls["BUNDLE"][1]["name"] == "Auricle.app"


def test_wheel_and_frozen_assets_work_outside_source(monkeypatch, tmp_path):
    # An isolated copy of the resolver cannot accidentally use source assets.
    source = tmp_path / "auricle_resources.py"
    source.write_bytes((ROOT / "auricle_resources.py").read_bytes())
    spec = importlib.util.spec_from_file_location("isolated_resources", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    package = tmp_path / "installed" / "auricle_assets"
    package.mkdir(parents=True)
    (package / "__init__.py").touch()
    (package / "auricle_logo.png").write_bytes(b"wheel artwork")
    monkeypatch.syspath_prepend(str(package.parent))
    monkeypatch.chdir(tmp_path)
    assert module.asset_path("auricle_logo.png").read_bytes() == b"wheel artwork"
    bundle = tmp_path / "frozen"
    (bundle / "assets").mkdir(parents=True)
    (bundle / "assets/auricle_logo.png").write_bytes(b"frozen artwork")
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    assert module.asset_path("auricle_logo.png").read_bytes() == b"frozen artwork"


def test_release_tag_and_github_screenshot_links(tmp_path, monkeypatch):
    import os
    root = tmp_path / "repo"
    (root / "packaging").mkdir(parents=True)
    script = root / "packaging/release_metadata.py"
    script.write_bytes((ROOT / "packaging/release_metadata.py").read_bytes())
    (root / "version.py").write_bytes((ROOT / "version.py").read_bytes())
    (root / "RELEASE_NOTES.md").write_bytes((ROOT / "RELEASE_NOTES.md").read_bytes())
    version = runpy.run_path(str(root / "version.py"))["APP_VERSION"]
    env = {**os.environ, "GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "v0",
           "GITHUB_REPOSITORY": "example/auricle", "GITHUB_SHA": "abc123"}
    bad = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True)
    assert bad.returncode != 0
    assert not (root / "build/release-notes.md").exists()
    env["GITHUB_REF_NAME"] = version
    good = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True)
    assert good.returncode == 0, good.stderr
    notes = (root / "build/release-notes.md").read_text(encoding="utf-8")
    assert "https://github.com/example/auricle/blob/abc123/docs/screenshots/auricle-v111.png?raw=true" in notes
    assert "(README.md)" not in notes
