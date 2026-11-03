#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv-build/bin/python ]; then
  "${PYTHON:-python3}" -m venv .venv-build
fi
.venv-build/bin/python -m pip install -r requirements-build.txt
.venv-build/bin/python -m PyInstaller --noconfirm --clean Auricle.spec
.venv-build/bin/python packaging/smoke_native.py
case "$(uname -s)" in
  Darwin)
    case "$(uname -m)" in
      arm64) target=macos-arm64 ;;
      x86_64) target=macos-x64 ;;
      *) echo "Unsupported macOS architecture" >&2; exit 1 ;;
    esac ;;
  Linux) target=linux-x64 ;;
  *) echo "Use build_windows.bat on Windows" >&2; exit 1 ;;
esac
.venv-build/bin/python packaging/package_release.py "$target"
printf '%s\n' "Build complete: out/"
