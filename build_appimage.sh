#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
bash build.sh
PYTHON="$PWD/.venv-build/bin/python" bash packaging/make_appimage.sh
