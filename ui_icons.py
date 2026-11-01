"""Cached, theme-aware rendering of the original UI-base SVG assets."""
from functools import lru_cache
from pathlib import Path
import math

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QSizeF
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel

from auricle_resources import asset_path

BLOCK_ICON_NAMES = {name: name + ".svg" for name in ("DRUM", "BASS", "MELODY", "PAD", "CHORD")}
APP_ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 192, 256, 512)
LOGO_ASSET = 'auricle_logo.svg'


def _artwork_key():
    path = asset_path(LOGO_ASSET)
    if not path.is_file():
        # Older source checkouts still open; the build exporter requires SVG.
        path = asset_path('auricle_logo.png')
    try:
        stat = path.stat()
        return str(path), stat.st_mtime_ns, stat.st_size
    except OSError:
        return str(path), 0, 0


def _svg_rect(renderer, bounds):
    size = renderer.viewBoxF().size()
    if size.isEmpty(): size = QSizeF(renderer.defaultSize())
    if size.isEmpty(): return QRectF(bounds)
    fitted = size.scaled(bounds.size(), Qt.KeepAspectRatio)
    return QRectF(bounds.center().x() - fitted.width() / 2,
                  bounds.center().y() - fitted.height() / 2,
                  fitted.width(), fitted.height())


def render_svg_image(source, size, *, supersample=3):
    """Render original SVG colours with alpha, aspect ratio and smooth edges.

    Small OS icon sizes are rendered larger and reduced once. No small PNG is
    enlarged for a high-DPI window switcher or a native application icon.
    """
    size = QSize(size)
    if size.isEmpty(): return QImage()
    renderer = QSvgRenderer(str(source) if isinstance(source, (str, Path)) else source)
    if not renderer.isValid(): raise ValueError(f'Invalid SVG artwork: {source!s}' if isinstance(source, (str, Path)) else 'Invalid SVG artwork')
    renderer.setAnimationEnabled(False)
    factor = max(1, int(supersample))
    image = QImage(size * factor, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        painter.scale(factor, factor)
        renderer.render(painter, _svg_rect(renderer, QRectF(0, 0, size.width(), size.height())))
    finally: painter.end()
    return image.scaled(size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation) if factor > 1 else image


@lru_cache(maxsize=4)
def _application_icon(key):
    path = Path(key[0])
    icon = QIcon()
    if not path.is_file(): return icon
    if path.suffix.lower() != '.svg': return QIcon(str(path))
    # Explicit sizes are exported by Qt to Windows and _NET_WM_ICON on Linux.
    # A single tiny pixmap would be stretched by the window switcher.
    for size in APP_ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(render_svg_image(path, QSize(size, size))))
    return icon


def application_icon():
    return QIcon(_application_icon(_artwork_key()))


def logo_pixmap(size, dpr=1.):
    path = Path(_artwork_key()[0]); size = QSize(size)
    dpr = max(1., float(dpr)) if math.isfinite(float(dpr)) else 1.
    if path.suffix.lower() == '.svg' and path.is_file():
        pixels = QSize(math.ceil(size.width() * dpr), math.ceil(size.height() * dpr))
        pixmap = QPixmap.fromImage(render_svg_image(path, pixels))
    else:
        pixmap = QPixmap(str(path)).scaled(math.ceil(size.width() * dpr), math.ceil(size.height() * dpr),
                                            Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


class LogoLabel(QLabel):
    """Paint vector artwork on the actual device, including fractional DPI."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._artwork = None
        self._renderer = None

    def refresh(self):
        key = _artwork_key()
        if key == self._artwork: return
        self._artwork = key
        if self._renderer is not None: self._renderer.deleteLater()
        self._renderer = None
        if Path(key[0]).suffix.lower() == '.svg':
            renderer = QSvgRenderer(key[0], self)
            if renderer.isValid():
                renderer.setAnimationEnabled(False)
                self._renderer = renderer
            else:
                renderer.deleteLater()
        if self._renderer is None:
            super().setPixmap(logo_pixmap(self.contentsRect().size(), self.devicePixelRatioF()))
        self.update()

    def paintEvent(self, event):
        if self._renderer is None: return super().paintEvent(event)
        painter = QPainter(self)
        try:
            painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
            self._renderer.render(painter, _svg_rect(self._renderer, QRectF(self.contentsRect())))
        finally: painter.end()

    def pixmap(self):
        if self._renderer is not None:
            return logo_pixmap(self.contentsRect().size(), self.devicePixelRatioF())
        return super().pixmap()


@lru_cache(maxsize=128)
def block_type_icon(block_type, color="#ffffff", size=24):
    filename = BLOCK_ICON_NAMES.get(str(block_type).upper())
    if filename is None:
        return QIcon()
    renderer = QSvgRenderer(str(asset_path(filename)))
    if not renderer.isValid():
        return QIcon()
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(QRectF(0, 0, size, size), QColor(color))
    painter.end()
    return QIcon(pixmap)


@lru_cache(maxsize=128)
def navigation_icon(symbol, color, size=24):
    """Draw at the requested size rather than magnifying a 12-pixel glyph."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / 24, size / 24)
    painter.setPen(QPen(QColor(color), 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    if symbol == "▦":
        for x in (3, 13):
            for y in (3, 13):
                painter.drawRoundedRect(QRectF(x, y, 8, 8), 1.5, 1.5)
    elif symbol == "▤":
        painter.drawRoundedRect(QRectF(2, 3, 20, 18), 2, 2)
        for y, length in ((7, 12), (12, 8), (17, 15)):
            painter.drawLine(QPointF(5, y), QPointF(5 + length, y))
    elif symbol == "↔":
        painter.drawLine(QPointF(3, 8), QPointF(21, 8))
        painter.drawLine(QPointF(3, 16), QPointF(21, 16))
        for a, b in (((17, 4), (21, 8)), ((17, 12), (21, 8)),
                     ((7, 12), (3, 16)), ((7, 20), (3, 16))):
            painter.drawLine(QPointF(*a), QPointF(*b))
    elif symbol == "≋":
        points = ((3, 12), (6, 12), (8, 5), (11, 20), (14, 4), (17, 15), (19, 12), (22, 12))
        for a, b in zip(points, points[1:]):
            painter.drawLine(QPointF(*a), QPointF(*b))
    else:
        painter.drawEllipse(QRectF(3, 3, 18, 18))
        font = painter.font(); font.setPixelSize(17); font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(3, 2, 18, 20), Qt.AlignCenter, "?")
    painter.end()
    return QIcon(pixmap)
