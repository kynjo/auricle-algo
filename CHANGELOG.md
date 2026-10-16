## v111 — Perform compact layout and phrase duration (2026-10-16)

- Removed the separate Phrase Form panel from Perform.
- Removed the Technique Curve caption; retained the 140 × 100 px parameter plots.
- Tightened card rows and placed Enable / Restart side by side.
- Added Global Phrase → Duration in quarter-note beats (4–256). Phrase stages
  and the Director contour stretch proportionally. Editing a running phrase
  preserves its progress, including the active technique's progress.
- Saved the selected phrase, duration and amount with the project.
- Made timeline ruler labels adapt to long phrases.
- Added runtime and UI persistence coverage; 412 tests pass.

## v111 - Perform UI bug fixes

- Added collapsible Global Phrase, Macros, Form and Musical Director sections.
- Timeline and Form now follow each phrase's real stages and beat total.
- Fixed stopped-transport phrase preview, live Amount updates and LIVE activity metering.
- Added phrase target selection, route hints, dynamic curve legends and theme-aware drawing.
- Reworked Perform cards to use content-driven height and accessible action labels.

## v110 - Perform UI

- Added a 16-beat phrase timeline with stage segments, progress fill and a
  moving playhead.
- Added normalized Technique Curve charts to each Perform block card; the
  chart shows which parameters the selected gesture moves over time.
- Standardized card height, grid expansion and control widths for readable
  two-column Perform layouts.
- Documented Shape semantics: `in`, `out`, `in/out` and `pulse`.

## v109 - LIVE velocity balance

- LIVE `velocity_base` techniques now blend toward their target instead of
  replacing natural event velocity, keeping Crescendo and Diminuendo musical
  at phrase boundaries.
- LIVE accent techniques use a bounded accent contribution and avoid clipping
  the whole event stream.

## v108 - LIVE technique adapter

- LIVE now consumes active Perform technique values for timing rate, swing,
  humanization, timing offset, gate, velocity base/accent and Euclidean phase.
- Temporary LIVE overrides stay in the active performance runtime and do not
  overwrite the saved block parameters.
- Added behavioral coverage for timing, articulation, dynamics and Euclidean
  phase changes in LIVE mode.

## v107 - Core module split

- Split the former monolithic `auricle_core.py` into `auricle_model.py`,
  `auricle_catalogs.py`, `auricle_engine.py`, `auricle_relations.py`,
  `auricle_persistence.py` and `auricle_transport.py`.
- Kept `auricle_core.py` as a small current-API facade for the GUI while
  removing legacy PERCUSSION project migration code.
- Removed tests that only protected obsolete project formats or source-file
  layout; behavior tests now target the responsible module.
- Replaced `assets/auricle_logo.png` with the supplied logo.

## v106 - Drum Machine voices

- Replaced the standalone PERCUSSION block type with a nested DRUM Machine.
- Added independent KICK, SNARE, CLOSED HAT, OPEN HAT, CLAP and PERC voices.
- Each voice owns its algorithm, SEQ/LIVE mode, MIDI channel, base note, mute
  state and output stream; the parent DRUM output remains the union used by
  Drum -> Bass relations.
- Added compact Drum Voice/KIT controls to the DRUM inspector, including a
  16-step SEQ lane, LIVE stream mode and per-voice routing. Selecting a voice
  opens the normal generator/structure/musical/motion/monitor controls for that
  sound, and voice names can be edited and saved.
- Pinned Drum Voices / Kit above the scrolling voice Inspector, so voice
  selection keeps the kit visible while parameters appear below.
- Switching a voice between SEQ and LIVE in Drum Voices / Kit refreshes its
  Pattern / LIVE stream lane and the selected voice's Inspector after the
  button event completes, preserving the Inspector's scroll position.
- Re-applied relations after live child voices update the parent Drum snapshot,
  keeping parent Drum sources and destinations audible in both modes.

## v105 - Live relation and MusicalContext wiring

Live transport blocks are ordered after their LIVE relation sources, including
built-in Drum -> Bass and Chord -> Melody links, so reordering blocks no longer
changes which event a destination hears. Bass rhythm and velocity shaping use
the selected Drum source consistently. MusicalContext now analyzes chord
activity, publishes harmony metrics and lets harmonic confidence adjust Chord
-> Melody anchoring alongside groove metrics.
Mouse-wheel editing remains active while the pointer is over a knob or numeric
stepper; keyboard focus is no longer required for hover-based adjustment.

## v104 - System stability

Threading and MIDI UI
- MIDI monitor, piano-roll history, activity LEDs and status messages are
  marshalled to the Qt thread through queued signals; the transport worker no
  longer touches widgets directly.
