#!/usr/bin/env bash
# Build Auricle-linux-<arch>.AppImage from the PyInstaller output in dist/Auricle.
#
#   python -m PyInstaller --noconfirm --clean Auricle.spec
#   bash packaging/make_appimage.sh
#
# Needs `appimagetool` in PATH, or ./appimagetool, or APPIMAGETOOL=/path/to/it.
# Build on an older distribution (e.g. Ubuntu 22.04): the AppImage uses the glibc of the
# machine that built it, so it only runs on systems at least that new.
set -euo pipefail
cd "$(dirname "$0")/.."

ARCH="${ARCH:-$(uname -m)}"
OUT_DIR="${OUT_DIR:-out}"
APPDIR="AppDir"
APPIMAGETOOL="${APPIMAGETOOL:-$(command -v appimagetool || echo ./appimagetool)}"

if [ ! -x dist/Auricle/Auricle ]; then
  echo "dist/Auricle/Auricle not found. Run: python -m PyInstaller --noconfirm --clean Auricle.spec" >&2
  exit 1
fi
if [ ! -x "$APPIMAGETOOL" ]; then
  echo "appimagetool not found. Download it from https://github.com/AppImage/appimagetool/releases" >&2
  echo "and put it in PATH, or set APPIMAGETOOL=/path/to/appimagetool." >&2
  exit 1
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/icons/hicolor/512x512/apps" "$OUT_DIR"
cp -r dist/Auricle/. "$APPDIR/usr/bin/"

cp assets/auricle_icon.png "$APPDIR/auricle.png"
cp assets/auricle_icon.png "$APPDIR/.DirIcon"
cp assets/auricle_icon.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/auricle.png"

cat > "$APPDIR/auricle.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Auricle
Comment=Algorithmic MIDI generator
Exec=Auricle
Icon=auricle
Terminal=false
Categories=AudioVideo;Audio;Midi;
DESKTOP

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/Auricle" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# Lets appimagetool run on machines without FUSE (CI containers, minimal VMs).
export APPIMAGE_EXTRACT_AND_RUN=1
OUT_FILE="$OUT_DIR/Auricle-linux-$ARCH.AppImage"
ARCH="$ARCH" "$APPIMAGETOOL" "$APPDIR" "$OUT_FILE"
chmod +x "$OUT_FILE"
echo "Built $OUT_FILE"
