#!/usr/bin/env bash
# Create a virtual environment on first run, then start Auricle.
set -e
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
if [ ! -x .venv/bin/python ]; then
  "$PYTHON" -m venv .venv
  .venv/bin/python -m pip install -U pip
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python auricle_gui.py "$@"