- Transport state and native MIDI port operations are serialized with a
  re-entrant lock during PLAY/STOP and port refresh.

Musical relations
- Director PerformanceState dataclasses now update MusicalContext energy and
  tension instead of being silently ignored.
- Bass groove shaping follows the selected Drum source, stale groove resets
  when no drums remain, and Drum/Chord regeneration rebuilds dependent SEQ
  blocks before applying relations.
- LIVE rests remain zero after role or user relations and chord anchoring no
  longer wraps forward to a future chord step.

Persistence and input
- Macro edits, macro routes, randomize and mutator changes mark the project
  dirty so destructive navigation cannot discard them silently.
- Knob and stepper wheel changes require keyboard focus.

Tests
- Added v104 regressions for Director context, groove source/reset/rebuild,
  LIVE rests, chord timing, Qt signal marshalling, dirty tracking and focus.

## v103.2 - Stability

Transport
- Lookahead tick scheduling is idempotent: duplicate planned timestamps are ignored.
- Worker callback exceptions are logged with traceback and counted instead of being swallowed.
- Added regression coverage for queue deduplication, BPM-grid dispatch and failure reporting.

Musical context
- Drum rhythm and accent streams are analyzed into density, syncopation, accent and groove metrics.
- MusicalContext.groove is refreshed before dependent SEQ/LIVE generators run, so Drum → Bass
  behavior responds to the actual selected drum pattern.
- LIVE generators publish a one-step rest before relation evaluation when a pattern/probability/
  density gate skips an event, preventing stale Drum or Chord events from leaking downstream.
- Added behavioral tests proving sparse and dense drum patterns produce different bass timing.

GUI safety
- Unsaved project changes are marked in the window title and prompt before New, Open or Quit.
- Saving clears the dirty marker; loading a project starts a clean editing session.

## v102.2 - Engine fixes

