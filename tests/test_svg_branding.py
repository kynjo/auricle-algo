"""The actual SVG drives UI artwork, high-DPI window icons and native files."""
from pathlib import Path
import runpy
import struct

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtWidgets import QApplication

import ui_icons
from auricle_resources import asset_path
from test_kit_preview_lifecycle import inspector


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def alpha_values(image):
    return {image.pixelColor(x, y).alpha() for x in range(image.width()) for y in range(image.height())}


def test_original_svg_renders_transparency_and_antialiased_edges(app):
    image = ui_icons.render_svg_image(asset_path('auricle_logo.svg'), QSize(32, 32))
    assert image.size() == QSize(32, 32)
    alpha = alpha_values(image)
    assert 0 in alpha and 255 in alpha and any(0 < value < 255 for value in alpha)
    assert image.pixelColor(0, 0).alpha() == 0


@pytest.mark.parametrize('dpr', [1., 1.25, 1.5, 2., 3.])
def test_window_switcher_has_native_pixels_for_each_dpi(app, dpr):
    icon = ui_icons.application_icon()
    assert {size.width() for size in icon.availableSizes()} == set(ui_icons.APP_ICON_SIZES)
    pixmap = icon.pixmap(QSize(32, 32), dpr)
    assert pixmap.size() == QSize(round(32 * dpr), round(32 * dpr))
    assert pixmap.devicePixelRatioF() == pytest.approx(dpr)
    assert any(0 < a < 255 for a in alpha_values(pixmap.toImage()))


@pytest.mark.parametrize('dpr', [1., 1.25, 1.5, 2., 3.])
def test_header_render_uses_actual_device_resolution(app, dpr):
    pixmap = ui_icons.logo_pixmap(QSize(56, 52), dpr)
    assert pixmap.size() == QSize(round(56 * dpr), round(52 * dpr))
    assert pixmap.devicePixelRatioF() == pytest.approx(dpr)


def test_non_square_svg_keeps_aspect_ratio(app):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"><rect width="100" height="50" fill="#ff0000"/></svg>'
    image = ui_icons.render_svg_image(svg, QSize(40, 40))
    assert image.pixelColor(20, 2).alpha() == 0
    assert image.pixelColor(20, 20).red() == 255
    assert image.pixelColor(20, 20).alpha() == 255
    assert image.pixelColor(20, 38).alpha() == 0


def test_bad_svg_fails_export_instead_of_silently_using_old_native_art(app):
    with pytest.raises(ValueError, match='Invalid SVG'):
        ui_icons.render_svg_image(b'<bad/>', QSize(32, 32))


def test_mainwindow_and_help_use_vector_labels_after_theme_changes(inspector):
    gui, win, drum, melody, errors = inspector
    before = []
    for label in (win.brand_logo, win.help_logo):
        assert isinstance(label, ui_icons.LogoLabel)
        assert label._renderer.isValid()
        before.append(label.pixmap().toImage())
    win.theme_combo.setCurrentText('Porcelain')
    assert [label.pixmap().toImage() for label in (win.brand_logo, win.help_logo)] == before
    assert {size.width() for size in win.windowIcon().availableSizes()} == set(ui_icons.APP_ICON_SIZES)
    assert not errors


def test_native_export_contains_readable_frames_and_retina_images(app, tmp_path):
    exporter = runpy.run_path(str(Path(__file__).parents[1] / 'packaging/render_icons.py'))['prepare_icons']
    files = exporter(asset_path('auricle_logo.svg'), tmp_path)
    ico = files['ico'].read_bytes()
    assert struct.unpack_from('<HHH', ico) == (0, 1, 11)
    sizes = set()
    for index in range(11):
        width, height, _, _, planes, bits, length, offset = struct.unpack_from('<BBBBHHII', ico, 6 + index * 16)
        size = width or 256
        assert size == (height or 256) and planes == 1 and bits == 32
        image = QImage.fromData(ico[offset:offset+length], 'PNG')
        assert image.size() == QSize(size, size)
        sizes.add(size)
    assert {16, 24, 32, 48, 64, 128, 256} <= sizes
    icns = files['icns'].read_bytes()
    assert icns[:4] == b'icns' and struct.unpack_from('>I', icns, 4)[0] == len(icns)
    offset, chunks = 8, {}
    while offset < len(icns):
        length = struct.unpack_from('>I', icns, offset + 4)[0]
        image = QImage.fromData(icns[offset+8:offset+length], 'PNG')
        assert not image.isNull()
        chunks[icns[offset:offset+4]] = image.size()
        offset += length
    assert chunks[b'ic10'] == QSize(1024, 1024)
    assert chunks[b'ic11'] == QSize(32, 32) and chunks[b'ic14'] == QSize(512, 512)
    for suffix in ('ico', 'icns'):
        reader = QImageReader(str(files[suffix]))
        assert reader.canRead() and reader.imageCount() == 11
    assert QImage(str(files['png'])).size() == QSize(512, 512)
    previous = {kind: path.stat().st_mtime_ns for kind, path in files.items()}
    exporter(asset_path('auricle_logo.svg'), tmp_path)
    assert {kind: path.stat().st_mtime_ns for kind, path in files.items()} == previous
