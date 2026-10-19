"""Public Auricle v107 core API.

Implementation is split by responsibility; this module exposes only the
active v107 names consumed by the GUI and current test suite.
"""
import mido
import time

from version import APP_VERSION
from auricle_catalogs import *  # noqa: F401,F403
from auricle_model import *  # noqa: F401,F403
from auricle_engine import MusicEngine
from auricle_relations import validate_relations, next_relation_id, remove_relation, duplicate_relation
from auricle_persistence import save_project, load_project
from auricle_transport import Transport, get_midi_output_names
from performance_presets import PerformanceRuntime, presets_for, preset_for
from motif_engine import Motif, MotifEngine, PhraseState, TensionCurve
from music_director import MusicDirector
from voice_leading import VoiceLeading
from relation_context import MusicalContext
from musical_clock import MusicalClock

__all__ = [name for name in globals() if not name.startswith("_")]
