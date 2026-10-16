from pathlib import Path


def test_v89_logo_asset_is_bundled_and_referenced():
    root = Path(__file__).parents[1]
    logo = root / "assets" / "auricle_logo.png"
    assert logo.exists()
    assert logo.stat().st_size > 1000

    gui = (root / "auricle_gui.py").read_text(encoding="utf-8")
    spec = (root / "Auricle.spec").read_text(encoding="utf-8")
    version = (root / "version.py").read_text(encoding="utf-8")

    assert 'asset_path("auricle_logo.png")' in gui
    assert 'setWindowIcon(QIcon(str(logo_path)))' in gui
    assert "assets/auricle_logo.png" in spec
    assert 'APP_VERSION = "v110"' in version
