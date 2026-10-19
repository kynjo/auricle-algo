#!/usr/bin/env bash
# Package dist/Auricle using the original PNG artwork; no ImageMagick is needed.
set -euo pipefail
cd "$(dirname "$0")/.."
ARCH="${ARCH:-$(uname -m)}"
case "$ARCH" in
  x86_64) ARTIFACT_ARCH=x64 ;;
  aarch64|arm64) ARCH=aarch64; ARTIFACT_ARCH=arm64 ;;
  *) echo "Unsupported AppImage architecture: $ARCH" >&2; exit 1 ;;
esac
OUT_DIR="${OUT_DIR:-out}"
APPDIR=AppDir
APPIMAGETOOL="${APPIMAGETOOL:-$(command -v appimagetool || true)}"
APPIMAGETOOL="${APPIMAGETOOL:-./appimagetool}"
if [ ! -x dist/Auricle/Auricle ]; then
  echo "Build first: bash build.sh" >&2
  exit 1
fi
if [ ! -x "$APPIMAGETOOL" ]; then
  echo "Set APPIMAGETOOL to an executable from https://github.com/AppImage/appimagetool/releases" >&2
  exit 1
fi
VERSION="$("${PYTHON:-python3}" -c 'from version import APP_VERSION; print(APP_VERSION)')"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/icons/hicolor/512x512/apps" "$OUT_DIR"
cp -R dist/Auricle/. "$APPDIR/usr/bin/"
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
export APPIMAGE_EXTRACT_AND_RUN=1
OUT_FILE="$OUT_DIR/Auricle-$VERSION-linux-$ARTIFACT_ARCH.AppImage"
ARCH="$ARCH" "$APPIMAGETOOL" "$APPDIR" "$OUT_FILE"
chmod +x "$OUT_FILE"
printf 'Built %s\n' "$OUT_FILE"
