"""One source of truth for the Markdown reference and contextual tooltips.

Keys are model keys, not translated captions. Keep descriptions about musical
behaviour here; Qt binding and document rendering live in separate modules.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    label: str
    en: str
    ru: str

    def text(self, language="ru"):
        return self.ru if language == "ru" else self.en


CATALOG = {}


def _add(scope, rows):
    entries = CATALOG.setdefault(scope, {})
    for line in rows.strip().splitlines():
        key, label, en, ru = (s.strip() for s in line.split("|"))
        if key in entries:
            raise ValueError(f"Duplicate help key: {scope}.{key}")
        entries[key] = Entry(label, en, ru)


_add("automation", """
add | Add parameter | Choose an instrument/voice and a parameter. Existing assignments in the selected section are opened without duplication. Assigning never starts playback. | Выберите инструмент/голос и параметр. Существующее назначение в выбранной секции откроется без дублирования. Назначение не запускает воспроизведение.
family | Parameter family | Filter assignments or destinations by Ratchet, Flam or Strum. Drum articulations target individual voices or single Drum/Percussion blocks; Strum targets CHORD/PAD. Filtering preserves all lanes. | Фильтр назначений и целей по Ratchet, Flam или Strum. Барабанные артикуляции назначаются отдельным голосам либо одиночным Drum/Percussion; Strum — CHORD/PAD. Фильтр сохраняет все дорожки.
macro_source | Energy / Tension source | Read the effective section macro, including its section curve and Blend transition. The response curve maps input 0–100% to the parameter's output range. No implicit articulation links are added. | Использует действующий макрос секции с её кривой и переходом Blend. Кривая отклика преобразует вход 0–100% в выходной диапазон параметра. Неявных связей с артикуляциями нет.
reverse | Reverse input | Evaluate the response at 1 minus the macro value. The graph and Input % show this reversed input; the output range keeps its own units. | Вычисляет отклик при входе 1 минус значение макроса. График и Input % показывают этот обращённый вход; выход сохраняет единицы параметра.
remove | Remove lane | Remove the selected lane; its manual base and remaining influences are restored. Undo restores the assignment. | Удаляет выбранную дорожку; восстанавливаются ручная основа и остальные влияния. Undo возвращает назначение.
destination | Destination | A block or individual Drum Voice and its exact parameter. Generator-specific lanes wait until their generator is active; missing targets remain visible for repair or Undo. | Блок или отдельный Drum Voice и точный параметр. Дорожки конкретного генератора ждут его включения; отсутствующие цели остаются видны для восстановления или Undo.
filter | Filter | Search assigned lanes by instrument, caption or parameter key. The instrument selector narrows the list without altering assignments. | Поиск назначенных дорожек по инструменту, подписи или ключу параметра. Выбор инструмента фильтрует список и не изменяет назначения.
tracks | Automation lanes | One direct assignment per parameter and section. Filled green means contributing; an outline means assigned or bypassed. This page edits the selected section, while playback can be in another. | Одно прямое назначение на параметр и секцию. Залитая зелёная точка означает влияние; контур — назначение или обход. Редактируется выбранная секция, воспроизведение может идти в другой.
mode | Value / Section curve / Macro response | Value holds a target. Section curve follows section time; Macro response maps effective Energy/Tension through a separate response curve. Choices/text use Value. | Value удерживает цель. Section curve следует времени секции; Macro response преобразует действующий Energy/Tension отдельной кривой отклика. Списки и текст используют Value.
operation | Set / Add / Multiply | Set supplies an absolute target. Add and Multiply derive a target from the latest authored manual base, never from the previous automated result; they do not accumulate. | Set задаёт абсолютную цель. Add и Multiply рассчитывают цель от последней ручной основы, а не предыдущего автоматического результата; накопления нет.
timing | Apply timing | Auto chooses musical timing for the parameter. Continuous follows beats; 1/16, Beat, Bar, Source cycle and Section start hold values between boundaries. Structural values cannot be continuous. Editing a held lane waits for the next boundary; seek reconstructs the destination immediately. | Auto выбирает музыкальную привязку для параметра. Continuous следует долям; 1/16, Beat, Bar, Source cycle и Section start удерживают значение между границами. Структурные значения не меняются непрерывно. Правка удерживаемой дорожки ждёт следующей границы; перемотка сразу восстанавливает значение позиции.
weight | Automation weight | 0 bypasses this lane; 1 requests full Composition weight. The shared per-parameter policy still decides the actual contribution. Nonzero choice/text weights enable discrete priority selection. | 0 обходит дорожку; 1 запрашивает полный вес Composition. Фактический вклад определяет общая политика параметра. Ненулевой вес списков/текста включает дискретный выбор по приоритету.
value | Target value | Exact value in the parameter's own units. Ranges and integer/boolean types are enforced. Existing sounding notes keep their scheduled endings. | Точное значение в единицах параметра. Диапазоны и целочисленные/логические типы соблюдаются. Уже звучащие ноты сохраняют назначенное окончание.
curve | Parameter curve | Double-click adds a point; drag moves it; Delete/right-click removes an interior point. Endpoints stay at 0/100%. Section curve uses section progress; Macro response uses macro input (after Reverse). Linear, Smooth and Step interpolate output values. | Двойной щелчок добавляет точку; перетаскивание перемещает; Delete/правый щелчок удаляет внутреннюю точку. Концы закреплены на 0/100%. Section curve использует время секции; Macro response — вход макроса после Reverse. Linear, Smooth и Step задают интерполяцию.
range | Curve range | The graph and point fields share the selected parameter limits and units. Length follows the current project buffer; Density uses 0–1. Add uses deltas; Multiply uses dimensionless factors. Valid subranges are preserved; fixed limits are locked. | График и поля точек используют общий диапазон и единицы параметра. Length ограничен текущей длиной проекта, Density — 0–1. Add задаёт прибавку, Multiply — безразмерный множитель. Допустимый поддиапазон сохраняется; фиксированные границы заблокированы.
point | Exact point | Edit X in quarter-note beats (Section curve) or input percent (Macro response), and Y in parameter units. Integer parameters snap values to whole numbers; Multiply keeps fractional factors. Snap 1/16 aligns dragged time to 0.25 beat in every meter. | X задаётся четвертными долями в Section curve или процентами входа в Macro response; Y — в единицах параметра. Для целых параметров значения округляются до целых; Multiply допускает дробные множители. Snap 1/16 привязывает время перетаскивания к 0.25 доли при любом размере.
full_range | Full parameter range | Restore the selected parameter's current full range without removing curve points. Length follows the project buffer. | Восстановить полный текущий диапазон параметра без удаления точек кривой. Предел Length зависит от длины проекта.
ramp | Ramp / Flat | Ramp sets the endpoints to the curve range minimum/maximum. Flat holds the selected point value across the section. | Ramp задаёт концам минимум и максимум диапазона кривой. Flat удерживает значение выбранной точки всю секцию.
influences | Shared influence policy | Composition, Technique, Modulation/Relations and Macro resolve through the same parameter policy: Priority, Weighted blend or Manual only. Direct parameter automation and final note-stream processing are separate stages. | Composition, Technique, Modulation/Relations и Macro используют общую политику параметра: Priority, Weighted blend или Manual only. Прямая автоматизация параметра и финальная обработка потока нот — разные стадии.
""")


_add("piano_roll", """
events | Emitted notes | Piano roll reads successful MIDI Note On/Off with worker timestamps, actual pitch, velocity, durations and timing shifts. Ratchet is purple, Flam grace is amber and Strum is teal. Hover notes for precise onset, length and source offset. With no MIDI port, accepted generated notes are labelled separately. Before playback, buffer/articulation preview does not predict future Composition, Dialogue or random gates. | Piano roll получает успешные MIDI Note On/Off со временем рабочего потока, фактической высотой, velocity, длительностью и сдвигами. Ratchet — фиолетовый, предудар Flam — янтарный, Strum — бирюзовый. Наведение показывает точное начало, длину и сдвиг относительно источника. Без MIDI-порта принятые события генератора обозначены отдельно. Превью буфера/артикуляций до запуска не прогнозирует будущие Composition, Dialogue и случайные фильтры.
length | Length (steps) | Fixed visible length, 1–4096 sixteenth-note steps. One step is 0.25 quarter-note beat. Changes the view only, independently of pattern length. Sparse LIVE notes never expand the time scale. Remembered across blocks and application restarts. | Фиксированная длина видимого окна: 1–4096 шестнадцатых шагов. Один шаг — 0.25 четвертной доли. Меняет только отображение независимо от длины паттерна. Редкие ноты LIVE не растягивают масштаб. Значение сохраняется при переключении блоков и перезапуске программы.
freeze | FREEZE | Hold emitted-note history, articulation colors, note endings, time anchor and tempo scale. Length remains adjustable. Uncheck to resume current history; Stop also holds the time anchor. | Фиксирует историю выданных нот, цвета артикуляций, окончания, положение времени и масштаб темпа. Length остаётся доступным. Снимите галочку для просмотра текущей истории; Stop также останавливает движение временного окна.
""")


_add("identity", """
name | Name | Instrument or voice name; does not change its MIDI route. | Имя инструмента или голоса; не меняет MIDI-маршрут.
block_type | Type | Musical role: DRUM, BASS, MELODY, PAD or CHORD; determines role shaping and available controls. | Музыкальная роль: DRUM, BASS, MELODY, PAD или CHORD. Определяет обработку партии и доступные настройки.
algorithm | Algorithm | Source generator. Its own parameters appear in Generator; processing layers act on the resulting material. | Исходный генератор. Его настройки находятся в Generator; следующие слои обрабатывают полученный материал.
mode | Mode · SEQ / LIVE | SEQ repeats a generated buffer; LIVE produces events during playback. Coordinated drums share one sixteenth-note grid in both modes. | SEQ повторяет сгенерированный буфер; LIVE создаёт события при воспроизведении. Согласованные ударные в обоих режимах используют общую сетку шестнадцатых.
muted | Mute | Global instrument/voice mute in every Composition section. | Глобальное отключение инструмента или голоса во всех секциях Composition.
midi_channel | MIDI channel | Output channel 1–16. A Drum Voice may inherit its kit channel. | Выходной канал 1–16. Drum Voice может наследовать канал набора.
midi_note | MIDI note | Base MIDI note. For a Drum Voice this selects the sound on the receiving drum instrument. | Базовая MIDI-нота. У Drum Voice выбирает звук на принимающем драм-инструменте.
output_port | Output port | MIDI output destination; an inherited Drum Voice route follows its parent kit. | MIDI-выход. Наследуемый маршрут Drum Voice следует выходу родительского набора.
""")
_add("block", """
fill_density | Pattern Density | Fraction of generated events kept before later performance layers: 0 removes source events, 1 keeps all. | Доля сохраняемых событий генератора до последующих исполнительских слоёв: 0 убирает исходные события, 1 сохраняет все.
event_probability | Event Probability | Chance of emitting an eligible event on each playback pass. | Вероятность воспроизведения допустимого события при каждом проходе.
anchor_strength | Anchors | Retention probability for structurally important anchor events. | Вероятность сохранения опорных, структурно важных событий.
support_probability | Support | Retention probability for supporting events between anchors. | Вероятность сохранения поддерживающих событий между опорами.
ornament_probability | Ornaments | Retention probability for decorative events. | Вероятность сохранения декоративных событий.
structure_length | Length | Number of source steps used by the structure layer, within the project buffer. | Число исходных шагов, используемых слоем Structure в пределах буфера проекта.
structure_rotation | Rotation | Cyclic shift of the structural pattern in steps. | Циклический сдвиг структурного рисунка в шагах.
timing_rate | Rate | Step-rate multiplier: 2 plays the ordinary grid twice as fast. Coordinated kits and active motifs use their own step grid. | Множитель скорости шагов: 2 удваивает скорость обычной сетки. Согласованный Kit и активный мотив используют собственный шаг.
timing_swing | Swing | Delays alternating steps, up to half a step; BPM stays unchanged. | Задерживает чередующиеся шаги до половины шага; BPM не меняется.
timing_humanize | Humanize | Random onset deviation, measured as a fraction of a step. | Случайное отклонение начала события, в долях шага.
timing_offset | Offset | Signed onset shift in fractions of a step. | Сдвиг начала события в долях шага; знак задаёт направление.
gate | Gate | Note duration relative to its step. 1 fills the step; values above 1 allow overlap. | Длительность ноты относительно шага. 1 заполняет шаг; значения выше 1 допускают перекрытие.
live_gate | Live Gate | Additional duration setting for LIVE events; interacts with the role duration and performance layers. | Настройка длительности LIVE-событий; взаимодействует с длительностью роли и исполнительскими слоями.
live_min_beats | Live Min | Minimum interval between free LIVE events, in quarter-note beats. | Минимальный интервал между свободными LIVE-событиями в четвертных долях.
live_max_beats | Live Max | Maximum free LIVE interval in quarter-note beats; cyclic/motif/kit grids can determine timing instead. | Максимальный свободный LIVE-интервал в четвертных долях. Циклическая сетка, мотив или Kit могут задавать время отдельно.
scale_root | Root | MIDI root used by this block's scale mapping. | Корневая MIDI-нота для отображения материала в гамму этого блока.
scale_name | Scale | Scale used to map generated degrees; explicit Harmonic Plan chords have their own roots and qualities. | Гамма для отображения ступеней генератора. Явные аккорды Harmonic Plan имеют собственные тоники и типы.
transpose | Transpose | Manual pitch offset in semitones; separate from Register Center. | Ручное смещение высоты в полутонах; независимо от Register Center.
octave | Octave | Manual pitch offset in octaves, 12 semitones each. | Ручное смещение в октавах, по 12 полутонов.
pitch_range | Pitch Range | Pitch span used when mapping generator material into notes, in semitones. | Диапазон отображения материала генератора в ноты, в полутонах.
role_center | Register Center | Center of the allowed role register, relative to the root, in semitones. Composition and Register Rise/Fall can offset this manual base. | Центр допустимого регистра роли относительно корня, в полутонах. Composition и Register Rise/Fall могут смещать эту ручную основу.
role_width | Register Width | Width of the role register window in semitones. | Ширина регистрового окна роли в полутонах.
role_density | Role Density | Role density fallback when no explicit Pattern Density is stored. Pattern Density takes precedence. | Запасная плотность роли, если Pattern Density не задана явно. Явная Pattern Density имеет приоритет.
role_duration | Role Duration | Role-level duration multiplier; combines with Gate. | Множитель длительности на уровне роли; сочетается с Gate.
role_root_bias | Root Bias | Preference for root-oriented notes in the role shaping. | Предпочтение опорных нот, связанных с корнем, при обработке роли.
pad_sustain | Pad Sustain | Sustained-note duration factor for PAD material. | Коэффициент длительности протяжённых нот PAD.
harmony_size | Chord Size | Number of voices for locally generated CHORD/PAD voicings. Explicit Harmonic Plan chords retain their chord tones. | Число голосов локального аккорда CHORD/PAD. Явные аккорды Harmonic Plan сохраняют свои аккордовые тоны.
harmony_spread | Chord Spread | Spacing of chord voices in semitones. | Разнос голосов аккорда в полутонах.
harmony_inversion | Inversion | Moves chord voices between octaves to change the inversion. | Переносит голоса аккорда между октавами для изменения обращения.
groove_follow | Groove Follow | How strongly the bass rhythm follows its selected drum source. | Насколько сильно басовый ритм следует выбранному источнику ударных.
groove_accent | Groove Accent | How strongly drum accents shape the bass dynamics. | Насколько акценты ударных влияют на динамику баса.
groove_offset | Groove Offset | Signed step offset for the rhythm followed by the bass. | Сдвиг в шагах для ритма, которому следует бас.
groove_mode | Groove Mode | Union combines bass and drum rhythm; Replace uses the selected drum rhythm. | Union объединяет ритм баса и ударных; Replace использует ритм выбранного ударного источника.
relation_drum_source | Drum Source | Drum instrument/voice used for role groove following. Auto selects a suitable source. | Ударный инструмент или голос для следования груву роли. Auto выбирает подходящий источник.
harmony_anchor | Harmony Anchor | Strength of the melody's chord-source anchoring. | Сила привязки мелодии к выбранному аккордовому источнику.
relation_chord_source | Chord Source | CHORD/PAD source used by the melody's role relationship. | Источник CHORD/PAD для ролевой связи мелодии.
harmonic_follow | Follow Harmonic Plan | Lets this pitched block use the active Harmonic Plan chord. DRUM notes are unchanged. | Разрешает тональному блоку следовать текущему аккорду Harmonic Plan. Ноты DRUM не меняются.
harmonic_strength | Harmonic Strength | Chord-tone anchoring for BASS/MELODY following Harmonic Plan. | Сила притяжения к аккордовым тонам у BASS/MELODY, следующих Harmonic Plan.
voice_smooth | Voice Smooth | Reduces large pitch/voicing jumps between consecutive harmonic events. | Уменьшает большие скачки высоты и голосоведения между гармоническими событиями.
velocity_base | Velocity Base | Base note velocity on the normalized 0–1 scale, converted to MIDI 1–127 for audible notes. | Базовая сила нажатия по шкале 0–1, преобразуемая в MIDI 1–127 для звучащих нот.
velocity_range | Velocity Range | Dynamic span of the source velocity contour. | Динамический диапазон исходного контура velocity.
velocity_random | Velocity Random | Random variation around the current note velocity. | Случайное отклонение от текущей силы нажатия.
velocity_accent | Velocity Accent | Extra emphasis for accented events. | Дополнительное усиление акцентированных событий.
mutation_pitch | Pitch Mutation | Blends pitch-mutator results with the original; 0 bypasses, 1 applies them fully. | Смешивает результат мутаторов высоты с оригиналом; 0 — обход, 1 — полное применение.
mutation_rhythm | Rhythm Mutation | Multiplies the strength of mutators targeting rhythm. | Множитель силы мутаторов, направленных на ритм.
mutation_velocity | Velocity Mutation | Multiplies the strength of mutators targeting velocity. | Множитель силы мутаторов, направленных на velocity.
mutation_timing | Timing Mutation | Multiplies the strength of mutators targeting note gate/duration. | Множитель силы мутаторов, направленных на gate/длительность нот.
variation_seed | Seed | Reproducible random seed. The same settings and seed recreate the same generated material. | Зерно воспроизводимой случайности. Одинаковые настройки и Seed воссоздают одинаковый исходный материал.
""")
_add("generator", """
euclidean_steps | Steps | Length of the Euclidean cycle in steps. | Длина евклидова цикла в шагах.
pulses | Pulses | Number of hits distributed across the cycle; cannot exceed its effective length. | Число ударов, распределяемых по циклу; не превышает его фактическую длину.
euclidean_rotation | Rotation | Cyclic shift of the Euclidean hits in steps. | Циклический сдвиг евклидовых ударов в шагах.
bres_steps | Steps | Length of the Bresenham rhythm cycle in steps. | Длина ритмического цикла Брезенхэма в шагах.
bres_pulses | Pulses | Number of hits distributed by the discrete-line algorithm. | Число ударов, распределяемых алгоритмом дискретной линии.
bres_rotation | Rotation | Cyclic shift of the Bresenham rhythm. | Циклический сдвиг ритма Брезенхэма.
poly_a | Cycle A | Period of pulse train A, in steps. | Период цепочки импульсов A в шагах.
poly_b | Cycle B | Period of pulse train B, in steps. | Период цепочки импульсов B в шагах.
poly_phase_a | Phase A | Step offset of pulse train A. | Сдвиг цепочки импульсов A в шагах.
poly_phase_b | Phase B | Step offset of pulse train B. | Сдвиг цепочки импульсов B в шагах.
poly_mode | Combine | OR keeps either train; AND keeps coincidences; XOR keeps events present in only one train. | OR оставляет события любой цепочки; AND — совпадения; XOR — события только одной из цепочек.
tm_rotation | Rotation | Step rotation of the Thue–Morse binary sequence. | Сдвиг двоичной последовательности Туэ—Морса в шагах.
tm_invert | Invert | Exchanges active and inactive cells before density processing. | Меняет активные и неактивные клетки местами до обработки плотности.
tm_density | Density | Fraction of Thue–Morse hits retained. | Доля сохраняемых ударов последовательности Туэ—Морса.
fib_density | Density | Hit density from 0 (silence) to 1 (every step), with Fibonacci-derived placement. | Плотность от 0 (тишина) до 1 (все шаги) с размещением по структуре Фибоначчи.
fib_offset | Offset | Shifts the Fibonacci rhythm in steps. | Сдвигает ритм Фибоначчи в шагах.
sequence_mod | Degree span | Wraps numeric sequence values into this number of scale degrees. | Сворачивает числовую последовательность в указанное число ступеней гаммы.
sequence_stride | Stride | Multiplies numeric sequence values before wrapping into the degree span. | Умножает значения последовательности до сворачивания в диапазон ступеней.
sequence_offset | Offset | Adds a degree offset before modulo wrapping. | Добавляет смещение в ступенях до операции остатка.
sequence_reverse | Reverse | Reverses the source sequence. | Разворачивает исходную последовательность.
debruijn_order | Order | Size of binary combinations systematically visited by the sequence. | Длина двоичных комбинаций, систематически перебираемых последовательностью.
debruijn_rotation | Rotation | Cyclic shift of the De Bruijn output. | Циклический сдвиг результата De Bruijn.
debruijn_mode | Mode | Rhythm uses binary cells as hits/rests; Pitch maps the sequence into notes. | Rhythm использует клетки как удары/паузы; Pitch отображает последовательность в ноты.
interval_step | Step | Basic interval size for each walk move, in semitones before optional scale quantization. | Базовый интервал перемещения в полутонах до необязательной квантизации в гамму.
interval_return | Return | Bias toward returning to the center of the walk. | Склонность возвращаться к центру блуждания.
interval_range | Range | Maximum excursion of the interval walk, in semitones. | Допустимый размах интервального блуждания в полутонах.
interval_leap | Leap | Chance of taking a larger interval move. | Вероятность увеличенного интервального скачка.
interval_quantize | Quantize | Scale snaps the walk into the selected scale; Chromatic keeps semitone motion. | Scale привязывает ход к выбранной гамме; Chromatic сохраняет хроматическое движение.
scale_step | Step | Size of each Scale Walker move in scale degrees. | Размер шага Scale Walker в ступенях гаммы.
scale_direction | Direction | Upward probability: 0 descends, 1 ascends, 0.5 balances both directions. | Вероятность движения вверх: 0 — вниз, 1 — вверх, 0.5 — баланс направлений.
scale_octaves | Octaves | Octave range available to Scale Walker. | Число октав, доступных Scale Walker.
scale_leap | Leap | Chance of a larger move through the scale. | Вероятность увеличенного скачка по гамме.
scale_weights | Weights | Comma-separated nonnegative degree weights, e.g. 4,1,2,1,3,1,1. Higher values are chosen more often. | Неотрицательные веса ступеней через запятую, например 4,1,2,1,3,1,1. Больший вес повышает частоту выбора.
scale_octave_spread | Octave spread | Chance of placing a weighted scale tone in another octave. | Вероятность переноса выбранного тона в другую октаву.
arp_pattern | Pattern | Comma-separated scale-degree indices, e.g. 0,2,4,6; zero is the root, not a rest. | Индексы ступеней через запятую, например 0,2,4,6. Ноль здесь — корень, а не пауза.
arp_octaves | Octaves | Number of octaves used by the arpeggio. | Число октав арпеджио.
arp_direction | Direction | Traversal order: Up, Down or Up/Down. | Порядок обхода: вверх, вниз или вверх/вниз.
arp_octave_mode | Octave mode | Cycle walks through octaves; Random chooses them using Seed. | Cycle перебирает октавы по порядку; Random выбирает их с учётом Seed.
ca_rule | Rule | Elementary cellular-automaton rule number, 0–255. | Номер правила элементарного клеточного автомата, 0–255.
ca_generations | Generations | Number of rule iterations applied to Seed cells. | Число итераций правила над Seed cells.
ca_density | Density | Retention density for active automaton cells. | Плотность сохранения активных клеток автомата.
ca_mode | Mode | Rhythm emits hits; Pitch maps active cells into notes and keeps inactive cells as rests. | Rhythm выдаёт удары; Pitch превращает активные клетки в ноты, неактивные — в паузы.
ca_seed | Seed cells | Initial binary row such as 00100000; separate from the numeric random Seed. | Начальная двоичная строка, например 00100000. Не совпадает с числовым зерном Seed.
ca_boundary | Boundary | Wrap joins the edges; Fixed uses inactive outside cells; Mirror reflects the edges. | Wrap соединяет края; Fixed считает внешние клетки неактивными; Mirror отражает края.
ca_evolution | Evolution | Final Row outputs the last generation; Evolution Trail concatenates generations; XOR Trail combines changes. | Final Row выводит последнее поколение; Evolution Trail — след поколений; XOR Trail — их XOR-сводку.
ls_axiom | Axiom | Starting symbol string for L-System rewriting. | Начальная строка символов для переписывания L-System.
ls_rule_a | Rule A | Replacement text for every A on each iteration. | Строка замены каждого A на каждой итерации.
ls_rule_b | Rule B | Replacement text for every B on each iteration. | Строка замены каждого B на каждой итерации.
ls_iterations | Iterations | Number of rewriting passes; long expansions are bounded by the generator. | Число проходов переписывания; длина развёртки ограничена генератором.
ls_mode | Mode | Pitch/Rhythm map symbols directly. Turtle modes use +/− for direction and brackets to save/restore branch positions. | Pitch/Rhythm отображают символы напрямую. В Turtle знаки +/− меняют направление, скобки сохраняют/восстанавливают позицию ветви.
ls_mapping | Pitch map | Comma-separated degree values assigned to generated symbols. | Значения ступеней для символов, через запятую.
turing_preset | Machine | State-machine rules: Busy Beaver, Alternator, Growth or the seeded Marbles variant. | Правила машины состояний: Busy Beaver, Alternator, Growth или вариант Marbles с зерном.
turing_mode | Mode | Interprets the resulting tape as rhythm or pitch. | Интерпретирует итоговую ленту как ритм или высоту.
turing_tape | Tape | Initial binary tape, e.g. 00010000. | Начальная двоичная лента, например 00010000.
turing_density | Density | Retention density of the machine output. | Плотность сохраняемого результата машины.
turing_wrap | Wrap tape | Wrap joins the tape ends; off reflects the head at the boundary. | Wrap соединяет края ленты; выключено — головка отражается у границы.
orbit_cycle_a | Cycle A | Period of orbital pulse train A, in steps. | Период орбитальной цепочки A в шагах.
orbit_cycle_b | Cycle B | Period of orbital pulse train B, in steps. | Период орбитальной цепочки B в шагах.
orbit_phase_a | Phase A | Signed phase offset of orbit A in steps. | Знаковый фазовый сдвиг орбиты A в шагах.
orbit_phase_b | Phase B | Signed phase offset of orbit B in steps. | Знаковый фазовый сдвиг орбиты B в шагах.
orbit_mode | Combine | A/B select one orbit; OR/AND/XOR combine hits; Interlock avoids coincident hits. | A/B выбирают одну орбиту; OR/AND/XOR объединяют удары; Interlock разносит совпадения.
orbit_output | Output | Maps orbital activity into rhythm or pitch. | Отображает орбитальную активность в ритм или высоту.
orbit_rotation | Rotation | Cyclic step shift after combining the orbits. | Циклический сдвиг в шагах после объединения орбит.
geometry_shape | Shape | Collision boundary: Box, Triangle, Hexagon or Circle. | Граница столкновений: прямоугольник, треугольник, шестиугольник или круг.
geometry_mode | Mode | Collisions become rhythmic events or pitch material. | Столкновения превращаются в ритмические события или высотный материал.
geometry_particles | Particles | Number of simulated moving particles. | Число моделируемых движущихся частиц.
geometry_speed | Speed | Particle speed multiplier; greater speed generally produces more collisions. | Множитель скорости частиц; увеличение обычно даёт больше столкновений.
geometry_substeps | Substeps | Simulation resolution per musical step; higher values cost more computation. | Число шагов моделирования на музыкальный шаг; увеличение требует больше вычислений.
chaos_r | R | Logistic-map coefficient; values near 4 create more chaotic trajectories. | Коэффициент логистического отображения; значения около 4 дают более хаотичные траектории.
chaos_x | X | Initial state of the logistic map, between 0 and 1. | Начальное состояние логистического отображения между 0 и 1.
chaos_octaves | Octaves | Pitch span of the chaos mapping in octaves. | Высотный диапазон хаотического отображения в октавах.
chaos_burn_in | Burn-in | Iterations discarded before the audible sequence starts. | Число пропускаемых итераций до начала звучащей последовательности.
chaos_smooth | Smooth | Smooths abrupt changes between mapped values. | Сглаживает резкие изменения отображённых значений.
chaos_quantize | Quantize | Scale maps chaos into the selected scale; Chromatic keeps semitone choices. | Scale отображает хаос в выбранную гамму; Chromatic использует хроматические ноты.
markov_jump | Max Jump | Maximum ordinary move through scale degrees. | Максимальное обычное перемещение по ступеням гаммы.
markov_transpose | Degree offset | Offset in scale degrees, not semitones. | Смещение в ступенях гаммы, а не в полутонах.
markov_octaves | Octaves | Extra octave spread of the Markov line. | Дополнительный октавный разнос линии Маркова.
markov_rest | Rest | Chance of a rest in the Markov sequence. | Вероятность паузы в последовательности Маркова.
markov_leap | Leap | Chance of a larger pitch leap. | Вероятность увеличенного высотного скачка.
markov_stay | Repeat | Chance of repeating the previous degree. | Вероятность повторить предыдущую ступень.
walk_step | Step | Maximum single random-walk move in semitones. | Максимальное одиночное перемещение случайного блуждания в полутонах.
walk_range | Range | Bounded pitch excursion of the walk in semitones. | Ограниченный размах блуждания в полутонах.
walk_start | Start | Initial pitch offset of the walk in semitones. | Начальное высотное смещение блуждания в полутонах.
walk_return_bias | Return Bias | Pull toward the walk center. | Сила возвращения к центру блуждания.
walk_drift | Drift | Direction bias: negative descends, positive ascends, zero balances. | Направленный дрейф: отрицательный — вниз, положительный — вверх, 0 — баланс.
probability | Probability | Chance that a generator step contains an event. | Вероятность события на шаге генератора.
probability_pitch_range | Pitch Range | Range of randomly selected pitch offsets. | Диапазон случайно выбираемых высотных смещений.
probability_center | Center | Center of the random pitch distribution. | Центр случайного распределения высоты.
probability_octaves | Octaves | Additional octave variation of probability-generated notes. | Дополнительная октавная вариативность случайных нот.
probability_velocity_floor | Velocity Floor | Minimum relative velocity of generated events. | Минимальная относительная сила нажатия создаваемых событий.
pattern | Pattern | Comma-separated rhythm amplitudes: 1,0,0.5,0. Zero is a rest; nonzero values set event strength. | Амплитуды ритма через запятую: 1,0,0.5,0. Ноль — пауза; ненулевые значения задают силу события.
pattern_rotation | Rotation | Cyclic shift of the explicit pattern in steps. | Циклический сдвиг явного паттерна в шагах.
pattern_scale | Scale | Multiplies the explicit pattern amplitudes. | Умножает амплитуды явного паттерна.
pattern_probability | Probability | Generator-level chance of retaining each pattern hit. | Вероятность сохранения удара на уровне генератора Pattern.
pattern_reverse | Reverse | Reverses the explicit pattern before rotation. | Разворачивает явный паттерн перед сдвигом.
pattern_step_chances | Step chance | Per-step playback chance, evaluated again each pass after processing. Follows pattern reverse/rotation; All 100% resets every step. | Вероятность каждого шага при воспроизведении, заново на каждом проходе после обработки. Следует Reverse/Rotation; All 100% сбрасывает все шаги.
""")
_add("kit", """
kit_density | Kit Density | Overall event retention for the drum kit. | Общая доля сохраняемых событий набора ударных.
kit_swing | Kit Swing | Offbeat delay on the shared kit grid, up to half a step. | Задержка слабых долей общей сетки Kit до половины шага.
kit_humanize | Kit Humanize | Adds small onset and velocity deviations: up to 10% of a step and 15% velocity at maximum. | Небольшие отклонения времени и velocity: при максимуме до 10% шага и 15% velocity.
kit_fill | Kit Fill | Fill activity near the end of the source/kit phrase. | Активность сбивок ближе к концу исходного цикла или фразы Kit.
kit_coordinated | Coordinated Kit | Gives non-Free voices a shared sixteenth-note plan in SEQ and LIVE. | Даёт голосам с ролью, отличной от Free, общий план шестнадцатых в SEQ и LIVE.
kit_style | Style | Straight, Half-time or Broken arrangement of the role grid. | Прямой, половинный или ломаный рисунок ролевой сетки.
kit_meter | Kit Meter | Meter of the kit phrase; independent of Composition and Harmonic Plan meters. | Размер фразы Kit; независим от размеров Composition и Harmonic Plan.
kit_phrase_bars | Phrase bars | Length of one coordinated kit phrase, in kit-meter bars. | Длина фразы согласованного Kit в тактах его размера.
kit_protect_anchors | Keep beat | Restores core rhythmic anchors after processing. Disable to allow more radical rhythmic displacement. | Восстанавливает основные ритмические опоры после обработки. Отключите для более радикальных сдвигов.
kit_variant | New variant | Reproducible variant number for a different coordinated drum plan. | Номер воспроизводимого варианта согласованного плана ударных.
kit_complexity | Complexity | Adds detail to the coordinated drum plan; in Metric / Barlow it increases secondary-role activity. | Добавляет детали в согласованный план; в Metric / Barlow повышает активность второстепенных ударов по ролям.
kit_syncopation | Syncopation · PS | Metric / Barlow: probability 0–1 of anticipating a pulse by one sixteenth; Fragment limits consecutive anticipations. Other engines shift added hits towards offbeats. | Metric / Barlow: вероятность PS 0–1 переноса пульса на одну шестнадцатую раньше; Fragment ограничивает последовательные переносы. В остальных движках смещает дополнительные удары на слабые доли.
kit_tom_activity | Tom activity | Activity of tom-role voices in coordinated phrases and fills. | Активность томов в согласованных фразах и сбивках.
kit_variation | Variation | Phrase-to-phrase changes of the coordinated pattern. | Изменения согласованного рисунка между фразами.
kit_role | Voice role | Kick/Snare/Hat/Clap/Tom/Perc coordinate by role; Free keeps an independent generator. Auto roles uses names then GM notes. | Kick/Snare/Hat/Clap/Tom/Perc согласуются по роли; Free сохраняет независимый генератор. Auto roles учитывает имена, затем GM-ноты.
kit_engine | Engine | Role grid uses the classic role plan; Rhythm map interpolates groove skeletons; Metric / Barlow derives event probabilities from the meter hierarchy. | Role grid использует классический ролевой план; Rhythm map смешивает скелеты грува; Metric / Barlow выводит вероятности событий из метрической иерархии.
kit_metric_density | Density R | Metric / Barlow: 0–1 controls weight ranges at each metric stratum. Zero keeps a sparse metric skeleton; Master Density zero silences the kit. | Metric / Barlow: R 0–1 задаёт диапазоны весов на уровнях метрической иерархии. Ноль оставляет редкую метрическую основу; Master Density 0 полностью выключает Kit.
kit_metric_strength | Strength M | Metric / Barlow: 1 follows metric weights, 0 gives uniform probabilities while preserving their expected event count before coordination. Lower M shuffles accent placement. | Metric / Barlow: M=1 следует метрическим весам, M=0 выравнивает вероятности с сохранением ожидаемого числа событий до согласования голосов. Снижение M перемешивает расположение акцентов.
kit_metric_fragment | Fragment | Metric / Barlow: 1–8 sixteenth-note pulses, the maximum consecutive anticipations. Every event moves by one pulse, not by the fragment length; a capped run resolves at the next metric group. | Metric / Barlow: 1–8 пульсов-шестнадцатых, максимум последовательных упреждений. Каждый удар переносится на один пульс, а не на длину фрагмента; после ограничения серия разрешается на следующей метрической группе.
kit_map_x | Straight → Broken | Horizontal Rhythm map coordinate: straight at the left, broken at the right. | Горизонталь Rhythm map: слева прямой рисунок, справа ломаный.
kit_map_y | Pocket → Driving | Vertical Rhythm map coordinate: pocket at the bottom, driving at the top. | Вертикаль Rhythm map: снизу спокойный грув, сверху напористый.
kit_motif_change | Motif change | Strength of changes between Theme, Variation, Answer, Fill and Return. | Сила изменений между Theme, Variation, Answer, Fill и Return.
kit_motif_enabled | Motif development | Enables repeatable kit phrase development: Theme → variants → Return. | Включает воспроизводимое развитие фразы Kit: Theme → варианты → Return.
kit_motif_return | Return every | Return to the original theme after this many kit phrases. | Возврат к исходной теме через указанное число фраз Kit.
kit_links_enabled | Voice links | Enables internal rhythmic relationships between drum voices; links read the same frozen candidate plan. | Включает внутренние ритмические связи голосов; связи читают один зафиксированный исходный план.
kit_voice_links | Voice links editor | Source/destination identify voices. OR supports, AND intersects, XOR separates; answer, complement, copy, gap fill, interlock and accent shape the destination. | Source/Destination выбирают голоса. OR поддерживает, AND пересекает, XOR разделяет; answer, complement, copy, gap fill, interlock и accent формируют результат адресата.
""")
_add("kit_link", """
enabled | Enabled | Enables this individual voice link. | Включает эту отдельную связь голосов.
source | Source | Voice whose candidate rhythm is read. | Голос, чей исходный ритм читается.
destination | Destination | Voice whose rhythm or accents are modified. | Голос, чей ритм или акценты изменяются.
operation | Operation | How source events support, suppress, answer or accent the destination. | Способ поддержки, подавления, ответа или акцентирования событий адресата.
amount | Influence | Strength of this link, independent of Chance. | Сила связи, независимо от Chance.
probability | Chance | Probability of evaluating the link at each eligible slot. | Вероятность применения связи в каждой подходящей позиции.
delay | Delay | Causal delay in sixteenth-note slots: the destination responds later. | Причинная задержка в шестнадцатых: адресат отвечает позже.
phase | Phase | Signed cyclic shift in sixteenth-note slots; separate from causal Delay. | Циклический сдвиг со знаком в шестнадцатых; независим от причинной Delay.
""")
_add("motif", """
motif_id | Motif | Phrase auto follows an assigned phrase motif; Off uses the generator; a named motif selects saved role material. | Phrase auto следует мотиву назначенной фразы; Off использует генератор; именованный мотив выбирает сохранённый материал роли.
motif_step_beats | Step beats | Motif step duration in quarter-note beats; coordinated drums keep their shared 0.25-beat step. | Длительность шага мотива в четвертных долях; согласованные ударные сохраняют общий шаг 0.25 доли.
motif_development | Development | Transformation used to develop the saved motif across cycles. | Преобразование для развития сохранённого мотива по циклам.
motif_amount | Amount | Strength of motif development. | Сила развития мотива.
motif_every | Every | Number of motif cycles between development changes. | Число циклов мотива между изменениями развития.
motif_return | Return | Number of developed variants before returning to the theme. | Число развитых вариантов до возврата к теме.
motif_hold | Hold | Holds the current developed motif instead of advancing its variation. | Удерживает текущий развитый мотив вместо продвижения вариаций.
capture | Capture | Saves the source preview before mutators, relations and macros as a reusable motif. | Сохраняет исходное превью до мутаторов, связей и макросов как повторно используемый мотив.
save_variant | Save variant | Saves the currently developed material as a separate motif. | Сохраняет текущий развитый материал как отдельный мотив.
recall | Recall | Restores a selected motif-development history state. | Восстанавливает выбранное состояние истории развития мотива.
""")
_add("mutation", """
type | Type | Transformation applied in stack order; available types depend on the target. | Преобразование, применяемое по порядку стека; список зависит от цели.
target | Target | Rhythm = hit/rest; Pitch = semitone offsets; Velocity = dynamics; Timing = gate/duration, not onset displacement. | Rhythm — удар/пауза; Pitch — высотные смещения; Velocity — динамика; Timing — gate/длительность, а не сдвиг начала.
amount | Amount | Operation amount; the target's Mutation control blends the result with the original. Neutral values depend on the selected type. | Параметр операции; Mutation соответствующей цели смешивает результат с оригиналом. Нейтральное значение зависит от типа.
""")
_add("mutation_type", """
Rotate | Rotate | Cyclic left shift by Amount × stream length; 1 is a full turn. | Циклический сдвиг влево на Amount × длину потока; 1 — полный оборот.
Reverse | Reverse | Reverses the stream when Amount is above zero. | Разворачивает поток при Amount выше нуля.
Invert | Invert | Reflects values within the target dimension when Amount is above zero. | Отражает значения в пределах целевого измерения при Amount выше нуля.
Transpose | Transpose | Pitch shift: round((Amount − 0.5) × 24) semitones; 0.5 is neutral. | Смещение высоты: round((Amount − 0.5) × 24) полутонов; 0.5 нейтрально.
Stretch | Stretch | Repeats values with an integer factor from 1 to 4. | Растягивает повторением значений с целым коэффициентом от 1 до 4.
Compress | Compress | Subsamples the stream with an integer factor from 1 to 4. | Сжимает поток прореживанием с целым коэффициентом от 1 до 4.
Probability | Probability | Keeps values with probability Amount: 1 keeps all, 0 removes them. | Сохраняет значения с вероятностью Amount: 1 — все, 0 — ни одного.
Mutate | Mutate | Randomly changes values with intensity Amount in the selected dimension. | Случайно изменяет значения выбранного измерения с интенсивностью Amount.
Shuffle | Shuffle | Randomly reorders material according to Amount. | Случайно переставляет материал с силой Amount.
Mirror | Mirror | Forms a reflected continuation of the source stream. | Формирует отражённое продолжение исходного потока.
Humanize | Humanize | Adds small value deviations. For Timing it changes gate, not onset; use Timing Humanize for onset jitter. | Добавляет небольшие отклонения значений. Для Timing меняет gate; для сдвигов начала используйте Timing Humanize.
Octave | Octave | Pitch shift: round((Amount − 0.5) × 4) octaves; 0.5 is neutral. | Смещение высоты: round((Amount − 0.5) × 4) октав; 0.5 нейтрально.
Threshold | Threshold | Removes values below Amount × target maximum. | Убирает значения ниже Amount × максимума целевого измерения.
Scale | Scale | Multiplies values by 0.25 + 1.5 × Amount; 0.5 is neutral. | Умножает значения на 0.25 + 1.5 × Amount; 0.5 нейтрально.
""")
_add("process", """
type | Type | Stream-processing primitive; processes run in stack order after generation and mutators. | Операция над потоком; процессы выполняются по порядку после генератора и мутаторов.
target | Target | Musical stream being read or transformed: rhythm, pitch, velocity, duration, density or accent. | Читаемый или преобразуемый поток: rhythm, pitch, velocity, duration, density или accent.
amount | Amount | Overall process amount; Depth/Mix parameters can define the actual blend for the selected primitive. | Общая сила процесса; Depth/Mix могут определять фактическое смешивание выбранной операции.
depth | Depth | Strength of the generated signal or parameter-modulation route, 0–1. | Сила создаваемого сигнала или маршрута модуляции параметра, 0–1.
length | Length | Counter waveform period in source steps. | Период волны Counter в исходных шагах.
step | Step | Counter ramp slope/amplitude multiplier; a negative value reverses its direction. | Множитель наклона/амплитуды Counter; отрицательное значение меняет направление.
offset | Offset | Shifts the counter/modulo signal before it is applied. | Смещает сигнал Counter/Modulo перед применением.
center | Center | Signal reference level; in Modulo Gate this is the replacement for rejected values. | Опорный уровень сигнала; в Modulo Gate заменяет отвергнутые значения.
phase | Phase | Step offset within the generated waveform or clock mask. | Сдвиг в шагах внутри волны или маски clock.
reset | Reset | Counter restarts its position after this many source steps; separate from waveform Length. | Counter сбрасывает позицию через указанное число исходных шагов; независимо от длины волны Length.
waveform | Waveform | Counter shape: Ramp, Triangle or Sine. | Форма Counter: пила Ramp, треугольник Triangle или синус Sine.
modulus | Modulus | Number of steps in the repeating modulo ramp. | Число шагов повторяющейся пилы Modulo.
scale | Scale | Signed amplitude multiplier of the modulo ramp. | Знаковый множитель амплитуды пилы Modulo.
threshold | Threshold | Comparison level; the selected operator/mode determines which values pass. | Порог сравнения; пропускаемые значения определяются оператором или режимом.
true_value | True value | Output value when the comparison succeeds. | Выходное значение при истинном сравнении.
false_value | False value | Output value when the comparison fails. | Выходное значение при ложном сравнении.
hysteresis | Equality tolerance | Tolerance used by the == comparison; does not add a latched hysteresis state. | Допуск сравнения ==; не создаёт защёлкивающегося состояния гистерезиса.
operator | Operator | Numeric comparison: >=, >, <, <= or ==. | Числовое сравнение: >=, >, <, <= или ==.
invert | Invert | Exchanges true and false results of Compare. | Меняет местами истинный и ложный результаты Compare.
mix | Mix | Blend between original and processed stream: 0 original, 1 processed; some Replace/Gate modes bypass this blend. | Смесь исходного и обработанного потока: 0 — исходный, 1 — обработанный. Некоторые режимы Replace/Gate обходят смешивание.
factor | Factor | Clock-pattern factor in source steps; transforms the stream without changing project BPM. | Коэффициент clock-рисунка в исходных шагах; преобразует поток без изменения BPM проекта.
duty | Duty | Active fraction of each clock-mask cycle, 0–1. | Активная доля цикла clock-маски, 0–1.
delay | Delay | Distance to an earlier stream value, in source steps, not milliseconds. | Расстояние до предыдущего значения потока в исходных шагах, а не миллисекундах.
feedback | Feedback | Weight of earlier values in Memory/Feedback; in Delay controls successive echo contributions. | Вес предыдущих значений в Memory/Feedback; в Delay — вклад последовательных повторов.
initial | Initial | Value used before enough earlier steps exist. | Значение до появления достаточного числа предыдущих шагов.
repeats | Repeats | Number of delayed contributions summed by Delay. | Число задержанных вкладов, суммируемых Delay.
decay | Decay | Attenuation of successive delayed/feedback contributions. | Затухание последовательных задержанных вкладов или обратной связи.
iterations | Iterations | Number of Feedback smoothing passes over the stream. | Число проходов Feedback по потоку.
bias | Bias | Offset added to the preceding Feedback output before blending. | Смещение, добавляемое к предыдущему результату Feedback перед смешиванием.
clamp | Clamp | Symmetric Feedback output limit; 0 disables this additional limit. | Симметричное ограничение результата Feedback; 0 выключает дополнительный предел.
destination_block | Destination | Block receiving Parameter Modulation; (none) leaves the route unconnected. | Блок, принимающий Parameter Modulation; (none) оставляет маршрут неподключённым.
destination_parameter | Parameter | Numeric parameter on the destination block receiving the mapped source stream. | Числовой параметр блока назначения, принимающий отображённый исходный поток.
source_min | Source min | Input value mapped to the destination minimum. | Входное значение, отображаемое в минимум назначения.
source_max | Source max | Input value mapped to the destination maximum. | Входное значение, отображаемое в максимум назначения.
min | Minimum | Destination value at Source min; bounded by the destination parameter's range. | Значение назначения при Source min; ограничено диапазоном целевого параметра.
max | Maximum | Destination value at Source max; bounded by the destination parameter's range. | Значение назначения при Source max; ограничено диапазоном целевого параметра.
smoothing | Smoothing | Smooths parameter-modulation changes; higher values react more gradually. | Сглаживает изменения модуляции параметра; большие значения дают более плавную реакцию.
""")
for _kind, _en, _ru in (
    ("Modulo", "Add adds the ramp; Multiply scales the input; Gate keeps values above Threshold and substitutes Center elsewhere.", "Add прибавляет пилу; Multiply масштабирует вход; Gate сохраняет значения выше Threshold, заменяя остальные на Center."),
    ("Clock Divide", "Gate zeros inactive mask positions; Hold repeats the preceding output. The mask period is 2 × Factor steps.", "Gate обнуляет неактивные позиции; Hold повторяет предыдущий результат. Период маски — 2 × Factor шагов."),
    ("Clock Multiply", "Repeats each source value for Factor steps. Gate additionally applies Duty; Hold keeps the repeated values. BPM is unchanged.", "Повторяет каждое исходное значение на Factor шагах. Gate дополнительно применяет Duty; Hold сохраняет повторы. BPM не меняется."),
    ("Memory", "Blend mixes with the original using Mix; Replace directly uses the memory blend controlled by Feedback.", "Blend смешивает результат с оригиналом по Mix; Replace напрямую использует смесь памяти, заданную Feedback."),
    ("Delay", "Echo mixes original and delayed values; Replace emits delayed values; Gate keeps the original only when the delayed sum is positive.", "Echo смешивает исходные и задержанные значения; Replace выводит задержанные; Gate сохраняет оригинал при положительной сумме задержек."),
):
    CATALOG[f"process.{_kind}"] = {"mode": Entry("Mode", _en, _ru)}

_add("relation", """
source | Source | Block whose selected output stream is read. | Блок, чей выбранный выходной поток читается.
dest | Destination | Block receiving this relationship. | Блок, принимающий эту связь.
source_part | Output | Source stream: rhythm, pitch, velocity, duration, density or accent. | Исходный поток: rhythm, pitch, velocity, duration, density или accent.
dest_part | Input | Destination stream modified by the relationship. | Поток назначения, изменяемый связью.
algorithm | Operation | Copy replaces, Mix blends, Quantize To aligns, Modulate changes values, Follow follows contour, Trigger gates events, Dialogue alternates instruments. | Copy заменяет, Mix смешивает, Quantize To выравнивает, Modulate изменяет значения, Follow следует контуру, Trigger управляет событиями, Dialogue чередует инструменты.
amount | Amount | Influence strength, shaped by Curve. In Dialogue this is Separation: 0 bypasses, 1 strictly alternates. | Сила влияния с учётом Curve. В Dialogue это Separation: 0 — обход, 1 — строгое чередование.
curve | Curve | Shapes Amount: Linear, Exponential, Logarithmic, Threshold or four-step Quantize. | Преобразует Amount: Linear, Exponential, Logarithmic, порог Threshold или четырёхступенчатая Quantize.
delay | Delay | Source-event delay (0, 1, 2, 4 or 8 events), not seconds. Cyclic feedback is evaluated with causal history. | Задержка в событиях источника (0, 1, 2, 4 или 8), а не в секундах. Циклическая обратная связь использует историю.
probability | Chance | Chance of applying the route. Dialogue evaluates chance once per whole call/response cycle. | Вероятность применения связи. Dialogue проверяет её один раз на целый цикл вопроса/ответа.
enabled | Enabled | Bypasses or enables this relationship without deleting it. | Включает связь или обходит её без удаления.
""")
_add("dialogue", """
meter | Meter | Bar size for call/response durations; independent of Composition meter. | Размер такта для длительностей вопроса/ответа; независим от Composition.
call_bars | Call | Length of the source instrument's turn in dialogue-meter bars. | Длина реплики источника в тактах размера Dialogue.
response_bars | Response | Length of the destination instrument's turn in dialogue-meter bars. | Длина реплики адресата в тактах размера Dialogue.
gap_beats | Gap | Silence in quarter-note beats after each turn, including the loop boundary. | Тишина в четвертных долях после каждой реплики, включая границу повтора.
reply | Reply | Own phrase keeps the reply material; Echo follows call contour/accents; Contrast inverts them. Reply rhythm stays its own. CHORD/PAD/DRUM follow accents only. | Own phrase сохраняет материал ответа; Echo следует контуру/акцентам вопроса; Contrast инвертирует их. Ритм ответа остаётся своим. CHORD/PAD/DRUM следуют только акцентам.
follow | Follow | Strength of call contour/accent influence on the reply; 0 preserves its own material. | Сила влияния контура/акцентов вопроса на ответ; 0 сохраняет собственный материал.
""")
_add("composition", """
enabled | Enable composition | Arms the form without starting it. Composition Play enables and starts the plan. Header Play auditions Blocks. | Подготавливает форму без запуска. Composition Play включает и запускает план; главный Play прослушивает Blocks.
meter | Meter | Global form meter. A beat is a quarter note: 4/4 = 4 beats, 6/8 = 3, 7/8 = 3.5. | Общий размер формы. Доля — четверть: 4/4 = 4 доли, 6/8 = 3, 7/8 = 3.5.
play_button | Play composition | Starts Composition from From, using section settings and assignments on the shared transport. | Запускает Composition с позиции From, используя настройки и назначения секций на общем транспорте.
stop_button | Stop composition | Stops Composition playback and releases its notes. Header Stop/Space stops playback globally. | Останавливает Composition и отпускает её ноты. Главный Stop/Space останавливает воспроизведение глобально.
play_from | From | Selected section starts at the section being edited; Form start begins at zero; Timeline cursor uses the stored seek position. | Selected section — с редактируемой секции; Form start — с начала формы; Timeline cursor — с сохранённой позиции таймлайна.
ending | End | Loop form repeats the arrangement; Stop at end releases notes at its end; Hold last section continues with final settings and curve endpoints. | Loop form повторяет форму; Stop at end отпускает ноты на её конце; Hold last section продолжает с финальными настройками и концами кривых.
section_type_add | New section type | Starter preset used when adding a new section. Types do not restrict later editing. | Стартовый пресет новой секции. Тип не ограничивает дальнейшее редактирование.
add_button | + Section | Adds a section of the selected type; up to 128 sections. | Добавляет секцию выбранного типа; максимум 128 секций.
duplicate_button | Duplicate | Copies the selected section with its macros, curves, instrument settings and assignments. | Копирует выбранную секцию вместе с макросами, кривыми, настройками и назначениями инструментов.
remove_button | Remove | Removes the selected section from the form; Undo restores the edit. | Удаляет выбранную секцию из формы; Undo восстанавливает изменение.
up_button | Move earlier | Moves the selected section earlier in playback order. | Перемещает выбранную секцию раньше в порядке воспроизведения.
down_button | Move later | Moves the selected section later in playback order. | Перемещает выбранную секцию позже в порядке воспроизведения.
section_list | Sections | Select to edit; selection does not seek playback. Drag cards or use arrows to reorder the form. | Выбор открывает редактирование и не перематывает воспроизведение. Перетаскивайте карточки или используйте стрелки для смены порядка.
timeline | Timeline | Click/drag, then release to seek with sixteenth-note snapping. During Blocks playback this only prepares the future Composition cursor. | Щёлкните или перетащите и отпустите для перемотки с шагом шестнадцатой. При воспроизведении Blocks задаёт будущий курсор Composition.
total_label | TOTAL | Sum of section durations in bars, quarter-note beats and time at the current BPM. Header LENGTH is a source-buffer step count, not form duration. | Суммарная длина секций в тактах, четвертных долях и времени при текущем BPM. LENGTH в заголовке — шаги исходного буфера, а не длина формы.
section_name | Name | Name of the selected section, shown on its card and timeline. | Имя выбранной секции на карточке и таймлайне.
section_type | Type | Semantic section label. Changing it alone preserves current settings; Apply type preset replaces them with starter values. | Смысловая метка секции. Её смена сохраняет настройки; Apply type preset заменяет их стартовыми значениями.
section_bars | Duration | Selected section length, 1–128 bars in Composition Meter. | Длина выбранной секции, 1–128 тактов размера Composition.
transition_bars | Blend in | Incoming macro blend in bars, clipped to section length; includes loop seam. Smoothly interpolates previous macro endpoints. Does not crossfade audio or all instrument coefficients. | Входное смешивание макросов в тактах, не длиннее секции; включает стык повтора. Плавно интерполирует финальные макросы предыдущей секции. Не является аудиокроссфейдом и не смешивает все коэффициенты инструментов.
apply_preset_button | Apply type preset | Replaces the selected section's macro and block settings with its type's starter values. | Заменяет настройки макросов и блоков выбранной секции стартовыми значениями её типа.
color_button | Color | Display color of the section; does not affect the music. | Цвет отображения секции; на музыку не влияет.
parameter_list_toggle | Controlled parameters | Shows which musical parameters Composition can influence. | Показывает музыкальные параметры, на которые может влиять Composition.
details_toggle | Block / Drum Voice settings | Opens per-block/per-voice coefficients, expression and section MIDI automation. Kit card edits apply to all its voices. | Открывает коэффициенты, Expression и MIDI-автоматизацию отдельных блоков/голосов. Карточка Kit изменяет все его голоса.
section_midi_override | MIDI override | Off inherits Block Inspector/parent kit MIDI expression; on enables section-specific CC, pitch bend and aftertouch settings for the selected entity. | Выключено — наследуется MIDI Expression блока или родительского Kit; включено — действуют секционные CC, Pitch Bend и Aftertouch выбранного инструмента/голоса.
""")
_add("macro", """
energy | Energy | Overall dynamic energy. In Composition affects velocity relative to the live Global baseline; 0.5 is the neutral center. | Общая динамическая энергия. В Composition влияет на velocity относительно текущей основы Global; 0.5 — нейтральный центр.
tension | Tension | Higher tension loosens chord-tone anchoring in BASS/MELODY that follow Harmonic Plan. | Повышенная напряжённость ослабляет привязку к аккордовым тонам у BASS/MELODY, следующих Harmonic Plan.
density | Density | Global/section density shaping. Zero is not guaranteed silence; use instrument Density = 0 or Active off for silence. | Формирование общей или секционной плотности. Ноль не гарантирует тишину; для неё задайте Density инструмента = 0 или отключите Active.
variation | Variation | Intensity of dynamic/accent variation. It is distinct from the generator's Seed. | Интенсивность динамических/акцентных вариаций. Независима от Seed генератора.
""")
_add("composition_curve", """
enabled | Override | Off follows live Global, ignoring this section's scalar and curve. On enables this section's macro value. | Выключено — следование текущему Global с игнорированием значения и кривой секции. Включено — действует макрос секции.
slider | Value | Section macro value, 0–100%; used when Override is on and Curve is off. | Значение макроса секции, 0–100%; используется при включённом Override и выключенном Curve.
curve_toggle | Curve | Uses the editable curve instead of the scalar value; Override must also be on. | Использует редактируемую кривую вместо постоянного значения; Override тоже должен быть включён.
shape | Shape | Smooth eases segments without overshoot; Linear uses straight slopes; Step holds each value to the next point. | Smooth плавно соединяет точки без выбросов; Linear даёт прямые отрезки; Step удерживает значение до следующей точки.
curve | Curve editor | X spans the section from start to end; Y is 0–100%. Double-click adds, drag moves; right-click/Delete removes an interior point. Endpoints remain. | X — время от начала до конца секции; Y — 0–100%. Двойной щелчок добавляет точку, перетаскивание перемещает; правый щелчок/Delete удаляет внутреннюю точку. Крайние точки сохраняются.
""")
_add("section_instrument", """
active | Active | Allows notes in this section only. A global Mute still silences the instrument. Kit card changes affect all its voices. | Разрешает ноты только в этой секции. Глобальный Mute по-прежнему отключает инструмент. Карточка Kit меняет все его голоса.
enabled | Active | Allows the selected block/voice to emit notes in this section. | Разрешает выбранному блоку или голосу выдавать ноты в этой секции.
technique | Technique | Inherit phrase uses the section phrase assignment; None excludes this instrument from that assignment; a named technique replaces it locally. Coefficients still apply. | Inherit phrase использует назначение фразы секции; None исключает инструмент из него; именованный приём заменяет его локально. Коэффициенты продолжают действовать.
amount | Amount | Strength of the explicitly selected instrument technique, 0–100%. | Сила явно выбранного приёма инструмента, 0–100%.
shape | Shape | In eases into the change; Out changes quickly then settles; Out–in–out eases both ends; In–pulse rises and returns. | In плавно входит в изменение; Out быстро меняется и замедляется; Out–in–out сглаживает оба края; In–pulse нарастает и возвращается.
fit | Fit | Stretches the technique over this section. Off uses Beats, then holds the technique endpoint until the section ends. | Растягивает приём на секцию. Выключено — используется Beats, затем конечное состояние удерживается до конца секции.
beats | Beats | Duration of the local technique in quarter-note beats when Fit is off. | Длительность локального приёма в четвертных долях при выключенном Fit.
gate | Gate | Section note-duration multiplier: 1 is neutral. | Секционный множитель длительности ноты: 1 нейтрален.
density | Density | Per-event keep probability: 0 silent, 1 preserves all eligible source events. Later sections can restore events from the source. | Вероятность сохранения события: 0 — тишина, 1 — все допустимые исходные события. Следующие секции могут вернуть события из источника.
velocity | Velocity | Section velocity multiplier: 1 neutral, 0 silent, values above 1 strengthen dynamics. | Секционный множитель velocity: 1 нейтрален, 0 — тишина, выше 1 — усиление динамики.
register_center | Register Center | Section offset to the manual block Center in semitones: 0 follows the block, +12 raises its register by an octave. Drum Voice notes stay fixed. | Секционное смещение ручного Center блока в полутонах: 0 следует блоку, +12 поднимает регистр на октаву. Ноты Drum Voice фиксированы.
variation | Variation | Deterministic per-event velocity variation in this section; 0 disables it. | Детерминированная вариативность velocity событий секции; 0 выключает её.
accent | Accent | Additional section accent strength; 0 is neutral. | Дополнительная сила акцентов секции; 0 нейтрален.
octave_spread | Octave spread | Extra octave placement variation for pitched notes; 0 is neutral. Unavailable for Drum Voices. | Дополнительная вариативность октавного размещения тональных нот; 0 нейтрален. Недоступно Drum Voice.
harmony | Harmony | Multiplier of chord-tone anchoring for BASS/MELODY following Harmonic Plan; 1 is neutral. | Множитель привязки BASS/MELODY к аккордовым тонам Harmonic Plan; 1 нейтрален.
mode | Mode | Global SEQ/LIVE mode of the instrument, shared across sections. | Глобальный режим SEQ/LIVE инструмента, общий для всех секций.
mute | Mute | Global mute across all sections, independent of local Active. | Глобальный Mute во всех секциях, независимо от локального Active.
details | Details / Voices | Opens detailed settings for this block and individual Drum Voices. | Открывает подробные настройки блока и отдельных Drum Voice.
curve | Preview | Preview of the assigned performance gesture; selecting a technique does not start standalone audition. | Превью назначенного исполнительского приёма; выбор приёма не запускает отдельное прослушивание.
""")
_add("section_phrase", """
phrase | Phrase | Multi-stage performance phrase assigned to this section; None leaves macros and coefficients active. Starts with Composition playback. | Многоэтапная исполнительская фраза секции; None сохраняет действие макросов и коэффициентов. Запускается с Composition.
amount | Amount | Strength of the section phrase, 0–100%. | Сила фразы секции, 0–100%.
fit | Fit to section | Proportionally stretches phrase stages to the section length and holds the final state at its endpoint. | Пропорционально растягивает этапы фразы на длину секции и удерживает финальное состояние на её конце.
duration | Duration | Phrase duration in quarter-note beats when Fit is off; after completion the phrase fades out its performance layer. | Длительность фразы в четвертных долях при выключенном Fit; после завершения фраза плавно освобождает свой исполнительский слой.
targets | Targets | All includes current and future blocks; a selected subset restricts phrase targets. An empty subset targets none. Local Technique overrides take precedence. | All включает текущие и будущие блоки; выбранный список ограничивает цели. Пустой список не выбирает никого. Локальный Technique имеет приоритет.
""")
_add("director", """
curve | Phrase Curve | Tension trajectory for the Musical Director; Custom preserves a loaded trajectory. | Траектория напряжённости Musical Director; Custom сохраняет загруженную траекторию.
Smoothing | Smoothing | Smoothness of Director state changes; higher settings react more gradually. | Плавность изменения состояния Director; большие значения дают более постепенную реакцию.
Energy Influence | Energy Influence | Strength of the Director's influence on dynamic energy. | Сила влияния Director на динамическую энергию.
Density Influence | Density Influence | Strength of the Director's influence on event density. | Сила влияния Director на плотность событий.
Register Influence | Register Influence | Strength of the Director's influence on the pitch register. | Сила влияния Director на высотный регистр.
Probability Influence | Probability Influence | Strength of the Director's influence on event probability. | Сила влияния Director на вероятность событий.
Voice Smooth | Voice Smooth | Smoothness of harmonic voice leading; shared with the engine's voice-leading solver. | Плавность гармонического голосоведения; настройка передаётся механизму голосоведения движка.
""")
_add("harmony", """
enabled | Follow plan | CHORD/PAD use plan chords; BASS/MELODY anchor to their tones according to Follow/Strength. DRUM is unaffected. | CHORD/PAD используют аккорды плана; BASS/MELODY привязываются к их тонам по Follow/Strength. DRUM не меняется.
meter | Meter | Bar size for harmonic durations, independent of Composition and Kit meters. | Размер такта гармонических длительностей, независимый от Composition и Kit.
loop | Loop | Repeats the harmonic plan; off holds the final chord after the plan ends. | Повторяет гармонический план; выключено — после конца удерживается последний аккорд.
presets | Preset | Selects a starter chord progression; Use preset replaces the chord list and enables the plan. | Выбирает стартовую последовательность; Use preset заменяет список аккордов и включает план.
root | Root | Chord root pitch class, independent of the header KEY/SCALE. | Класс высоты тоники аккорда, независимый от KEY/SCALE в заголовке.
quality | Quality | Chord type and its tones; seventh chords retain four notes. | Тип аккорда и его тоны; септаккорды сохраняют четыре ноты.
bars | Duration | Chord duration, 1–64 bars of the Harmonic Plan meter. | Длительность аккорда, 1–64 такта размера Harmonic Plan.
""")
_add("midi_expression", """
cc_table | CC lanes | Up to 16 distinct CC lanes. Values use the shared Musical Clock; choose a row to edit its curve below. | До 16 отдельных линий CC. Значения используют общие музыкальные часы; выберите строку для редактирования её кривой ниже.
enabled | Enable | Enables this expression lane without changing note generation. | Включает линию MIDI-выразительности без изменения генерации нот.
cc | CC | MIDI controller number, 0–119; use a distinct number for each lane. | Номер MIDI-контроллера, 0–119; для каждой линии используйте отдельный номер.
min | Min | Minimum outgoing controller value, 0–127. | Минимальное выходное значение контроллера, 0–127.
max | Max | Maximum outgoing controller value, 0–127. | Максимальное выходное значение контроллера, 0–127.
period | Period | Curve cycle length in quarter-note beats for Loop. Section timebase stretches the curve over the entire section and ignores Period. | Длина цикла кривой в четвертных долях для Loop. Section растягивает кривую на всю секцию и игнорирует Period.
rate | Rate | Minimum interval between expression samples, in beats. Smaller values send more frequent MIDI updates. | Минимальный интервал между отсчётами в долях. Меньшее значение отправляет MIDI чаще.
phase | Phase | Loop curve phase offset in quarter-note beats; Section timebase uses section progress. | Фазовый сдвиг кривой Loop в четвертных долях; Section использует прогресс секции.
timebase | Timebase | Loop repeats every Period on the shared beat clock. Section traverses the full curve once over the current section; Period is ignored. | Loop повторяется с Period по общим музыкальным часам. Section проходит всю кривую один раз за текущую секцию; Period игнорируется.
shape | Shape | Linear, Smooth or Step interpolation between curve points. | Интерполяция точек кривой: Linear, Smooth или Step.
points | Points | Normalized x:y pairs, e.g. 0:0,0.5:1,1:0; edit text or drag the curve. Up to 64 points. | Нормированные пары x:y, например 0:0,0.5:1,1:0; редактируйте текст или кривую. До 64 точек.
bend_range | Bend Range | Expected pitch-bend range in semitones, 1–24. The receiving instrument must use the same range for matching pitch. | Ожидаемый диапазон Pitch Bend, 1–24 полутона. Принимающий инструмент должен использовать тот же диапазон для совпадения высоты.
bend_points | Bend Points | Normalized bend: 0 fully down, 0.5 center, 1 fully up. X spans Period. | Нормированный изгиб: 0 — максимум вниз, 0.5 — центр, 1 — максимум вверх. X охватывает Period.
after_mode | Aftertouch Mode | Channel pressure affects the channel; Polyphonic pressure addresses active note pitches. Receiver support is required. | Channel pressure действует на канал; Polyphonic pressure адресует высоты активных нот. Нужна поддержка принимающего инструмента.
after_sensitivity | Sensitivity | Pressure gain: 0 sends zero, 1 normal, 2 doubles the curve level, clipped to 127. | Усиление давления: 0 — нулевое, 1 — обычное, 2 удваивает уровень с ограничением до 127.
after_points | Aftertouch Points | Normalized pressure: 0 none, 1 maximum. X spans Period. | Нормированное давление: 0 — нет, 1 — максимум. X охватывает Period.
""")
_add("influence", """
policy | Policy | Priority resolves sources in order; Blend combines enabled source weights; Manual keeps the manual value. | Priority разрешает источники по порядку; Blend смешивает включённые источники по весам; Manual сохраняет ручное значение.
priority | Priority | Highest priority is first; partial weights allow lower-priority layers through. | Первым указан высший приоритет; частичные веса пропускают нижние слои.
manual | Manual | Weight of the manual base value, 0–1. | Вес ручного базового значения, 0–1.
macro | Macro | Weight of global/section macro influence, 0–1. | Вес влияния глобальных/секционных макросов, 0–1.
technique | Technique | Weight of performance techniques, 0–1. | Вес исполнительских приёмов, 0–1.
modulation | Modulation | Weight of modulation routes, 0–1; multiple routes in the category are averaged. | Вес маршрутов модуляции, 0–1; несколько маршрутов категории усредняются.
""")
_add("project", """
bpm | BPM | Tempo in quarter notes per minute, shared by Blocks, Composition, performance and MIDI expression. | Темп в четвертных нотах в минуту, общий для Blocks, Composition, исполнения и MIDI Expression.
length | LENGTH | Source sequence buffer length in steps; independent of section durations in bars. | Длина исходного буфера последовательности в шагах; независима от длительностей секций в тактах.
key | KEY | Global root for scale-based material. Explicit harmonic-plan chord roots remain independent. | Общий корень материала, основанного на гамме. Явные тоники Harmonic Plan независимы.
scale | SCALE | Global scale for scale-based material; blocks may carry their own scale settings. | Общая гамма материала; блоки могут иметь собственные настройки гаммы.
seed | SEED | Project random seed for repeatable generation. Regenerate rebuilds material; it does not start playback. | Зерно проекта для повторяемой генерации. Regenerate перестраивает материал, но не запускает воспроизведение.
""")
_add("midi_learn", """
input | Input port | Connect the hardware MIDI input before learning. Select its port so incoming messages can reach the mapping. | Подключите аппаратный MIDI-вход перед обучением. Выберите его порт для поступления сообщений в назначение.
learn | Learn | Starts capture for a block parameter or Global macro. Move the hardware control; after capture, subsequent messages change the parameter. | Начинает захват для параметра блока или макроса Global. Поверните аппаратный контрол: после захвата следующие сообщения меняют параметр.
enabled | Enabled | Enables this stored MIDI mapping. | Включает сохранённое MIDI-назначение.
pickup | Pickup | For absolute CC controls, waits until the hardware crosses the manual value to avoid a jump. Note-velocity learning disables pickup by default. | Для абсолютных CC ждёт пересечения ручного значения аппаратной ручкой, предотвращая скачок. Обучение по velocity ноты по умолчанию выключает Pickup.
minimum | Minimum | Parameter value mapped to the input minimum; must fit the destination range. | Значение параметра для минимума входа; должно быть в диапазоне назначения.
maximum | Maximum | Parameter value mapped to the input maximum; can reverse the control direction with a lower endpoint. | Значение параметра для максимума входа; обратный порядок границ меняет направление управления.
cancel | Cancel Learn | Cancels pending capture without removing saved mappings. | Отменяет ожидание захвата без удаления сохранённых назначений.
remove | Remove | Removes the selected mapping. Clear removes all mappings. | Удаляет выбранное назначение. Clear удаляет все назначения.
""")
_add("midi_sync", """
enabled | Send MIDI Clock | Sends 24 MIDI clock pulses per quarter note at the project tempo. | Отправляет 24 импульса MIDI Clock на четверть при темпе проекта.
transport | Transport messages | Sends MIDI Start, Stop and Continue alongside clock according to transport actions. | Отправляет MIDI Start, Stop и Continue вместе с clock по действиям транспорта.
spp | Song Position Pointer | Sends the musical position on seek using MIDI Song Position Pointer. | Передаёт музыкальную позицию при перемотке через MIDI Song Position Pointer.
port | Output | Sends synchronization to all active outputs or the selected output port. | Отправляет синхронизацию во все активные выходы или выбранный порт.
""")

GENERATOR_KEYS = {
    "Euclidean": "euclidean_steps pulses euclidean_rotation",
    "Bresenham": "bres_steps bres_pulses bres_rotation",
    "Polyrhythm": "poly_a poly_b poly_phase_a poly_phase_b poly_mode",
    "Thue-Morse": "tm_rotation tm_invert tm_density variation_seed",
    "Fibonacci Rhythm": "fib_density fib_offset",
    "Fibonacci": "sequence_mod sequence_stride sequence_offset sequence_reverse",
    "Recaman": "sequence_mod sequence_stride sequence_offset sequence_reverse",
    "De Bruijn": "debruijn_order debruijn_rotation debruijn_mode",
    "Interval Walker": "interval_step interval_return interval_range interval_leap interval_quantize variation_seed",
    "Scale Walker": "scale_step scale_direction scale_octaves scale_leap variation_seed",
    "Weighted Scale": "scale_weights scale_octave_spread variation_seed",
    "Arpeggiator": "arp_pattern arp_octaves arp_direction arp_octave_mode variation_seed",
    "Cellular Automaton": "ca_rule ca_generations ca_density ca_mode ca_seed ca_boundary ca_evolution variation_seed",
    "L-System": "ls_axiom ls_rule_a ls_rule_b ls_iterations ls_mode ls_mapping",
    "Turing Machine": "turing_preset turing_mode turing_tape turing_density turing_wrap variation_seed",
    "Orbital Sequence": "orbit_cycle_a orbit_cycle_b orbit_phase_a orbit_phase_b orbit_mode orbit_output orbit_rotation",
    "Geometry Collision": "geometry_shape geometry_mode geometry_particles geometry_speed geometry_substeps variation_seed",
    "Logistic Chaos": "chaos_r chaos_x chaos_octaves chaos_burn_in chaos_smooth chaos_quantize",
    "Markov": "markov_jump markov_transpose markov_octaves markov_rest markov_leap markov_stay variation_seed",
    "Random Walk": "walk_step walk_range walk_start walk_return_bias walk_drift variation_seed",
    "Probability": "probability probability_pitch_range probability_center probability_octaves probability_velocity_floor variation_seed",
    "Pattern": "pattern pattern_rotation pattern_scale pattern_probability pattern_reverse pattern_step_chances",
}
PROCESS_KEYS = {
    "Counter": "length step offset center phase reset depth waveform",
    "Modulo": "modulus offset scale center threshold depth mode",
    "Compare": "threshold true_value false_value hysteresis mix operator invert",
    "Clock Divide": "factor phase duty mode",
    "Clock Multiply": "factor phase duty mode",
    "Memory": "delay feedback mix initial mode",
    "Delay": "delay repeats feedback mix decay initial mode",
    "Feedback": "feedback iterations decay mix bias clamp initial",
    "Parameter Modulation": "destination_block destination_parameter source_min source_max min max smoothing depth",
}


_add("articulation", """
drum_ratchet_probability | Ratchet chance | 0–1 chance of subdividing an accepted Drum Voice hit. Zero bypasses Ratchet. Source rests and source probability are evaluated before articulation. | Вероятность 0–1 дробления принятого удара Drum Voice. Ноль отключает Ratchet. Паузы и вероятность источника проверяются до артикуляции.
drum_ratchet_count | Ratchet count | Integer 1–8 principal hits, including the original hit. Flam can add one grace before the first principal. | Целые 1–8 основных ударов, включая исходный. Flam может добавить один предудар перед первым основным ударом.
drum_ratchet_spread | Ratchet spread | 0.1–1 of the source interval occupied by the repeat grid. One spreads repeats evenly across that interval; smaller values make a tighter cluster. | Доля исходного интервала 0.1–1, занимаемая сеткой повторов. Единица равномерно распределяет повторы по интервалу; меньшие значения собирают их плотнее.
drum_ratchet_decay | Ratchet decay | 0–1 velocity multiplier for each subsequent principal hit. One keeps dynamics equal; zero silences later repeats. | Множитель velocity 0–1 для каждого следующего основного удара. Единица сохраняет одинаковую динамику; ноль выключает последующие повторы.
drum_flam_probability | Flam chance | 0–1 chance of a quiet grace at the source onset, followed by the principal after Gap. Only the first ratchet principal gets a grace. Zero bypasses Flam. | Вероятность 0–1 тихого предудара на исходной позиции с основным ударом через Gap. Предудар получает только первый основной удар Ratchet. Ноль отключает Flam.
drum_flam_spacing | Flam gap · beats | 0.01–0.12 quarter-note beats; 0.04 is 20 ms at 120 BPM. Clamped to 45% of a repeat subdivision so it cannot cross the next hit. The principal is delayed after the grace in both SEQ and LIVE. | 0.01–0.12 четвертной доли; 0.04 — это 20 мс при 120 BPM. Ограничивается 45% шага повтора, чтобы не пересекать следующий удар. Основной удар следует после предудара с одинаковым правилом в SEQ и LIVE.
drum_flam_velocity | Flam grace velocity | 0.05–1 multiplier of the source velocity for the grace. The principal retains the source velocity. | Множитель 0.05–1 исходной velocity для предудара. Основной удар сохраняет исходную velocity.
""")


_add("strum", """
strum_probability | Strum chance | CHORD/PAD: 0–1 probability of strumming an accepted chord; zero preserves simultaneous notes. Probability is drawn once for the whole chord. | CHORD/PAD: вероятность 0–1 перебора принятого аккорда; ноль сохраняет одновременные ноты. Вероятность проверяется один раз на весь аккорд.
strum_spacing | Strum gap · beats | Requested spacing between notes, 0–0.5 quarter-note beats. 0.04 is 20 ms at 120 BPM. Wide strums compress to fit the source interval, gate and harmonic cutoff. | Запрошенный интервал между нотами, 0–0.5 четвертной доли. 0.04 — это 20 мс при 120 BPM. Широкий перебор сжимается под интервал источника, gate и границу гармонии.
strum_dynamics | Strum dynamics | −1…+1 velocity slope in playing order: negative fades, positive grows, zero preserves source velocity before Humanize. Notes remain within MIDI velocity limits. | Наклон velocity −1…+1 по порядку игры: отрицательный — затихание, положительный — нарастание, ноль сохраняет исходную velocity до Humanize. Значения остаются в пределах MIDI velocity.
strum_humanize | Strum humanize | 0–1 repeatable variation of gaps and velocity. Timing varies by at most 20% of a subdivision, velocity by 10%; note order and event boundaries stay protected. | Воспроизводимый разброс интервалов и velocity 0–1. Время меняется максимум на 20% шага, velocity — на 10%; порядок нот и границы события сохраняются.
strum_direction | Strum direction | Up/Down follow actual MIDI pitch after voicing. Alternate changes direction on source steps, including rests; Random shuffles existing tones deterministically. | Up/Down следуют фактической MIDI-высоте после voicing. Alternate меняет направление по шагам источника, включая паузы; Random воспроизводимо перемешивает имеющиеся ноты.
strum_gate_mode | Strum gate | Shared end releases all tones at the original chord end. Per note gives each tone its full source duration. Both respect harmonic, Dialogue and transport boundaries. | Shared end завершает все ноты в исходный момент конца аккорда. Per note даёт каждой ноте полную исходную длительность. Оба режима учитывают границы гармонии, Dialogue и транспорта.
""")


def entry(scope, key):
    """Return exact semantic help, with explicit shared-scope fallbacks."""
    found = CATALOG.get(scope, {}).get(key)
    if found is not None:
        return found
    if scope.startswith("process."):
        return CATALOG["process"].get(key)
    if scope in ("block", "generator"):
        for shared in ("block", "generator", "kit", "motif", "articulation", "strum"):
            if key in CATALOG[shared]:
                return CATALOG[shared][key]
    return None
_add("perform", """
preset | Technique | Musical gesture for this block; selection alone does not start playback. Enable/Restart auditions it. | Музыкальный приём блока; выбор сам по себе не запускает воспроизведение. Enable/Restart прослушивает приём.
amount | Amount | Strength of the auditioned performance gesture, 0–100%. | Сила прослушиваемого исполнительского жеста, 0–100%.
shape | Shape | Easing of the gesture: In, Out, Out–in–out or In–pulse. | Характер изменения: In, Out, Out–in–out или In–pulse.
length | Beats | Duration of the gesture in quarter-note beats. | Длительность жеста в четвертных долях.
phrase | Phrase | Multi-stage musical phrase for the selected target blocks. Play Phrase explicitly starts it. | Многоэтапная музыкальная фраза выбранных блоков. Play Phrase запускает её явно.
duration | Duration | Phrase length in quarter-note beats; all stages stretch proportionally. | Длина фразы в четвертных долях; этапы растягиваются пропорционально.
targets | Targets | Blocks included in this manual phrase audition. | Блоки, участвующие в ручном прослушивании фразы.
""")
_add("macro_route", """
value | Macro value | Manual macro value from 0 to 1, mapped to each assigned route. | Ручное значение макроса от 0 до 1, отображаемое в назначенные маршруты.
block_combo | Target block | Block receiving this user macro route. | Блок, принимающий этот маршрут пользовательского макроса.
parameter_combo | Parameter | Numeric block parameter controlled by the route. | Числовой параметр блока, управляемый маршрутом.
min_value | Minimum | Destination parameter value at macro 0. | Значение целевого параметра при макросе 0.
max_value | Maximum | Destination parameter value at macro 1. | Значение целевого параметра при макросе 1.
amount | Amount | Strength of this user macro route. | Сила маршрута пользовательского макроса.
curve | Curve | Exponent shaping the route: 1 linear; larger values delay the rise; smaller values emphasize the start. | Показатель формы маршрута: 1 — линейно; больше — рост позже; меньше — усиление начала.
""")

_add("influence", """
composition | Composition weight | Weight of section parameter automation in this parameter policy. Default priority puts Composition first; 0 bypasses it. | Вес секционной автоматизации в политике параметра. По умолчанию Composition имеет первый приоритет; 0 обходит его.
""")
