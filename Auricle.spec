# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for a one-folder Windows build: dist\Auricle\Auricle.exe
from PyInstaller.utils.hooks import collect_submodules

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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Auricle',
)
