# Auricle Algorithmic MIDI v111

Stability release after pitch, harmony, relations, LIVE, groove, voice smoothing, validation and GUI accessibility fixes.

## Included fixes
- Pitch model separation (relative vs MIDI pitch)
- Quantize pipeline validation
- Diatonic harmony generation
- Relations pipeline improvements
- LIVE MusicalContext and Groove processing
- Transport queue deduplication and callback error logging
- Drum-pattern groove analysis feeding dependent generators
- LIVE rest propagation across built-in role relations
- Unsaved project protection in New/Open/Quit flows
- Voice Smooth behaviour correction
- Validation test suite
- GUI accessibility and release cleanup
- Core refactor: model, catalogs, engine, relations, persistence and transport
  now live in separate modules.
- Current v107 project schema drops legacy PERCUSSION migration paths.
- Replaced the application logo with the new Auricle mark.
- Added a LIVE technique adapter for timing rate, swing, humanization,
  gate, velocity, accents and Euclidean phase.
- Softened LIVE velocity targeting so phrase Crescendo preserves a healthy
  baseline instead of jumping from a quiet start to a loud peak.
- Added a compact Perform timeline and normalized Technique Curve charts in
  every equal-width block card.


## v106
Live relation processing now follows source dependencies, Bass groove velocity
uses the selected Drum source, and MusicalContext carries both groove and
harmonic authority into dependent generators.

DRUM is now a Drum Machine container with independent Kick, Snare, Closed Hat,
Open Hat, Clap and Perc voices. Each voice has its own SEQ/LIVE mode, generator,
MIDI channel and base note. The v107 schema contains only the DRUM container for percussion.

## v102.1
UI release: theme-correct colours and contrast on all 13 themes, live Perform panels,
layout fixes and keyboard shortcuts. See CHANGELOG.md.

Run: `./run.sh` (Linux/macOS) or `setup_windows.bat` then `run_windows.bat` (Windows).
Build a Windows app with `build_windows.bat` (see docs/WINDOWS_BUILD.md).

## Perform: phrase duration

Use **GLOBAL PHRASE → Duration · beats** to set the phrase length from 4 to
256 quarter-note beats. In 4/4, 16 beats equals four bars; at 120 BPM it lasts
eight seconds. All stages stretch proportionally. Changing Duration while
the phrase plays preserves its current progress. Phrase selection, Duration
and Amount are saved in the project. The main transport LENGTH still controls
the pattern length; the card's Length controls an individual technique.
