"""Artwork stays readable after theme changes and is available to packaging."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel
from auricle_gui import MainWindow
from auricle_resources import REQUIRED_ASSETS, asset_path
from ui_themes import theme_palette


def test_release_assets_exist():
    for name in REQUIRED_ASSETS:
        assert asset_path(name).is_file(), name
        assert asset_path(name).stat().st_size > 1000


def test_logo_keeps_its_original_colours_on_light_and_dark_themes():
    app = QApplication.instance() or QApplication([])
    class Host:
        brand_logo = QLabel()
        help_logo = QLabel()

    host = Host()
    for theme in ("Midnight", "Solar"):
        host._active_theme = theme_palette(theme)
        MainWindow._refresh_theme_assets(host)
        for label, size in ((host.brand_logo, (56, 53)), (host.help_logo, (74, 60))):
            expected = QPixmap(str(asset_path("auricle_logo.png"))).scaled(
                *size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            assert not label.pixmap().isNull()
            assert label.pixmap().toImage() == expected.toImage()
    app.processEvents()
