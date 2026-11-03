<a name="top"></a>

# Auricle · User guide

This reference follows the current interface. English control names are kept so you can find the same setting in the UI. Hover over a control or its caption for a short description. Help language also selects tooltip language.

- [Quickstart](#quickstart)
- [Composition](#composition)
- [Blocks](#blocks)
- [Block parameters](#parameters)
- [Generators](#generators)
- [Drum Kit](#drums)
- [CHORD / PAD · Strum](#strum)
- [Motifs](#motifs)
- [Mutators](#mutators)
- [Process Layers](#processes)
- [Relations / Dialogue](#relations)
- [Perform / Global](#performance)
- [MIDI expression](#expression)
- [MIDI Learn / Sync](#midi)
- [Monitor / Piano roll](#piano-roll)
- [Parameter automation](#parameter-automation)
- [Troubleshooting](#troubleshooting)

<a name="quickstart"></a>

## Quickstart

1. Connect a MIDI output to a receiving synth, sampler or DAW; Auricle generates MIDI, not audio.
2. Add a DRUM or pitched block. Set its channel, note/root, algorithm and density. Use header Play to audition Blocks.
3. Edit source material in Generator, then shape Structure, Timing, Musical and Mutation. Process Layers transform streams; Relations connect instruments.
4. In Composition add sections, set their bars, macro overrides and instrument Active/Density/Velocity. Start with Composition Play.
5. Save the project. Undo/Redo includes arrangement and parameter edits; Panic releases stuck notes.

| Parameter | Description |
| --- | --- |
| **BPM** | Tempo in quarter notes per minute, shared by Blocks, Composition, performance and MIDI expression. |
| **LENGTH** | Source sequence buffer length in steps; independent of section durations in bars. |
| **KEY** | Global root for scale-based material. Explicit harmonic-plan chord roots remain independent. |
| **SCALE** | Global scale for scale-based material; blocks may carry their own scale settings. |
| **SEED** | Project random seed for repeatable generation. Regenerate rebuilds material; it does not start playback. |

Units: one beat is a quarter note; the ordinary base step is 0.25 beat (a sixteenth). MIDI channels are 1–16; note/controller values are 0–127. A value of zero is a rest in rhythm/Pattern material, but can be a valid root degree in pitch generators.

<a name="composition"></a>

## Composition · form and arrangement

Composition schedules musical settings over sections on the same transport as Blocks. The form overview stays visible while SECTION, INSTRUMENTS and GLOBAL edit different scopes. Selecting a section changes the editor only. Header Play auditions Blocks without section automation or Perform; Composition Play starts the authored form.

| Parameter | Description |
| --- | --- |
| **Enable composition** | Arms the form without starting it. Composition Play enables and starts the plan. Header Play auditions Blocks. |
| **Meter** | Global form meter. A beat is a quarter note: 4/4 = 4 beats, 6/8 = 3, 7/8 = 3.5. |
| **Play composition** | Starts Composition from From, using section settings and assignments on the shared transport. |
| **Stop composition** | Stops Composition playback and releases its notes. Header Stop/Space stops playback globally. |
| **From** | Selected section starts at the section being edited; Form start begins at zero; Timeline cursor uses the stored seek position. |
| **End** | Loop form repeats the arrangement; Stop at end releases notes at its end; Hold last section continues with final settings and curve endpoints. |
| **Sections** | Select to edit; selection does not seek playback. Drag cards or use arrows to reorder the form. |
| **Timeline** | Click/drag, then release to seek with sixteenth-note snapping. During Blocks playback this only prepares the future Composition cursor. |
| **TOTAL** | Sum of section durations in bars, quarter-note beats and time at the current BPM. Header LENGTH is a source-buffer step count, not form duration. |
| **New section type** | Starter preset used when adding a new section. Types do not restrict later editing. |
| **+ Section** | Adds a section of the selected type; up to 128 sections. |
| **Duplicate** | Copies the selected section with its macros, curves, instrument settings and assignments. |
| **Move earlier** | Moves the selected section earlier in playback order. |
| **Move later** | Moves the selected section later in playback order. |
| **Remove** | Removes the selected section from the form; Undo restores the edit. |
| **Controlled parameters** | Shows which musical parameters Composition can influence. |

<a name="composition-section"></a>

### SECTION · identity and time

| Parameter | Description |
| --- | --- |
| **Name** | Name of the selected section, shown on its card and timeline. |
| **Type** | Semantic section label. Changing it alone preserves current settings; Apply type preset replaces them with starter values. |
| **Duration** | Selected section length, 1–128 bars in Composition Meter. |
| **Blend in** | Incoming macro blend in bars, clipped to section length; includes loop seam. Smoothly interpolates previous macro endpoints. Does not crossfade audio or all instrument coefficients. |
| **Color** | Display color of the section; does not affect the music. |
| **Apply type preset** | Replaces the selected section's macro and block settings with its type's starter values. |

Intro, Verse, Build, Drop, Break, Bridge, Transition and Outro supply starter settings. A single 8-bar Main section can be used as a simple loop. The section Duration and Composition Meter define its actual time; changing header LENGTH changes source material, not the form.

<a name="composition-macros"></a>

### SECTION · macros and curves

| Parameter | Description |
| --- | --- |
| **Energy** | Overall dynamic energy. In Composition affects velocity relative to the live Global baseline; 0.5 is the neutral center. |
| **Tension** | Higher tension loosens chord-tone anchoring in BASS/MELODY that follow Harmonic Plan. |
| **Density** | Global/section density shaping. Zero is not guaranteed silence; use instrument Density = 0 or Active off for silence. |
| **Variation** | Intensity of dynamic/accent variation. It is distinct from the generator's Seed. |

| Parameter | Description |
| --- | --- |
| **Override** | Off follows live Global, ignoring this section's scalar and curve. On enables this section's macro value. |
| **Value** | Section macro value, 0–100%; used when Override is on and Curve is off. |
| **Curve** | Uses the editable curve instead of the scalar value; Override must also be on. |
| **Shape** | Smooth eases segments without overshoot; Linear uses straight slopes; Step holds each value to the next point. |
| **Curve editor** | X spans the section from start to end; Y is 0–100%. Double-click adds, drag moves; right-click/Delete removes an interior point. Endpoints remain. |

Override off → follows live Global. Override on + Curve off → fixed section value. Override on + Curve on → section curve. Blend in interpolates from the preceding section's final macro values into the incoming section, including a looping seam. The first start of the form begins at its own initial values. Blend in affects macros; it neither overlaps sections nor fades every local instrument coefficient.

<a name="composition-phrase"></a>

### SECTION · Phrase

| Parameter | Description |
| --- | --- |
| **Phrase** | Multi-stage performance phrase assigned to this section; None leaves macros and coefficients active. Starts with Composition playback. |
| **Amount** | Strength of the section phrase, 0–100%. |
| **Fit to section** | Proportionally stretches phrase stages to the section length and holds the final state at its endpoint. |
| **Duration** | Phrase duration in quarter-note beats when Fit is off; after completion the phrase fades out its performance layer. |
| **Targets** | All includes current and future blocks; a selected subset restricts phrase targets. An empty subset targets none. Local Technique overrides take precedence. |

A phrase is a sequence of stages; stage previews show the assigned techniques. Fit proportionally distributes those stages over the section. With Fit off the phrase finishes after Duration and fades out its layer. A local instrument technique with Fit off behaves differently: its endpoint remains held until the section ends. Section boundaries/seek re-establish the appropriate section assignments.

<a name="composition-instruments"></a>

### INSTRUMENTS · local settings

| Parameter | Description |
| --- | --- |
| **Active** | Allows notes in this section only. A global Mute still silences the instrument. Kit card changes affect all its voices. |
| **Active** | Allows the selected block/voice to emit notes in this section. |
| **Technique** | Inherit phrase uses the section phrase assignment; None excludes this instrument from that assignment; a named technique replaces it locally. Coefficients still apply. |
| **Amount** | Strength of the explicitly selected instrument technique, 0–100%. |
| **Shape** | In eases into the change; Out changes quickly then settles; Out–in–out eases both ends; In–pulse rises and returns. |
| **Fit** | Stretches the technique over this section. Off uses Beats, then holds the technique endpoint until the section ends. |
| **Beats** | Duration of the local technique in quarter-note beats when Fit is off. |
| **Gate** | Section note-duration multiplier: 1 is neutral. |
| **Density** | Per-event keep probability: 0 silent, 1 preserves all eligible source events. Later sections can restore events from the source. |
| **Velocity** | Section velocity multiplier: 1 neutral, 0 silent, values above 1 strengthen dynamics. |
| **Register Center** | Section offset to the manual block Center in semitones: 0 follows the block, +12 raises its register by an octave. Drum Voice notes stay fixed. |
| **Variation** | Deterministic per-event velocity variation in this section; 0 disables it. |
| **Accent** | Additional section accent strength; 0 is neutral. |
| **Octave spread** | Extra octave placement variation for pitched notes; 0 is neutral. Unavailable for Drum Voices. |
| **Harmony** | Multiplier of chord-tone anchoring for BASS/MELODY following Harmonic Plan; 1 is neutral. |
| **Mode** | Global SEQ/LIVE mode of the instrument, shared across sections. |
| **Mute** | Global mute across all sections, independent of local Active. |
| **Details / Voices** | Opens detailed settings for this block and individual Drum Voices. |
| **Preview** | Preview of the assigned performance gesture; selecting a technique does not start standalone audition. |

| Parameter | Description |
| --- | --- |
| **Block / Drum Voice settings** | Opens per-block/per-voice coefficients, expression and section MIDI automation. Kit card edits apply to all its voices. |
| **MIDI override** | Off inherits Block Inspector/parent kit MIDI expression; on enables section-specific CC, pitch bend and aftertouch settings for the selected entity. |

Active and coefficients belong to the selected section; Mode and Mute are global. Card edits for DRUM fan out to all its voices; Details/Voices can differentiate individual voices. Density = 0 or Active off reliably silences that entity in the section. Register Center offsets the manual center before final scale/harmony placement; it preserves pitch classes through octave placement and does not retune fixed drum notes.

<a name="composition-global"></a>

### GLOBAL · project-wide music

Musical Director and Harmonic Plan apply across the project. They do not become section-local when another section is selected. Manual performance audition opens standalone Perform controls; it starts only from an explicit audition action. Use section Phrase/Technique assignments for a reproducible arrangement.

<a name="composition-example"></a>

### Example · an eight-bar build

Add Build, set Duration to 8 bars and Meter to 4/4 (32 quarter-note beats). Enable Energy Override + Curve, with a low start and high end. Leave Density Override off to follow Global. Keep the bass Active throughout and disable the lead in the preceding section. Assign a fitted phrase or a fitted local technique. Start from Selected section, then choose Loop form to hear the transition back. To compare the original blocks, use header Play.

<a name="blocks"></a>

## Blocks · musical roles

<a name="block-drum"></a>

### DRUM

A kit of independent Drum Voices. Each voice has its own source, processing and MIDI note/route; coordinated mode arranges role-based voices on a shared grid. Use Free for an independent voice.

<a name="block-bass"></a>

### BASS

Low-register foundation. Groove Follow/Accent can couple it to drums; Harmonic Plan can anchor it to chord tones. Register Center/Width constrain its placement.

<a name="block-melody"></a>

### MELODY

A pitched lead line with scale/register shaping and optional chord-source or Harmonic Plan anchoring. Start with modest density so the contour remains clear.

<a name="block-pad"></a>

### PAD

Sustained harmonic texture. Gate, Role Duration and Sustain control length; Chord Size/Spread/Inversion shape local voicings, or Harmonic Plan supplies explicit chords.

<a name="block-chord"></a>

### CHORD

Rhythmic chordal part. A generator supplies activity, while chord controls or Harmonic Plan determine voicing. Gate separates short stabs from connected chords.

| Parameter | Description |
| --- | --- |
| **Name** | Instrument or voice name; does not change its MIDI route. |
| **Type** | Musical role: DRUM, BASS, MELODY, PAD or CHORD; determines role shaping and available controls. |
| **Algorithm** | Source generator. Its own parameters appear in Generator; processing layers act on the resulting material. |
| **Mode · SEQ / LIVE** | SEQ repeats a generated buffer; LIVE produces events during playback. Coordinated drums share one sixteenth-note grid in both modes. |
| **Mute** | Global instrument/voice mute in every Composition section. |
| **MIDI channel** | Output channel 1–16. A Drum Voice may inherit its kit channel. |
| **MIDI note** | Base MIDI note. For a Drum Voice this selects the sound on the receiving drum instrument. |
| **Output port** | MIDI output destination; an inherited Drum Voice route follows its parent kit. |

<a name="parameters"></a>

## Block parameters · common layers

Only controls applicable to the current block/voice are shown. Some stored legacy fields may coexist; the explicit Pattern Density has priority over Role Density. Knob drag/wheel edits the manual value; double-click restores its default; the context menu contains MIDI Learn and influence controls where supported.

<a name="parameters-0"></a>

### Structure / Density

| Parameter | Description |
| --- | --- |
| **Pattern Density** | Fraction of generated events kept before later performance layers: 0 removes source events, 1 keeps all. |
| **Event Probability** | Chance of emitting an eligible event on each playback pass. |
| **Anchors** | Retention probability for structurally important anchor events. |
| **Support** | Retention probability for supporting events between anchors. |
| **Ornaments** | Retention probability for decorative events. |
| **Length** | Number of source steps used by the structure layer, within the project buffer. |
| **Rotation** | Cyclic shift of the structural pattern in steps. |
| **Role Density** | Role density fallback when no explicit Pattern Density is stored. Pattern Density takes precedence. |

<a name="parameters-1"></a>

### Timing

| Parameter | Description |
| --- | --- |
| **Rate** | Step-rate multiplier: 2 plays the ordinary grid twice as fast. Coordinated kits and active motifs use their own step grid. |
| **Swing** | Delays alternating steps, up to half a step; BPM stays unchanged. |
| **Humanize** | Random onset deviation, measured as a fraction of a step. |
| **Offset** | Signed onset shift in fractions of a step. |
| **Gate** | Note duration relative to its step. 1 fills the step; values above 1 allow overlap. |
| **Live Gate** | Additional duration setting for LIVE events; interacts with the role duration and performance layers. |
| **Live Min** | Minimum interval between free LIVE events, in quarter-note beats. |
| **Live Max** | Maximum free LIVE interval in quarter-note beats; cyclic/motif/kit grids can determine timing instead. |
| **Role Duration** | Role-level duration multiplier; combines with Gate. |
| **Pad Sustain** | Sustained-note duration factor for PAD material. |

<a name="parameters-2"></a>

### Pitch / Register / Harmony

| Parameter | Description |
| --- | --- |
| **Root** | MIDI root used by this block's scale mapping. |
| **Scale** | Scale used to map generated degrees; explicit Harmonic Plan chords have their own roots and qualities. |
| **Transpose** | Manual pitch offset in semitones; separate from Register Center. |
| **Octave** | Manual pitch offset in octaves, 12 semitones each. |
| **Pitch Range** | Pitch span used when mapping generator material into notes, in semitones. |
| **Register Center** | Center of the allowed role register, relative to the root, in semitones. Composition and Register Rise/Fall can offset this manual base. |
| **Register Width** | Width of the role register window in semitones. |
| **Root Bias** | Preference for root-oriented notes in the role shaping. |
| **Chord Size** | Number of voices for locally generated CHORD/PAD voicings. Explicit Harmonic Plan chords retain their chord tones. |
| **Chord Spread** | Spacing of chord voices in semitones. |
| **Inversion** | Moves chord voices between octaves to change the inversion. |
| **Follow Harmonic Plan** | Lets this pitched block use the active Harmonic Plan chord. DRUM notes are unchanged. |
| **Harmonic Strength** | Chord-tone anchoring for BASS/MELODY following Harmonic Plan. |
| **Voice Smooth** | Reduces large pitch/voicing jumps between consecutive harmonic events. |

<a name="parameters-3"></a>

### Role relationships

| Parameter | Description |
| --- | --- |
| **Groove Follow** | How strongly the bass rhythm follows its selected drum source. |
| **Groove Accent** | How strongly drum accents shape the bass dynamics. |
| **Groove Offset** | Signed step offset for the rhythm followed by the bass. |
| **Groove Mode** | Union combines bass and drum rhythm; Replace uses the selected drum rhythm. |
| **Drum Source** | Drum instrument/voice used for role groove following. Auto selects a suitable source. |
| **Harmony Anchor** | Strength of the melody's chord-source anchoring. |
| **Chord Source** | CHORD/PAD source used by the melody's role relationship. |

<a name="parameters-4"></a>

### Velocity / Mutation

| Parameter | Description |
| --- | --- |
| **Velocity Base** | Base note velocity on the normalized 0–1 scale, converted to MIDI 1–127 for audible notes. |
| **Velocity Range** | Dynamic span of the source velocity contour. |
| **Velocity Random** | Random variation around the current note velocity. |
| **Velocity Accent** | Extra emphasis for accented events. |
| **Pitch Mutation** | Blends pitch-mutator results with the original; 0 bypasses, 1 applies them fully. |
| **Rhythm Mutation** | Multiplies the strength of mutators targeting rhythm. |
| **Velocity Mutation** | Multiplies the strength of mutators targeting velocity. |
| **Timing Mutation** | Multiplies the strength of mutators targeting note gate/duration. |
| **Seed** | Reproducible random seed. The same settings and seed recreate the same generated material. |

<a name="generators"></a>

## Generators · every source parameter

<a name="generator-0"></a>

### Euclidean

Euclidean rhythm distributes a chosen number of hits as evenly as possible across a cycle. Use Steps, Pulses and Rotation to move the accent pattern without changing its density.

| Parameter | Description |
| --- | --- |
| **Steps** | Length of the Euclidean cycle in steps. |
| **Pulses** | Number of hits distributed across the cycle; cannot exceed its effective length. |
| **Rotation** | Cyclic shift of the Euclidean hits in steps. |

<a name="generator-1"></a>

### Bresenham

Bresenham treats rhythm as a discrete line-rasterization problem. It is useful for clean, mechanical distributions of events across a loop.

| Parameter | Description |
| --- | --- |
| **Steps** | Length of the Bresenham rhythm cycle in steps. |
| **Pulses** | Number of hits distributed by the discrete-line algorithm. |
| **Rotation** | Cyclic shift of the Bresenham rhythm. |

<a name="generator-2"></a>

### Polyrhythm

Polyrhythm combines two independent cycles. Cycle A and Cycle B can create interference patterns whose combined period is longer than either source cycle.

| Parameter | Description |
| --- | --- |
| **Cycle A** | Period of pulse train A, in steps. |
| **Cycle B** | Period of pulse train B, in steps. |
| **Phase A** | Step offset of pulse train A. |
| **Phase B** | Step offset of pulse train B. |
| **Combine** | OR keeps either train; AND keeps coincidences; XOR keeps events present in only one train. |

<a name="generator-3"></a>

### Thue-Morse

Thue-Morse generates a recursively structured binary pattern. It produces repetition with controlled self-similarity and is useful for non-obvious rhythmic symmetry.

| Parameter | Description |
| --- | --- |
| **Rotation** | Step rotation of the Thue–Morse binary sequence. |
| **Invert** | Exchanges active and inactive cells before density processing. |
| **Density** | Fraction of Thue–Morse hits retained. |
| **Seed** | Reproducible random seed. The same settings and seed recreate the same generated material. |

<a name="generator-4"></a>

### Fibonacci Rhythm

Density sets the hit count across the full 0–1 range, including silence and every step. Fibonacci Rhythm derives event placement from Fibonacci structure. Density and offset control how strongly the sequence is exposed as rhythm.

| Parameter | Description |
| --- | --- |
| **Density** | Hit density from 0 (silence) to 1 (every step), with Fibonacci-derived placement. |
| **Offset** | Shifts the Fibonacci rhythm in steps. |

<a name="generator-5"></a>

### Fibonacci

Fibonacci generates a deterministic numerical sequence that can be mapped into pitch or other musical dimensions. Use range, stride and offset to shape its musical scale.

| Parameter | Description |
| --- | --- |
| **Degree span** | Wraps numeric sequence values into this number of scale degrees. |
| **Stride** | Multiplies numeric sequence values before wrapping into the degree span. |
| **Offset** | Adds a degree offset before modulo wrapping. |
| **Reverse** | Reverses the source sequence. |

<a name="generator-6"></a>

### Recaman

Recamán generates a non-linear integer sequence with frequent directional changes. It is useful for irregular pitch contours and evolving patterns.

| Parameter | Description |
| --- | --- |
| **Degree span** | Wraps numeric sequence values into this number of scale degrees. |
| **Stride** | Multiplies numeric sequence values before wrapping into the degree span. |
| **Offset** | Adds a degree offset before modulo wrapping. |
| **Reverse** | Reverses the source sequence. |

<a name="generator-7"></a>

### De Bruijn

De Bruijn sequences visit combinations of symbols with controlled coverage. They are useful when you want systematic variation with minimal immediate repetition.

| Parameter | Description |
| --- | --- |
| **Order** | Size of binary combinations systematically visited by the sequence. |
| **Rotation** | Cyclic shift of the De Bruijn output. |
| **Mode** | Rhythm uses binary cells as hits/rests; Pitch maps the sequence into notes. |

<a name="generator-8"></a>

### Markov

Markov generates the next musical event from transition probabilities. Max Jump, Rest, Repeat, Leap and Seed control stability versus exploration.

| Parameter | Description |
| --- | --- |
| **Max Jump** | Maximum ordinary move through scale degrees. |
| **Degree offset** | Offset in scale degrees, not semitones. |
| **Octaves** | Extra octave spread of the Markov line. |
| **Rest** | Chance of a rest in the Markov sequence. |
| **Leap** | Chance of a larger pitch leap. |
| **Repeat** | Chance of repeating the previous degree. |
| **Seed** | Reproducible random seed. The same settings and seed recreate the same generated material. |

<a name="generator-9"></a>

### Random Walk

Random Walk moves through pitch or value space one bounded step at a time. Drift, return bias and range determine whether the line wanders or stays centered.

| Parameter | Description |
| --- | --- |
| **Step** | Maximum single random-walk move in semitones. |
| **Range** | Bounded pitch excursion of the walk in semitones. |
| **Start** | Initial pitch offset of the walk in semitones. |
| **Return Bias** | Pull toward the walk center. |
| **Drift** | Direction bias: negative descends, positive ascends, zero balances. |
| **Seed** | Reproducible random seed. The same settings and seed recreate the same generated material. |

<a name="generator-10"></a>

### Interval Walker

Interval Walker chooses interval-sized moves rather than absolute notes. Step, range, leap chance and return behavior shape the melodic contour.

| Parameter | Description |
| --- | --- |
| **Step** | Basic interval size for each walk move, in semitones before optional scale quantization. |
| **Return** | Bias toward returning to the center of the walk. |
| **Range** | Maximum excursion of the interval walk, in semitones. |
| **Leap** | Chance of taking a larger interval move. |
| **Quantize** | Scale snaps the walk into the selected scale; Chromatic keeps semitone motion. |
| **Seed** | Reproducible random seed. The same settings and seed recreate the same generated material. |

<a name="generator-11"></a>

### Scale Walker

Scale Walker moves through degrees of the selected scale. Direction, step size, leap probability and octave range provide controlled melodic motion.

| Parameter | Description |
| --- | --- |
| **Step** | Size of each Scale Walker move in scale degrees. |
| **Direction** | Upward probability: 0 descends, 1 ascends, 0.5 balances both directions. |
| **Octaves** | Octave range available to Scale Walker. |
| **Leap** | Chance of a larger move through the scale. |
| **Seed** | Reproducible random seed. The same settings and seed recreate the same generated material. |

<a name="generator-12"></a>

### Weighted Scale

Weighted Scale assigns different probabilities to scale degrees. It is useful for biased tonal melodies where some notes occur more often than others.

| Parameter | Description |
| --- | --- |
| **Weights** | Comma-separated nonnegative degree weights, e.g. 4,1,2,1,3,1,1. Higher values are chosen more often. |
| **Octave spread** | Chance of placing a weighted scale tone in another octave. |
| **Seed** | Reproducible random seed. The same settings and seed recreate the same generated material. |

<a name="generator-13"></a>

### Arpeggiator

Arpeggiator cycles through chord/scale tones using an order, octave range and direction. It is useful for harmonic motion and repeating ostinatos.

| Parameter | Description |
| --- | --- |
| **Pattern** | Comma-separated scale-degree indices, e.g. 0,2,4,6; zero is the root, not a rest. |
| **Octaves** | Number of octaves used by the arpeggio. |
| **Direction** | Traversal order: Up, Down or Up/Down. |
| **Octave mode** | Cycle walks through octaves; Random chooses them using Seed. |
| **Seed** | Reproducible random seed. The same settings and seed recreate the same generated material. |

<a name="generator-14"></a>

### Probability

Probability makes events stochastic according to a probability threshold. It is a direct way to turn a dense source into a sparse, evolving stream.

| Parameter | Description |
| --- | --- |
| **Probability** | Chance that a generator step contains an event. |
| **Pitch Range** | Range of randomly selected pitch offsets. |
| **Center** | Center of the random pitch distribution. |
| **Octaves** | Additional octave variation of probability-generated notes. |
| **Velocity Floor** | Minimum relative velocity of generated events. |
| **Seed** | Reproducible random seed. The same settings and seed recreate the same generated material. |

<a name="generator-15"></a>

### Pattern

Pattern plays an explicit user-defined numeric pattern. Use it when you want algorithmic processing around a known rhythmic or melodic seed.

| Parameter | Description |
| --- | --- |
| **Pattern** | Comma-separated rhythm amplitudes: 1,0,0.5,0. Zero is a rest; nonzero values set event strength. |
| **Rotation** | Cyclic shift of the explicit pattern in steps. |
| **Scale** | Multiplies the explicit pattern amplitudes. |
| **Probability** | Generator-level chance of retaining each pattern hit. |
| **Reverse** | Reverses the explicit pattern before rotation. |
| **Step chance** | Per-step playback chance, evaluated again each pass after processing. Follows pattern reverse/rotation; All 100% resets every step. |

<a name="generator-16"></a>

### Cellular Automaton

Cellular Automaton evolves a binary tape through local elementary rules. Choose a boundary mode and output either the final row, the full evolution trail or an XOR summary. Pitch mode treats inactive cells as rests.

| Parameter | Description |
| --- | --- |
| **Rule** | Elementary cellular-automaton rule number, 0–255. |
| **Generations** | Number of rule iterations applied to Seed cells. |
| **Density** | Retention density for active automaton cells. |
| **Mode** | Rhythm emits hits; Pitch maps active cells into notes and keeps inactive cells as rests. |
| **Seed cells** | Initial binary row such as 00100000; separate from the numeric random Seed. |
| **Boundary** | Wrap joins the edges; Fixed uses inactive outside cells; Mirror reflects the edges. |
| **Evolution** | Final Row outputs the last generation; Evolution Trail concatenates generations; XOR Trail combines changes. |
| **Seed** | Reproducible random seed. The same settings and seed recreate the same generated material. |

<a name="generator-17"></a>

### L-System

L-System expands an axiom through rewriting rules. In Turtle modes, + and - move the pitch degree, while [ and ] save and restore a branch position.

| Parameter | Description |
| --- | --- |
| **Axiom** | Starting symbol string for L-System rewriting. |
| **Rule A** | Replacement text for every A on each iteration. |
| **Rule B** | Replacement text for every B on each iteration. |
| **Iterations** | Number of rewriting passes; long expansions are bounded by the generator. |
| **Mode** | Pitch/Rhythm map symbols directly. Turtle modes use +/− for direction and brackets to save/restore branch positions. |
| **Pitch map** | Comma-separated degree values assigned to generated symbols. |

<a name="generator-18"></a>

### Logistic Chaos

Logistic Chaos uses the logistic map to create deterministic but highly sensitive trajectories. Chaos R, initial state and smoothing control the degree of instability.

| Parameter | Description |
| --- | --- |
| **R** | Logistic-map coefficient; values near 4 create more chaotic trajectories. |
| **X** | Initial state of the logistic map, between 0 and 1. |
| **Octaves** | Pitch span of the chaos mapping in octaves. |
| **Burn-in** | Iterations discarded before the audible sequence starts. |
| **Smooth** | Smooths abrupt changes between mapped values. |
| **Quantize** | Scale maps chaos into the selected scale; Chromatic keeps semitone choices. |

<a name="generator-19"></a>

### Turing Machine

A finite binary tape is processed by a small state machine. Busy Beaver, Alternator and Growth use different transition rules; Marbles emits events when moving particles collide. Tape, density and edge wrapping shape the result.

| Parameter | Description |
| --- | --- |
| **Machine** | State-machine rules: Busy Beaver, Alternator, Growth or the seeded Marbles variant. |
| **Mode** | Interprets the resulting tape as rhythm or pitch. |
| **Tape** | Initial binary tape, e.g. 00010000. |
| **Density** | Retention density of the machine output. |
| **Wrap tape** | Wrap joins the tape ends; off reflects the head at the boundary. |
| **Seed** | Reproducible random seed. The same settings and seed recreate the same generated material. |

<a name="generator-20"></a>

### Orbital Sequence

Two independent periodic orbits meet on the same step grid. Cycle lengths and phase offsets create long interference patterns; A, B, OR, AND, XOR and Interlock choose how the orbits interact.

| Parameter | Description |
| --- | --- |
| **Cycle A** | Period of orbital pulse train A, in steps. |
| **Cycle B** | Period of orbital pulse train B, in steps. |
| **Phase A** | Signed phase offset of orbit A in steps. |
| **Phase B** | Signed phase offset of orbit B in steps. |
| **Combine** | A/B select one orbit; OR/AND/XOR combine hits; Interlock avoids coincident hits. |
| **Output** | Maps orbital activity into rhythm or pitch. |
| **Rotation** | Cyclic step shift after combining the orbits. |

<a name="generator-21"></a>

### Geometry Collision

Particles bounce inside a box, triangle, hexagon or circle. Quantized boundary collisions become rhythm triggers or scale-degree notes. Particle count, speed and simulation substeps control density and complexity.

| Parameter | Description |
| --- | --- |
| **Shape** | Collision boundary: Box, Triangle, Hexagon or Circle. |
| **Mode** | Collisions become rhythmic events or pitch material. |
| **Particles** | Number of simulated moving particles. |
| **Speed** | Particle speed multiplier; greater speed generally produces more collisions. |
| **Substeps** | Simulation resolution per musical step; higher values cost more computation. |
| **Seed** | Reproducible random seed. The same settings and seed recreate the same generated material. |

<a name="drums"></a>

## Drum Kit

| Parameter | Description |
| --- | --- |
| **Kit Density** | Overall event retention for the drum kit. |
| **Kit Swing** | Offbeat delay on the shared kit grid, up to half a step. |
| **Kit Humanize** | Adds small onset and velocity deviations: up to 10% of a step and 15% velocity at maximum. |
| **Kit Fill** | Fill activity near the end of the source/kit phrase. |
| **Coordinated Kit** | Gives non-Free voices a shared sixteenth-note plan in SEQ and LIVE. |
| **Style** | Straight, Half-time or Broken arrangement of the role grid. |
| **Kit Meter** | Meter of the kit phrase; independent of Composition and Harmonic Plan meters. |
| **Phrase bars** | Length of one coordinated kit phrase, in kit-meter bars. |
| **Keep beat** | Restores core rhythmic anchors after processing. Disable to allow more radical rhythmic displacement. |
| **New variant** | Reproducible variant number for a different coordinated drum plan. |
| **Complexity** | Adds detail to the coordinated drum plan; in Metric / Barlow it increases secondary-role activity. |
| **Syncopation · PS** | Metric / Barlow: probability 0–1 of anticipating a pulse by one sixteenth; Fragment limits consecutive anticipations. Other engines shift added hits towards offbeats. |
| **Tom activity** | Activity of tom-role voices in coordinated phrases and fills. |
| **Variation** | Phrase-to-phrase changes of the coordinated pattern. |
| **Voice role** | Kick/Snare/Hat/Clap/Tom/Perc coordinate by role; Free keeps an independent generator. Auto roles uses names then GM notes. |
| **Engine** | Role grid uses the classic role plan; Rhythm map interpolates groove skeletons; Metric / Barlow derives event probabilities from the meter hierarchy. |
| **Density R** | Metric / Barlow: 0–1 controls weight ranges at each metric stratum. Zero keeps a sparse metric skeleton; Master Density zero silences the kit. |
| **Strength M** | Metric / Barlow: 1 follows metric weights, 0 gives uniform probabilities while preserving their expected event count before coordination. Lower M shuffles accent placement. |
| **Fragment** | Metric / Barlow: 1–8 sixteenth-note pulses, the maximum consecutive anticipations. Every event moves by one pulse, not by the fragment length; a capped run resolves at the next metric group. |
| **Straight → Broken** | Horizontal Rhythm map coordinate: straight at the left, broken at the right. |
| **Pocket → Driving** | Vertical Rhythm map coordinate: pocket at the bottom, driving at the top. |
| **Motif change** | Strength of changes between Theme, Variation, Answer, Fill and Return. |
| **Motif development** | Enables repeatable kit phrase development: Theme → variants → Return. |
| **Return every** | Return to the original theme after this many kit phrases. |
| **Voice links** | Enables internal rhythmic relationships between drum voices; links read the same frozen candidate plan. |
| **Voice links editor** | Source/destination identify voices. OR supports, AND intersects, XOR separates; answer, complement, copy, gap fill, interlock and accent shape the destination. |

<a name="drum-metric"></a>

### Metric / Barlow

An independent adaptation of Sioros & Guedes, Automatic Rhythmic Performance in Max/MSP: the kin.rhythmicator (NIME 2011, pp. 88–91). No Max patch or runtime is required. Select Metric / Barlow in the rhythm engine; Settings replaces the groove map with R, M, Fragment and a probability preview. Syncopation in the common kit row is PS.

The meter is factored into ordered strata, then Barlow indispensability ranks determine pulse weights. 3/4 uses 3×2×2, 6/8 uses 2×3×2; their twelve sixteenths therefore have different accents. Additive 7/8 is an Auricle extension: a 3×3×2 parent is shortened to the 2+2+3 grouping while preserving rank order.

At stratum i the weights span R^i…R^(i−1). Event probability is p=n·W^M, with n=ΣW/Σ(W^M). M=0 gives uniform probabilities with the same expected event count, including when R=0. Velocity uses a fixed reference profile independent of R; reducing M shuffles its accent distribution. The preview shows this metric model before roles, anticipation, links, fills and output thinning, so it is not an exact note-count display.

Auricle orchestrates this model by role: kick owns the downbeat, snare/clap emphasize the backbeat, hats are denser and tom activity follows Toms. Complexity raises secondary activity. Half-time moves the principal snare accent to the bar midpoint; Broken changes percussion placement. Free voices remain independent. Master Density, voice probabilities and processing still shape the audible result.

PS anticipates a pulse by exactly one sixteenth, carrying its probability and accent. Fragment caps consecutive anticipations; after the cap the next metric group resolves normally. A shorter run may suppress the immediately following stress. Collisions merge into one hit, and the first pulse of every bar remains a resolution point. This boundary rule is an Auricle adaptation that prevents notes escaping into the previous section or loop. PS=1 therefore cannot rotate the whole bar. Keep beat protects the resulting plan rather than recreating an anticipated source beat.

Motifs, Development, Return, Composition cadences, voice links and shared fills also apply to Metric. Variation zero repeats stochastic choices in Theme/Return; optional Motifs can still develop the phrase. Replay, seeking and New variant remain deterministic. R and M use 0–1 automation; Fragment uses integer 1–8 sixteenths. MIDI Learn and the normal parameter-influence highlight work on all three controls.

<a name="drum-articulation"></a>

### Drum Voice · Ratchet + Flam

| Parameter | Description |
| --- | --- |
| **Ratchet chance** | 0–1 chance of subdividing an accepted Drum Voice hit. Zero bypasses Ratchet. Source rests and source probability are evaluated before articulation. |
| **Ratchet count** | Integer 1–8 principal hits, including the original hit. Flam can add one grace before the first principal. |
| **Ratchet spread** | 0.1–1 of the source interval occupied by the repeat grid. One spreads repeats evenly across that interval; smaller values make a tighter cluster. |
| **Ratchet decay** | 0–1 velocity multiplier for each subsequent principal hit. One keeps dynamics equal; zero silences later repeats. |
| **Flam chance** | 0–1 chance of a quiet grace at the source onset, followed by the principal after Gap. Only the first ratchet principal gets a grace. Zero bypasses Flam. |
| **Flam gap · beats** | 0.01–0.12 quarter-note beats; 0.04 is 20 ms at 120 BPM. Clamped to 45% of a repeat subdivision so it cannot cross the next hit. The principal is delayed after the grace in both SEQ and LIVE. |
| **Flam grace velocity** | 0.05–1 multiplier of the source velocity for the grace. The principal retains the source velocity. |

Select a Drum Voice and open DRUM ARTICULATION in its Block Inspector. Settings belong to that voice. Both Chance knobs default to zero, preserving existing projects. Ratchet and Flam act after voice/kit processing, source probability and Composition gates, in SEQ, LIVE, Perform and every Coordinated Kit engine, including Metric / Barlow. They use the fixed voice MIDI note and route.

Ratchet Count includes the first principal. With Flam, the grace sounds on the original onset and the principal follows after Gap: this causal rule works identically in SEQ and LIVE without looking ahead. Only that first principal receives a grace, so a source hit produces at most nine notes. Gaps, onsets and gates follow musical time across BPM edits; short gates prevent repeat overlap.

All seven knobs support MIDI Learn, parameter-influence dots and Composition Set/Add/Multiply automation in their native ranges. Source/Plan grids remain the accepted trigger pattern; MIDI Monitor and piano-roll history receive the actual emitted sub-hits. An articulation snapshots its settings at the source hit; new values shape the next hit. Ratchet Chance zero also cancels outstanding repeats. Stop, Panic, Mute, seek, routing/mode changes and Composition section/loop boundaries cannot leak old queued notes; late worker ticks discard overdue repeats instead of catching up with a burst.

<a name="drum-links"></a>

### Internal voice links

| Parameter | Description |
| --- | --- |
| **Enabled** | Enables this individual voice link. |
| **Source** | Voice whose candidate rhythm is read. |
| **Destination** | Voice whose rhythm or accents are modified. |
| **Operation** | How source events support, suppress, answer or accent the destination. |
| **Influence** | Strength of this link, independent of Chance. |
| **Chance** | Probability of evaluating the link at each eligible slot. |
| **Delay** | Causal delay in sixteenth-note slots: the destination responds later. |
| **Phase** | Signed cyclic shift in sixteenth-note slots; separate from causal Delay. |

Delay is causal time; Phase is cyclic placement. Links read a frozen candidate plan, so cycles remain deterministic and anchors/fills remain protected. A musical kit preset enables Rhythm map, motifs and suggested links while preserving generators, processing and MIDI routes. Auto roles infers names/GM notes without changing routes. Copy/Paste sound preserves voice identity, role, mode, mute and routing; Undo paste restores the previous sound.

Plan shows the coordinated candidate plan; Output shows accepted generator output, not incoming MIDI feedback; Source shows generator material. Length edits source steps (up to 128); paging shows up to 32 steps at once.

<a name="strum"></a>

## CHORD / PAD · Strum

| Parameter | Description |
| --- | --- |
| **Strum chance** | CHORD/PAD: 0–1 probability of strumming an accepted chord; zero preserves simultaneous notes. Probability is drawn once for the whole chord. |
| **Strum gap · beats** | Requested spacing between notes, 0–0.5 quarter-note beats. 0.04 is 20 ms at 120 BPM. Wide strums compress to fit the source interval, gate and harmonic cutoff. |
| **Strum dynamics** | −1…+1 velocity slope in playing order: negative fades, positive grows, zero preserves source velocity before Humanize. Notes remain within MIDI velocity limits. |
| **Strum humanize** | 0–1 repeatable variation of gaps and velocity. Timing varies by at most 20% of a subdivision, velocity by 10%; note order and event boundaries stay protected. |
| **Strum direction** | Up/Down follow actual MIDI pitch after voicing. Alternate changes direction on source steps, including rests; Random shuffles existing tones deterministically. |
| **Strum gate** | Shared end releases all tones at the original chord end. Per note gives each tone its full source duration. Both respect harmonic, Dialogue and transport boundaries. |

STRUM in the CHORD/PAD Block Inspector plays the finished voicing one note at a time. It runs after source probability, register/voicing, Dialogue and Composition processing, and uses the existing musical event scheduler in SEQ, LIVE, Perform and Composition. Chance defaults to zero, so existing projects retain their simultaneous chord output. Single-note events are unchanged.

Up and Down sort actual MIDI pitches after inversion, spread and voice leading. Alternate uses the absolute source-step parity; rests advance that parity too, so seeking needs no playback history. Random, chance and Humanize are reproducible for the same seed, block and source beat. Strum preserves chord tones and removes duplicate physical MIDI notes caused by clipping.

Gap is a requested interval in quarter-note beats, not milliseconds. A strum occupies at most 90% of the available source interval/gate or the remaining harmony/Dialogue window; wider settings compress automatically. Humanize keeps notes ordered. Shared end shortens later notes to the original chord deadline, even after a late worker tick or BPM change. Per note retains each note's source duration, allowing legato overlap as configured by Gate. Harmonic cutoffs still take precedence.

The four knobs support MIDI Learn and continuous Composition automation in native ranges. Direction and Gate support discrete Composition assignments through their context menu; source dots show active influences and the selectors show the effective choice without editing the manual value. Settings and voicing are captured once per accepted chord; later edits affect the next chord. Stop, Panic, Mute, seek, routing/mode/type changes and Composition section/loop changes cancel old pending tones. MIDI Monitor and piano-roll history receive individual emitted notes; source/plan buffers remain unchanged.

<a name="motifs"></a>

## Motifs

| Parameter | Description |
| --- | --- |
| **Motif** | Phrase auto follows an assigned phrase motif; Off uses the generator; a named motif selects saved role material. |
| **Step beats** | Motif step duration in quarter-note beats; coordinated drums keep their shared 0.25-beat step. |
| **Development** | Transformation used to develop the saved motif across cycles. |
| **Amount** | Strength of motif development. |
| **Every** | Number of motif cycles between development changes. |
| **Return** | Number of developed variants before returning to the theme. |
| **Hold** | Holds the current developed motif instead of advancing its variation. |
| **Capture** | Saves the source preview before mutators, relations and macros as a reusable motif. |
| **Save variant** | Saves the currently developed material as a separate motif. |
| **Recall** | Restores a selected motif-development history state. |

<a name="mutators"></a>

## Mutators

| Parameter | Description |
| --- | --- |
| **Type** | Transformation applied in stack order; available types depend on the target. |
| **Target** | Rhythm = hit/rest; Pitch = semitone offsets; Velocity = dynamics; Timing = gate/duration, not onset displacement. |
| **Amount** | Operation amount; the target's Mutation control blends the result with the original. Neutral values depend on the selected type. |

| Parameter | Description |
| --- | --- |
| **Rotate** | Cyclic left shift by Amount × stream length; 1 is a full turn. |
| **Reverse** | Reverses the stream when Amount is above zero. |
| **Invert** | Reflects values within the target dimension when Amount is above zero. |
| **Transpose** | Pitch shift: round((Amount − 0.5) × 24) semitones; 0.5 is neutral. |
| **Stretch** | Repeats values with an integer factor from 1 to 4. |
| **Compress** | Subsamples the stream with an integer factor from 1 to 4. |
| **Probability** | Keeps values with probability Amount: 1 keeps all, 0 removes them. |
| **Mutate** | Randomly changes values with intensity Amount in the selected dimension. |
| **Shuffle** | Randomly reorders material according to Amount. |
| **Mirror** | Forms a reflected continuation of the source stream. |
| **Humanize** | Adds small value deviations. For Timing it changes gate, not onset; use Timing Humanize for onset jitter. |
| **Octave** | Pitch shift: round((Amount − 0.5) × 4) octaves; 0.5 is neutral. |
| **Threshold** | Removes values below Amount × target maximum. |
| **Scale** | Multiplies values by 0.25 + 1.5 × Amount; 0.5 is neutral. |

Stack order matters. Target-specific Mutation blends the transformed result with the original, preserving the operation's neutral point. Compatibility limits the menu: Transpose/Octave operate on pitch; Threshold on velocity/timing; Probability on rhythm/velocity/timing. Timing mutators transform gate, whereas Timing Humanize/Offset move note onsets.

<a name="processes"></a>

## Process Layers

Processes read/transform musical streams after generation and mutators; they are not audio effects. Delay values are source steps, not milliseconds. Clock primitives reshape the stream and do not change BPM. Reorder the stack to change the result.

| Parameter | Description |
| --- | --- |
| **Type** | Stream-processing primitive; processes run in stack order after generation and mutators. |
| **Target** | Musical stream being read or transformed: rhythm, pitch, velocity, duration, density or accent. |
| **Amount** | Overall process amount; Depth/Mix parameters can define the actual blend for the selected primitive. |

<a name="process-0"></a>

### Counter

Adds a repeating ramp, triangle or sine control signal. Good for cyclic sweeps of pitch, density or velocity.

| Parameter | Description |
| --- | --- |
| **Length** | Counter waveform period in source steps. |
| **Step** | Counter ramp slope/amplitude multiplier; a negative value reverses its direction. |
| **Offset** | Shifts the counter/modulo signal before it is applied. |
| **Center** | Signal reference level; in Modulo Gate this is the replacement for rejected values. |
| **Phase** | Step offset within the generated waveform or clock mask. |
| **Reset** | Counter restarts its position after this many source steps; separate from waveform Length. |
| **Depth** | Strength of the generated signal or parameter-modulation route, 0–1. |
| **Waveform** | Counter shape: Ramp, Triangle or Sine. |

<a name="process-1"></a>

### Modulo

Creates a repeating modular control pattern. Use Add, Multiply or Gate modes to impose periodic structure.

| Parameter | Description |
| --- | --- |
| **Modulus** | Number of steps in the repeating modulo ramp. |
| **Offset** | Shifts the counter/modulo signal before it is applied. |
| **Scale** | Signed amplitude multiplier of the modulo ramp. |
| **Center** | Signal reference level; in Modulo Gate this is the replacement for rejected values. |
| **Threshold** | Comparison level; the selected operator/mode determines which values pass. |
| **Depth** | Strength of the generated signal or parameter-modulation route, 0–1. |
| **Mode** | Add adds the ramp; Multiply scales the input; Gate keeps values above Threshold and substitutes Center elsewhere. |

<a name="process-2"></a>

### Compare

Compares each value with a threshold and blends between true and false values. Useful for gates, accents and conditional transformations.

| Parameter | Description |
| --- | --- |
| **Threshold** | Comparison level; the selected operator/mode determines which values pass. |
| **True value** | Output value when the comparison succeeds. |
| **False value** | Output value when the comparison fails. |
| **Equality tolerance** | Tolerance used by the == comparison; does not add a latched hysteresis state. |
| **Mix** | Blend between original and processed stream: 0 original, 1 processed; some Replace/Gate modes bypass this blend. |
| **Operator** | Numeric comparison: >=, >, <, <= or ==. |
| **Invert** | Exchanges true and false results of Compare. |

<a name="process-3"></a>

### Clock Divide

Slows a stream by periodically gating or holding events. Useful for creating slower envelopes and rhythmic subdivisions.

| Parameter | Description |
| --- | --- |
| **Factor** | Clock-pattern factor in source steps; transforms the stream without changing project BPM. |
| **Phase** | Step offset within the generated waveform or clock mask. |
| **Duty** | Active fraction of each clock-mask cycle, 0–1. |
| **Mode** | Gate zeros inactive mask positions; Hold repeats the preceding output. The mask period is 2 × Factor steps. |

<a name="process-4"></a>

### Clock Multiply

Repeats or gates a source according to a clock factor. Each source value is repeated for Factor steps; project BPM is unchanged.

| Parameter | Description |
| --- | --- |
| **Factor** | Clock-pattern factor in source steps; transforms the stream without changing project BPM. |
| **Phase** | Step offset within the generated waveform or clock mask. |
| **Duty** | Active fraction of each clock-mask cycle, 0–1. |
| **Mode** | Repeats each source value for Factor steps. Gate additionally applies Duty; Hold keeps the repeated values. BPM is unchanged. |

<a name="process-5"></a>

### Memory

Reads a previous value and blends it with the current value. Delay and feedback create persistence and smoothing.

| Parameter | Description |
| --- | --- |
| **Delay** | Distance to an earlier stream value, in source steps, not milliseconds. |
| **Feedback** | Weight of earlier values in Memory/Feedback; in Delay controls successive echo contributions. |
| **Mix** | Blend between original and processed stream: 0 original, 1 processed; some Replace/Gate modes bypass this blend. |
| **Initial** | Value used before enough earlier steps exist. |
| **Mode** | Blend mixes with the original using Mix; Replace directly uses the memory blend controlled by Feedback. |

<a name="process-6"></a>

### Delay

Adds delayed copies of a stream. Repeats, feedback and decay control the resulting echo-like structure.

| Parameter | Description |
| --- | --- |
| **Delay** | Distance to an earlier stream value, in source steps, not milliseconds. |
| **Repeats** | Number of delayed contributions summed by Delay. |
| **Feedback** | Weight of earlier values in Memory/Feedback; in Delay controls successive echo contributions. |
| **Mix** | Blend between original and processed stream: 0 original, 1 processed; some Replace/Gate modes bypass this blend. |
| **Decay** | Attenuation of successive delayed/feedback contributions. |
| **Initial** | Value used before enough earlier steps exist. |
| **Mode** | Echo mixes original and delayed values; Replace emits delayed values; Gate keeps the original only when the delayed sum is positive. |

<a name="process-7"></a>

### Feedback

Feeds processed output back through the process for iterative evolution. Keep feedback bounded when using pitch or velocity.

| Parameter | Description |
| --- | --- |
| **Feedback** | Weight of earlier values in Memory/Feedback; in Delay controls successive echo contributions. |
| **Iterations** | Number of Feedback smoothing passes over the stream. |
| **Decay** | Attenuation of successive delayed/feedback contributions. |
| **Mix** | Blend between original and processed stream: 0 original, 1 processed; some Replace/Gate modes bypass this blend. |
| **Bias** | Offset added to the preceding Feedback output before blending. |
| **Clamp** | Symmetric Feedback output limit; 0 disables this additional limit. |
| **Initial** | Value used before enough earlier steps exist. |

<a name="process-8"></a>

### Parameter Modulation

Reads a musical stream as a control signal for a real numeric parameter. Modulation is applied with an event delay to avoid same-pass recursive feedback.

| Parameter | Description |
| --- | --- |
| **Destination** | Block receiving Parameter Modulation; (none) leaves the route unconnected. |
| **Parameter** | Numeric parameter on the destination block receiving the mapped source stream. |
| **Source min** | Input value mapped to the destination minimum. |
| **Source max** | Input value mapped to the destination maximum. |
| **Minimum** | Destination value at Source min; bounded by the destination parameter's range. |
| **Maximum** | Destination value at Source max; bounded by the destination parameter's range. |
| **Smoothing** | Smooths parameter-modulation changes; higher values react more gradually. |
| **Depth** | Strength of the generated signal or parameter-modulation route, 0–1. |

<a name="relations"></a>

## Relations / Dialogue

| Parameter | Description |
| --- | --- |
| **Source** | Block whose selected output stream is read. |
| **Destination** | Block receiving this relationship. |
| **Output** | Source stream: rhythm, pitch, velocity, duration, density or accent. |
| **Input** | Destination stream modified by the relationship. |
| **Operation** | Copy replaces, Mix blends, Quantize To aligns, Modulate changes values, Follow follows contour, Trigger gates events, Dialogue alternates instruments. |
| **Amount** | Influence strength, shaped by Curve. In Dialogue this is Separation: 0 bypasses, 1 strictly alternates. |
| **Curve** | Shapes Amount: Linear, Exponential, Logarithmic, Threshold or four-step Quantize. |
| **Delay** | Source-event delay (0, 1, 2, 4 or 8 events), not seconds. Cyclic feedback is evaluated with causal history. |
| **Chance** | Chance of applying the route. Dialogue evaluates chance once per whole call/response cycle. |
| **Enabled** | Bypasses or enables this relationship without deleting it. |

<a name="dialogue"></a>

### Dialogue · call and response

| Parameter | Description |
| --- | --- |
| **Meter** | Bar size for call/response durations; independent of Composition meter. |
| **Call** | Length of the source instrument's turn in dialogue-meter bars. |
| **Response** | Length of the destination instrument's turn in dialogue-meter bars. |
| **Gap** | Silence in quarter-note beats after each turn, including the loop boundary. |
| **Reply** | Own phrase keeps the reply material; Echo follows call contour/accents; Contrast inverts them. Reply rhythm stays its own. CHORD/PAD/DRUM follow accents only. |
| **Follow** | Strength of call contour/accent influence on the reply; 0 preserves its own material. |

Cycle = Call + Gap + Response + Gap. Separation 1 enforces alternating turns; 0 bypasses separation. Cycle chance is tested once per whole cycle. Dialogue requires distinct instrument owners; a Drum Voice belongs to its kit. If an instrument appears in multiple Dialogue pairs, the earlier pair wins. Ordinary Relations use explicit streams, and cyclic graphs use delayed history rather than recursive same-pass updates.

<a name="performance"></a>

## Perform / Global

| Parameter | Description |
| --- | --- |
| **Technique** | Musical gesture for this block; selection alone does not start playback. Enable/Restart auditions it. |
| **Amount** | Strength of the auditioned performance gesture, 0–100%. |
| **Shape** | Easing of the gesture: In, Out, Out–in–out or In–pulse. |
| **Beats** | Duration of the gesture in quarter-note beats. |
| **Phrase** | Multi-stage musical phrase for the selected target blocks. Play Phrase explicitly starts it. |
| **Duration** | Phrase length in quarter-note beats; all stages stretch proportionally. |
| **Targets** | Blocks included in this manual phrase audition. |

| Parameter | Description |
| --- | --- |
| **Macro value** | Manual macro value from 0 to 1, mapped to each assigned route. |
| **Target block** | Block receiving this user macro route. |
| **Parameter** | Numeric block parameter controlled by the route. |
| **Minimum** | Destination parameter value at macro 0. |
| **Maximum** | Destination parameter value at macro 1. |
| **Amount** | Strength of this user macro route. |
| **Curve** | Exponent shaping the route: 1 linear; larger values delay the rise; smaller values emphasize the start. |

| Parameter | Description |
| --- | --- |
| **Phrase Curve** | Tension trajectory for the Musical Director; Custom preserves a loaded trajectory. |
| **Smoothing** | Smoothness of Director state changes; higher settings react more gradually. |
| **Energy Influence** | Strength of the Director's influence on dynamic energy. |
| **Density Influence** | Strength of the Director's influence on event density. |
| **Register Influence** | Strength of the Director's influence on the pitch register. |
| **Probability Influence** | Strength of the Director's influence on event probability. |
| **Voice Smooth** | Smoothness of harmonic voice leading; shared with the engine's voice-leading solver. |

| Parameter | Description |
| --- | --- |
| **Follow plan** | CHORD/PAD use plan chords; BASS/MELODY anchor to their tones according to Follow/Strength. DRUM is unaffected. |
| **Meter** | Bar size for harmonic durations, independent of Composition and Kit meters. |
| **Loop** | Repeats the harmonic plan; off holds the final chord after the plan ends. |
| **Preset** | Selects a starter chord progression; Use preset replaces the chord list and enables the plan. |
| **Root** | Chord root pitch class, independent of the header KEY/SCALE. |
| **Quality** | Chord type and its tones; seventh chords retain four notes. |
| **Duration** | Chord duration, 1–64 bars of the Harmonic Plan meter. |

<a name="influence"></a>

### Parameter influence and knob feedback

| Parameter | Description |
| --- | --- |
| **Policy** | Priority resolves sources in order; Blend combines enabled source weights; Manual keeps the manual value. |
| **Priority** | Highest priority is first; partial weights allow lower-priority layers through. |
| **Manual** | Weight of the manual base value, 0–1. |
| **Macro** | Weight of global/section macro influence, 0–1. |
| **Technique** | Weight of performance techniques, 0–1. |
| **Modulation** | Weight of modulation routes, 0–1; multiple routes in the category are averaged. |
| **Composition weight** | Weight of section parameter automation in this parameter policy. Default priority puts Composition first; 0 bypasses it. |

The manual base remains available while Perform, Composition or Relations contribute. Source dots distinguish assigned and active influences. The needle may display the effective parameter or an output-equivalent value; the short outer tick retains the manual setting. An output-equivalent indication summarizes event-level shaping rather than rewriting every block parameter.

<a name="techniques"></a>

### Common techniques

| Technique | Action | Parameters |
| --- | --- | --- |
| **Crescendo** | Gradually increases dynamics. | `velocity_base`, `fill_density` |
| **Diminuendo** | Gradually reduces dynamics. | `velocity_base`, `fill_density` |
| **Sforzando** | A short accent followed by a return to the previous dynamic. | `velocity_accent` |
| **Accelerando** | Gradually accelerates the motion. | `timing_rate` |
| **Ritardando** | Gradually slows the motion. | `timing_rate` |
| **Stringendo** | Accelerates while increasing tension. | `timing_rate`, `velocity_base` |
| **Smorzando** | Fades and settles toward rest. | `velocity_base`, `fill_density`, `timing_rate` |
| **Staccato** | Short, detached events. | `gate` |
| **Tenuto** | Sustains notes for a more connected articulation. | `gate` |
| **Rubato** | Gentle timing fluctuation without a permanent tempo shift. | `timing_humanize`, `timing_swing` |
| **Register Rise** | Raises Register Center from its manual setting, preserving scale and harmonic pitch classes. | `role_center` |
| **Register Fall** | Lowers Register Center from its manual setting, preserving scale and harmonic pitch classes. | `role_center` |
| **Density Swell** | Gradually increases event density. | `fill_density`, `event_probability` |
| **Density Drop** | Rapidly opens space by reducing density. | `fill_density`, `event_probability` |
| **Accent Build** | Builds accents without necessarily raising average loudness. | `velocity_accent` |
| **Dynamic Scatter** | Adds velocity variation around the current dynamic in SEQ and LIVE. | `velocity_random` |
| **Register Bloom** | Widens the allowed role register without moving its center. | `role_width` |
| **Harmonic Resolve** | Gradually anchors BASS/MELODY to chord tones when following Harmonic Plan. | `harmonic_strength` |
| **Kit Evolution** | Builds fills, syncopation, tom activity and pattern variation on the shared kit grid. | `kit_fill`, `kit_syncopation`, `kit_tom_activity`, `kit_variation` |

<a name="algorithm-techniques"></a>

### Algorithm techniques

These gestures automate the listed generator parameters. Amount, shape and duration control how far and how quickly the listed values change. Their parameter descriptions are in the generator reference above.

| Algorithm / Technique | Parameter movement |
| --- | --- |
| Euclidean / **Euclidean Fill** | `pulses`: 2 → 12 |
| Euclidean / **Euclidean Rotate** | `euclidean_rotation`: 0 → 7 |
| Bresenham / **Bresenham Fill** | `bres_pulses`: 2 → 12 |
| Bresenham / **Bresenham Rotate** | `bres_rotation`: 0 → 7 |
| Polyrhythm / **Polyrhythm Unison** | `poly_a`: 3 → 4; `poly_b`: 5 → 4 |
| Polyrhythm / **Polyrhythm Spread** | `poly_a`: 3 → 7; `poly_b`: 4 → 9 |
| Thue-Morse / **Thue–Morse Density** | `tm_density`: 0.3 → 1 |
| Thue-Morse / **Thue–Morse Rotate** | `tm_rotation`: 0 → 7 |
| Fibonacci Rhythm / **Fibonacci Rise** | `fib_density`: 0.2 → 1 |
| Fibonacci Rhythm / **Fibonacci Fade** | `fib_density`: 1 → 0.12 |
| Fibonacci / **Fibonacci Register** | `sequence_mod`: 4 → 12; `sequence_stride`: 1 → 3 |
| Recaman / **Recamán Widen** | `sequence_mod`: 4 → 14; `sequence_stride`: 1 → 3 |
| De Bruijn / **De Bruijn Rotate** | `debruijn_rotation`: 0 → 15 |
| De Bruijn / **De Bruijn Expansion** | `debruijn_order`: 2 → 4 |
| Markov / **Markov Unstable** | `markov_leap`: 0.04 → 0.45; `markov_stay`: 0.2 → 0.02 |
| Markov / **Markov Settle** | `markov_leap`: 0.4 → 0.03; `markov_stay`: 0.02 → 0.45 |
| Random Walk / **Walk Drift** | `walk_drift`: 0 → 0.8 |
| Random Walk / **Walk Return** | `walk_return_bias`: 0 → 0.85 |
| Interval Walker / **Interval Leaps** | `interval_leap`: 0.02 → 0.5 |
| Interval Walker / **Interval Tame** | `interval_leap`: 0.45 → 0.02; `interval_return`: 0.1 → 0.65 |
| Scale Walker / **Scale Climb** | `scale_direction`: 0.5 → 1; `scale_leap`: 0.05 → 0.2 |
| Scale Walker / **Scale Wander** | `scale_direction`: 0.5 → 0.5; `scale_leap`: 0.02 → 0.35 |
| Weighted Scale / **Weighted Open** | `scale_octave_spread`: 0.05 → 0.8 |
| Arpeggiator / **Arpeggio Expand** | `arp_octaves`: 1 → 4 |
| Probability / **Probability Open** | `probability`: 0.2 → 1 |
| Probability / **Probability Close** | `probability`: 1 → 0.08 |
| Pattern / **Pattern Bloom** | `pattern_scale`: 0.5 → 1.5; `pattern_probability`: 0.5 → 1 |
| Pattern / **Pattern Rotate** | `pattern_rotation`: 0 → 7 |
| Cellular Automaton / **Cellular Birth** | `ca_density`: 0.2 → 1 |
| L-System / **L-System Growth** | `ls_iterations`: 1 → 6 |
| Logistic Chaos / **Chaos Heat** | `chaos_r`: 3.4 → 3.98; `chaos_smooth`: 0.5 → 0 |
| Logistic Chaos / **Chaos Cool** | `chaos_r`: 3.98 → 3.2; `chaos_smooth`: 0 → 0.8 |

<a name="phrases"></a>

### Phrase catalog

| Phrase | Stages |
| --- | --- |
| **Opening Bloom** | Crescendo (4 b) → Density Swell (4 b) → Register Rise (4 b) |
| **Tension Rise** | Stringendo (4 b) → Accent Build (4 b) → Register Rise (4 b) |
| **Climax → Release** | Crescendo (4 b) → Sforzando (1 b) → Ritardando (4 b) → Diminuendo (6 b) |
| **Breath** | Expand (4 b) → Hold (2 b) → Rubato (4 b) → Release (6 b) |
| **Accelerando → Release** | Accelerando (6 b) → Density (4 b) → Ritardando (6 b) |

<a name="expression"></a>

## MIDI Expression · CC / Pitch Bend / Aftertouch

These are outgoing MIDI controls sampled from the shared musical clock, independent of note generation. A receiving instrument must support the messages. Block expression may be inherited by Drum Voices; Composition can override it per section and entity. Curves use normalized coordinates; their actual scale is set by the lane.

| Parameter | Description |
| --- | --- |
| **CC lanes** | Up to 16 distinct CC lanes. Values use the shared Musical Clock; choose a row to edit its curve below. |
| **Enable** | Enables this expression lane without changing note generation. |
| **CC** | MIDI controller number, 0–119; use a distinct number for each lane. |
| **Min** | Minimum outgoing controller value, 0–127. |
| **Max** | Maximum outgoing controller value, 0–127. |
| **Period** | Curve cycle length in quarter-note beats for Loop. Section timebase stretches the curve over the entire section and ignores Period. |
| **Rate** | Minimum interval between expression samples, in beats. Smaller values send more frequent MIDI updates. |
| **Phase** | Loop curve phase offset in quarter-note beats; Section timebase uses section progress. |
| **Timebase** | Loop repeats every Period on the shared beat clock. Section traverses the full curve once over the current section; Period is ignored. |
| **Shape** | Linear, Smooth or Step interpolation between curve points. |
| **Points** | Normalized x:y pairs, e.g. 0:0,0.5:1,1:0; edit text or drag the curve. Up to 64 points. |
| **Bend Range** | Expected pitch-bend range in semitones, 1–24. The receiving instrument must use the same range for matching pitch. |
| **Bend Points** | Normalized bend: 0 fully down, 0.5 center, 1 fully up. X spans Period. |
| **Aftertouch Mode** | Channel pressure affects the channel; Polyphonic pressure addresses active note pitches. Receiver support is required. |
| **Sensitivity** | Pressure gain: 0 sends zero, 1 normal, 2 doubles the curve level, clipped to 127. |
| **Aftertouch Points** | Normalized pressure: 0 none, 1 maximum. X spans Period. |

<a name="midi"></a>

## MIDI Learn / Sync

| Parameter | Description |
| --- | --- |
| **Input port** | Connect the hardware MIDI input before learning. Select its port so incoming messages can reach the mapping. |
| **Learn** | Starts capture for a block parameter or Global macro. Move the hardware control; after capture, subsequent messages change the parameter. |
| **Enabled** | Enables this stored MIDI mapping. |
| **Pickup** | For absolute CC controls, waits until the hardware crosses the manual value to avoid a jump. Note-velocity learning disables pickup by default. |
| **Minimum** | Parameter value mapped to the input minimum; must fit the destination range. |
| **Maximum** | Parameter value mapped to the input maximum; can reverse the control direction with a lower endpoint. |
| **Cancel Learn** | Cancels pending capture without removing saved mappings. |
| **Remove** | Removes the selected mapping. Clear removes all mappings. |

Open MIDI IN, connect the input, then use a supported knob's context menu → MIDI Learn. CC, note velocity, pitch wheel, channel pressure and polyphonic pressure can be learned. Up to 512 mappings are stored in the project. Learning captures a mapping; subsequent movement applies it. The application does not automatically decode every relative encoder protocol.

| Parameter | Description |
| --- | --- |
| **Send MIDI Clock** | Sends 24 MIDI clock pulses per quarter note at the project tempo. |
| **Transport messages** | Sends MIDI Start, Stop and Continue alongside clock according to transport actions. |
| **Song Position Pointer** | Sends the musical position on seek using MIDI Song Position Pointer. |
| **Output** | Sends synchronization to all active outputs or the selected output port. |

<a name="piano-roll"></a>

## Monitor / Piano roll

The horizontal scale uses Length (steps), independent of the source pattern. During playback the right edge is the current time; old events leave the fixed window. When stopped or frozen the time anchor holds. At 120 BPM, 16 steps span 2 seconds; 64 steps span 8 seconds. Without MIDI history the generated preview uses the same fixed length and clips steps outside it. Selecting a Drum Voice monitors that voice; selecting the kit combines its voices.

| Parameter | Description |
| --- | --- |
| **Emitted notes** | Piano roll reads successful MIDI Note On/Off with worker timestamps, actual pitch, velocity, durations and timing shifts. Ratchet is purple, Flam grace is amber and Strum is teal. Hover notes for precise onset, length and source offset. With no MIDI port, accepted generated notes are labelled separately. Before playback, buffer/articulation preview does not predict future Composition, Dialogue or random gates. |
| **Length (steps)** | Fixed visible length, 1–4096 sixteenth-note steps. One step is 0.25 quarter-note beat. Changes the view only, independently of pattern length. Sparse LIVE notes never expand the time scale. Remembered across blocks and application restarts. |
| **FREEZE** | Hold emitted-note history, articulation colors, note endings, time anchor and tempo scale. Length remains adjustable. Uncheck to resume current history; Stop also holds the time anchor. |

During playback the roll shows dispatched notes, not source triggers: every emitted Ratchet repeat, the causal Flam grace/principal pair and each shifted Strum tone. Bar widths follow actual MIDI Note Off, including retrigger, choke, Mute and Stop; held notes grow only to the current view anchor. Onset and release times are captured before the GUI queue. The grid follows quarter-note beats across tempo changes; the seconds caption is the equivalent span at the current tempo. Hover a note for pitch, velocity, onset, length, channel and source offset. Canceled and skipped sub-hits are absent. MIDI Monitor may remain off.

Without a physical MIDI port the roll labels accepted generated notes separately and uses their planned gates. Before the first playback it previews the current buffers through the same Ratchet/Flam/Strum expansion; this preview cannot predict later section changes, Dialogue or random gates. Source buffers remain unchanged. Freeze preserves an immutable snapshot, including sounding tails and the musical anchor, through Inspector rebuilds. Play/seek starts a fresh unfrozen capture; a frozen snapshot remains until released. History is bounded to 8192 notes per owner and 32768 total.

<a name="parameter-automation"></a>

## Composition · parameter automation

AUTOMATION edits exact block/voice parameters for the selected section. Right-click a knob or source caption and choose Automate in Composition. The action creates or opens a lane, preserves the manual base and leaves playback unchanged. Composition Play applies lanes; Blocks/Perform playback and stopped editing do not. Green source dots show assigned and contributing Composition layers.

| Parameter | Description |
| --- | --- |
| **Add parameter** | Choose an instrument/voice and a parameter. Existing assignments in the selected section are opened without duplication. Assigning never starts playback. |
| **Parameter family** | Filter assignments or destinations by Ratchet, Flam or Strum. Drum articulations target individual voices or single Drum/Percussion blocks; Strum targets CHORD/PAD. Filtering preserves all lanes. |
| **Energy / Tension source** | Read the effective section macro, including its section curve and Blend transition. The response curve maps input 0–100% to the parameter's output range. No implicit articulation links are added. |
| **Reverse input** | Evaluate the response at 1 minus the macro value. The graph and Input % show this reversed input; the output range keeps its own units. |
| **Remove lane** | Remove the selected lane; its manual base and remaining influences are restored. Undo restores the assignment. |
| **Destination** | A block or individual Drum Voice and its exact parameter. Generator-specific lanes wait until their generator is active; missing targets remain visible for repair or Undo. |
| **Filter** | Search assigned lanes by instrument, caption or parameter key. The instrument selector narrows the list without altering assignments. |
| **Automation lanes** | One direct assignment per parameter and section. Filled green means contributing; an outline means assigned or bypassed. This page edits the selected section, while playback can be in another. |
| **Value / Section curve / Macro response** | Value holds a target. Section curve follows section time; Macro response maps effective Energy/Tension through a separate response curve. Choices/text use Value. |
| **Set / Add / Multiply** | Set supplies an absolute target. Add and Multiply derive a target from the latest authored manual base, never from the previous automated result; they do not accumulate. |
| **Apply timing** | Auto chooses musical timing for the parameter. Continuous follows beats; 1/16, Beat, Bar, Source cycle and Section start hold values between boundaries. Structural values cannot be continuous. Editing a held lane waits for the next boundary; seek reconstructs the destination immediately. |
| **Automation weight** | 0 bypasses this lane; 1 requests full Composition weight. The shared per-parameter policy still decides the actual contribution. Nonzero choice/text weights enable discrete priority selection. |
| **Target value** | Exact value in the parameter's own units. Ranges and integer/boolean types are enforced. Existing sounding notes keep their scheduled endings. |
| **Parameter curve** | Double-click adds a point; drag moves it; Delete/right-click removes an interior point. Endpoints stay at 0/100%. Section curve uses section progress; Macro response uses macro input (after Reverse). Linear, Smooth and Step interpolate output values. |
| **Curve range** | The graph and point fields share the selected parameter limits and units. Length follows the current project buffer; Density uses 0–1. Add uses deltas; Multiply uses dimensionless factors. Valid subranges are preserved; fixed limits are locked. |
| **Exact point** | Edit X in quarter-note beats (Section curve) or input percent (Macro response), and Y in parameter units. Integer parameters snap values to whole numbers; Multiply keeps fractional factors. Snap 1/16 aligns dragged time to 0.25 beat in every meter. |
| **Full parameter range** | Restore the selected parameter's current full range without removing curve points. Length follows the project buffer. |
| **Ramp / Flat** | Ramp sets the endpoints to the curve range minimum/maximum. Flat holds the selected point value across the section. |
| **Shared influence policy** | Composition, Technique, Modulation/Relations and Macro resolve through the same parameter policy: Priority, Weighted blend or Manual only. Direct parameter automation and final note-stream processing are separate stages. |

Default priority is Composition → Technique → Modulation → Macro; partial weights reveal lower layers. Old source orders are preserved below the new Composition category. Numeric targets clamp and round after resolution. Choices/text always use stable source priority, including in blend mode. Continuous SEQ generation is batched to sixteenth-note boundaries; source-cycle timing captures the manual cycle at section entry. Stop/bypass removes automation and reveals the latest manual base. Section entry, looping and seek evaluate musical position without replaying earlier UI edits.

Ratchet/Flam can target individual Drum Voices or single Drum/Percussion blocks; Strum targets CHORD/PAD. Use the family filter to find them. Each section stores its own Value, Section curve or Macro response assignment. Strum Direction/Gate are Value snapshots at musical boundaries. Numeric output uses native units: Ratchet Count is 1–8 hits, Flam Gap is 0.01–0.12 beats, Strum Spacing is 0–0.5 beats and Strum Dynamics is −1…+1. These controls affect future accepted events without rebuilding source patterns or resetting LIVE phase; scheduled hits keep their existing settings.

Energy/Tension links are explicit: choose Macro response and its Source, or right-click an articulation control and choose Composition: link Energy/Tension. The input is the effective section macro, including section macro curves and Blend transitions. X is input 0–100%; Y is the selected target range. Reverse input evaluates 1−input. Set writes the mapped target; Add/Multiply apply an offset/factor to the latest manual base, then clamp and round. Weight and Parameter influences use the existing Composition policy and green highlights. Held timing samples the macro only at the selected boundary. Stop, disabled lanes and section changes release the layer. Section and response curves are stored separately, so switching modes preserves both.

<a name="troubleshooting"></a>

## Troubleshooting

- No sound: check receiving instrument, MIDI output/channel/note, global Mute, section Active and Density, event probability, Dialogue turn and velocity. MIDI Monitor confirms outgoing messages.
- A section does not affect playback: start with Composition Play; confirm Enable composition and the desired From position. Selecting a section alone does not seek.
- A macro slider seems ignored: check Override, Curve, live Global and influence policy. A curve replaces the scalar slider while enabled.
- A learned control moves late: with Pickup enabled, cross the manual setting once. MIDI IN Diagnostics / Copy diagnostics shows input, GUI, pickup, queued and applied stages.
- Unexpected pitch: check semitone Transpose versus degree offset, Register Center, scale and Harmonic Plan. Drum Voice note selection remains separate.
- Stuck notes: use Panic/Stop and inspect the receiver's sustain state. For sluggish UI, turn off unnecessary monitor traffic and reduce expensive Geometry Substeps or oversized processing stacks.

[Back to contents](#top)
