"""Export native application icons from the same SVG used by the Qt UI."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
_ICON_APP = None


def prepare_icons(source, output):
    global _ICON_APP
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        raise FileNotFoundError(f'Application artwork is missing: {source}')
    # The exporter also runs on headless build machines; it never opens a UI.
    if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QBuffer, QIODevice, QSize
    from PySide6.QtGui import QGuiApplication
    from ui_icons import render_svg_image
    if QGuiApplication.instance() is None:
        _ICON_APP = QGuiApplication(['auricle-icon-export'])
    output.mkdir(parents=True, exist_ok=True)
    encoded = {}
    for size in (16, 20, 24, 32, 40, 48, 64, 96, 128, 192, 256, 512, 1024):
        image = render_svg_image(source, QSize(size, size))
        buffer = QBuffer(); buffer.open(QIODevice.WriteOnly)
        if not image.save(buffer, 'PNG'):
            raise RuntimeError(f'Could not encode application icon at {size} px')
        encoded[size] = bytes(buffer.data())

    # PNG-backed ICO entries preserve full alpha at every Windows icon size.
    sizes = (16, 20, 24, 32, 40, 48, 64, 96, 128, 192, 256)
    offset = 6 + 16 * len(sizes)
    directory = []
    for size in sizes:
        png = encoded[size]
        directory.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(png), offset))
        offset += len(png)
    ico = struct.pack('<HHH', 0, 1, len(sizes)) + b''.join(directory) + b''.join(encoded[size] for size in sizes)

    # Modern macOS ICNS stores PNG chunks, including native Retina variants.
    formats = ((b'icp4', 16), (b'icp5', 32), (b'icp6', 64), (b'ic07', 128),
               (b'ic08', 256), (b'ic09', 512), (b'ic10', 1024),
               (b'ic11', 32), (b'ic12', 64), (b'ic13', 256), (b'ic14', 512))
    chunks = b''.join(kind + struct.pack('>I', 8 + len(encoded[size])) + encoded[size] for kind, size in formats)
    icns = b'icns' + struct.pack('>I', 8 + len(chunks)) + chunks
    files = {'ico': output / 'auricle.ico', 'icns': output / 'auricle.icns', 'png': output / 'auricle_icon.png'}
    for key, data in (('ico', ico), ('icns', icns), ('png', encoded[512])):
        if not files[key].is_file() or files[key].read_bytes() != data:
            files[key].write_bytes(data)
    return files


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'assets' / 'auricle_logo.svg')
    parser.add_argument('--output', type=Path, default=ROOT / 'assets')
    args = parser.parse_args()
    for path in prepare_icons(args.source, args.output).values(): print(path)
