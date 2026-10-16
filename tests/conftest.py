import sys
from pathlib import Path

# The project uses a flat module layout; make it importable without PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
