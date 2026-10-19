#!/usr/bin/env bash
# Build on the target OS; PYTHON selects the interpreter used to create the venv.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv-build/bin/python ]; then
  "${PYTHON:-python3}" -m venv .venv-build
fi
.venv-build/bin/python -m pip install -r requirements-build.txt
.venv-build/bin/python -m PyInstaller --noconfirm --clean Auricle.spec
printf '%s\n' "Build complete. See dist/ and docs/BUILDING.md."
