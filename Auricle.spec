# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for a one-folder build on Windows, Linux and macOS:
#   Windows: dist/Auricle/Auricle.exe
#   Linux:   dist/Auricle/Auricle      (packaged into an AppImage by packaging/make_appimage.sh)
#   macOS:   dist/Auricle.app          (BUNDLE below)
import sys
from PyInstaller.utils.hooks import collect_submodules

# Single source of truth for the version shown in the macOS bundle.
_ns = {}
exec(open('version.py', encoding='utf-8').read(), _ns)
APP_VERSION = str(_ns.get('APP_VERSION', 'v0')).lstrip('v')

hiddenimports = [
    'mido.backends.rtmidi', 'rtmidi', 'transport_queue', 'transport_worker',
    'auricle_catalogs', 'auricle_model', 'auricle_engine',
    'auricle_relations', 'auricle_persistence', 'auricle_transport',
] + collect_submodules('mido.backends')

a = Analysis(
    ['auricle_gui.py'],
    pathex=['.'],
    binaries=[],
    datas=[('assets/auricle_logo.png', 'assets')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
# One-folder build: binaries/datas belong to COLLECT only (exclude_binaries=True).
# Passing them to EXE as well would also embed them in the executable.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Auricle',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='assets/auricle.ico' if sys.platform == 'win32' else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Auricle',
)

if sys.platform == 'darwin':
    # Change bundle_identifier to your own reverse-DNS id before publishing.
    app = BUNDLE(
        coll,
        name='Auricle.app',
        icon='assets/auricle.icns',
        bundle_identifier='com.auricle.midi',
        info_plist={
            'CFBundleName': 'Auricle',
            'CFBundleDisplayName': 'Auricle',
            'CFBundleShortVersionString': APP_VERSION,
            'CFBundleVersion': APP_VERSION,
            'NSHighResolutionCapable': True,
            'LSApplicationCategoryType': 'public.app-category.music',
        },
    )
