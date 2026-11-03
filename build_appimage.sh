#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bash build.sh
.venv-build/bin/python packaging/fetch_appimage_tools.py
PYTHON="$PWD/.venv-build/bin/python" APPIMAGETOOL="$PWD/build/appimage/appimagetool" bash packaging/make_appimage.sh
