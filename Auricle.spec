# -*- mode: python ; coding: utf-8 -*-
"""Native Windows/Linux folder build and macOS .app bundle."""
from pathlib import Path
import runpy
import sys

ROOT = Path(SPECPATH).resolve()
VERSION = runpy.run_path(str(ROOT / "version.py"))["PACKAGE_VERSION"]
icon = None
if sys.platform == "win32":
    icon = str(ROOT / "assets" / "auricle.ico")
elif sys.platform == "darwin":
    icon = str(ROOT / "assets" / "auricle.icns")

a = Analysis(
    [str(ROOT / "auricle_gui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "assets"), "assets"),
        (str(ROOT / "examples"), "examples"),
        (str(ROOT / "docs"), "docs"),
        (str(ROOT / "README.md"), "."),
        (str(ROOT / "RELEASE_NOTES.md"), "."),
    ],
    hiddenimports=["mido.backends.rtmidi", "rtmidi"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtWebEngineCore",
              "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Auricle",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Auricle")
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Auricle.app",
        icon=icon,
        bundle_identifier="org.auricle.Auricle",
        version=VERSION,
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": VERSION,
            "CFBundleDisplayName": "Auricle",
        },
    )