Tonality and harmony
- Final quantization compared relative pitches with the absolute root, shifting the scale by the
  key: non-C keys could send wrong notes (A major sent D#). Pitches are now quantized in the
  root-relative frame everywhere (SEQ, LIVE, relations, chord anchor).
- CHORD/PAD voicings stack diatonic thirds on the degree of the generated root (a fixed I-chord
  shape transposed onto every root produced chords such as A-C#-E in C major).
- Chord -> Melody anchoring is quantized to the melody scale again (it produced C#, Bb, Ab in C).
- quantize_interval_to_scale considers the next octave (11 -> 12 in a pentatonic, not 11 -> 9).
- Voice Smooth: 0 = free movement (it froze the voice on one note), 1 = nearest-octave voice
  leading with a tight leap limit; no fractional blending; SEQ smoothing is deterministic.

Timing
- Swing delays the off-beats (it made them early).
- Humanize jitters each step only; it no longer accumulates into a drift off the grid.
- Mute only releases notes: the clock and the pattern position keep running, so unmute is in phase.
- After a stall the missed steps advance the pattern too; blocks added or switched to SEQ during
  playback join the shared 16th grid.

Relations
- Relations aimed at LIVE blocks are audible: events are built after relations, and LIVE
  destinations read their sources at the current transport step instead of step 0.
- Pitch relation results stay in the destination scale; rhythm relations give new hits the
  block velocity and gate (they were sent with velocity 1).
- relation_drum_source / relation_chord_source select the built-in groove/harmony source again.
- Groove mode "Replace" keeps only the selected drum hits (it behaved like "Union").
- The groove stage runs for SEQ and LIVE alike.

Director, persistence, performance
- LIVE events no longer apply event probability twice while a phrase runs.
- Phrase stage crossfade uses the intended in/out curve (typo "in-out").
- Projects are saved atomically: a failed save keeps the previous file intact.
- LIVE blocks outside every relation skip the project-wide relation pass.

Tests
- 84 new regression tests (all 12 keys x 5 generators send in-scale MIDI, chords per scale,
  swing/humanize/mute/grid, LIVE relations, atomic save...). test_v114 now checks sent MIDI notes,
  and the curve/delay test checks a non-pitch dimension because pitch results are quantized.

## v102.1 - UI fixes

Themes and palette
- Every theme colour is derived from theme tokens: PLAY/STOP/DELETE/× no longer use
  hard-coded dark fills (on Solar/Cream Studio the text contrast was 1.2-1.6:1, now >= 7:1).
- Text on accent/success/danger surfaces is picked for WCAG contrast (SEQ/LIVE on Mono was 1.5:1).
- A QPalette is built from the theme and applied app-wide with the stylesheet (Fusion base style):
  knobs, piano roll, preview, dialogs and menus now follow the theme instead of default blue.
- Logo and tab icons are tinted with the theme colours (the white logo was invisible on light themes).
- Styled checkboxes (indicator was invisible on dark themes), scrollbars, menus, combo popups,
  disabled states and slider fill; labels no longer paint background patches inside cards.

Layout and widgets
- "SCALE & PITCH" title rendered as "SCALE _PITCH" (Qt mnemonic) - escaped.
- Stepper "+" button was clipped; steppers round "12.6" and ignore horizontal scrolling.
- Knobs: visible keyboard-focus ring, trackpad scrolling for integer knobs, double-click resets
  to the real default (STRUCTURE/TIMING/ROLE/MUTATION/HARMONY used the current value).
- Inspector fills the window after resize/maximize; empty Inspector page is installed when no block
  is selected; nested groups re-measure on expand (clipped knob values).
- Process controls: label above combo/checkbox, wider cells (combos were clipped); route
  parameters shown with readable names. Algorithm preview caption was drawn outside the widget.
- HARMONY is shown only for PAD/CHORD and ROLE only for roles that have a register profile.
- Block list has no horizontal scrollbar; Relations inspector captions/controls are aligned;
  built-in DRUM→BASS / CHORD→MELODY relations are explained on the Relations tab.

Perform tab
- FORM panel and phrase stage strip follow the running PhraseState (they were static placeholders).
- Card diagnostics show live groove/harmony sources, relation counts, motif and density.
- Phrase STOP stops the running phrase even after the selector moved; STOP is disabled when idle.
- A finished technique switches its card to OFF (it stayed ON and restarted on every card rebuild).
- Selected Perform card border is visible; mute/mode changes update cards in place; changing
  type/algorithm/mode in the Inspector refreshes the Perform cards; replaced cards are hidden at once.
- Director controls are re-applied to the engine after New/Open project.

Main window
- Project menu: New (Ctrl+N), Open (Ctrl+O), Save (Ctrl+S), Save as (Ctrl+Shift+S), Refresh MIDI (F5),
  Quit; Space toggles PLAY/STOP; window title shows the project file; save errors of any kind are reported.
- New blocks get their role defaults and the first free MIDI channel.
- MIDI activity LEDs restyle only on state changes (one timer per burst); the MIDI monitor is
  flushed in batches on the 80 ms UI heartbeat; button sync moved off the 5 ms MIDI clock.
- Accessible names for steppers, knobs, combos and relation fields.
- help_content.py runs on Python 3.9-3.11 again (no line breaks inside f-string fields).

## v102.0 - Tonality hardening release

- Full tonality validation across pitch generators.
- Fixed relative/absolute pitch separation.
- Added rhythm validation coverage.

## v101.2 - Real rhythm-first relations

- Added automatic Drum → Bass groove masks with stable per-step follow amount,
  groove offset, velocity accents and generated note durations.
- Added automatic Chord → Melody nearest chord-tone anchoring with configurable
  strength and reuse of the last active chord across chord rests.
- Exposed the relation controls in each BASS/MELODY role panel and added
  focused regression tests.

## v100 - Musical Director cleanup

- Unified phrase execution around a single `PhraseState`; removed the legacy parallel phrase-state dictionary.
- Connected PhraseState stage progression, smooth STOP/release snapshots, target blocks and active motifs.
- Added real TensionCurve presets (Gentle rise, Crescendo, Peak and release) and separated tension amount from curve smoothing.
- Loaded/saved Motif data into the runtime MotifEngine and applied active role motifs to SEQ and LIVE representations.
- Applied Director Energy, Density, Probability and Register influence to actual generation instead of writing temporary block parameters.
- Connected Perform Voice smooth to the real VoiceLeading smoothness and kept voice leading role/register safe.
- Added Director influence to LIVE generation and preserved scale-safe output while the Director is inactive.
- Added mid-phrase PhraseState/Motif persistence and v100 integration tests.

## v99
- Motif / PhraseState / TensionCurve foundations.
# Audit fixes (2026-10-15)

- Coalesced Global Macro route application so slider drags generate once per burst.
- Applied Energy, Density and Variation macros to LIVE events as well as SEQ material.
- Restored the visible phrase selector and amount from loaded PhraseState without marking projects dirty.
- Preserved Drum Voice MIDI channel overrides from the full Inspector and refreshed the pinned kit after voice edits.
- Cached MIDI output discovery for the drum kit and Inspector; inherited Drum Voice ports now reopen correctly.
- Aggregated Drum Voice MIDI history in the parent piano roll and recorded all pitches for CHORD/PAD history.
- Made header macro sliders adaptive to the window width and exposed built-in relation status in the Relations tab.
- Equivalent visible DRUM→BASS and CHORD→MELODY routes replace their built-in transforms instead of stacking.

