"""Bilingual Auricle user guide content.

UI imports this module instead of embedding the documentation in auricle_gui.py.
"""
from functools import lru_cache
from html import escape
import re

from help_catalog import CATALOG, GENERATOR_KEYS, PROCESS_KEYS, entry
from auricle_catalogs import BLOCK_TYPES, GENERATORS, PROCESS_TYPES
from performance_presets import COMMON, ALGORITHM_GESTURES, PHRASES, KIT_EVOLUTION

ALGORITHMS = {
    "Euclidean": ("Euclidean rhythm distributes a chosen number of hits as evenly as possible across a cycle. Use Steps, Pulses and Rotation to move the accent pattern without changing its density.", "Ритм Евклида распределяет заданное число ударов максимально равномерно по циклу. Используйте Steps, Pulses и Rotation, чтобы менять рисунок акцентов, не меняя общую плотность."),
    "Bresenham": ("Bresenham treats rhythm as a discrete line-rasterization problem. It is useful for clean, mechanical distributions of events across a loop.", "Bresenham рассматривает ритм как дискретную растеризацию линии. Подходит для чётких механических распределений событий по циклу."),
    "Polyrhythm": ("Polyrhythm combines two independent cycles. Cycle A and Cycle B can create interference patterns whose combined period is longer than either source cycle.", "Polyrhythm объединяет два независимых цикла. Cycle A и Cycle B создают интерференционные рисунки, общий период которых может быть длиннее каждого исходного цикла."),
    "Thue-Morse": ("Thue-Morse generates a recursively structured binary pattern. It produces repetition with controlled self-similarity and is useful for non-obvious rhythmic symmetry.", "Thue-Morse создаёт рекурсивно организованный бинарный рисунок. Он даёт повторение с контролируемым самоподобием и хорошо подходит для необычной ритмической симметрии."),
    "Fibonacci Rhythm": ("Density sets the hit count across the full 0–1 range, including silence and every step. Fibonacci Rhythm derives event placement from Fibonacci structure. Density and offset control how strongly the sequence is exposed as rhythm.", "Density задаёт число ударов во всём диапазоне 0–1, от тишины до заполнения всех шагов. Fibonacci Rhythm строит расположение событий на основе структуры Фибоначчи. Density и Offset определяют, насколько явно последовательность проявляется в ритме."),
    "Fibonacci": ("Fibonacci generates a deterministic numerical sequence that can be mapped into pitch or other musical dimensions. Use range, stride and offset to shape its musical scale.", "Fibonacci создаёт детерминированную числовую последовательность, которую можно отображать на высоту или другие музыкальные измерения. Range, Stride и Offset формируют её музыкальное поведение."),
    "Recaman": ("Recamán generates a non-linear integer sequence with frequent directional changes. It is useful for irregular pitch contours and evolving patterns.", "Recamán создаёт нелинейную целочисленную последовательность с частыми сменами направления. Подходит для неровных мелодических контуров и развивающихся паттернов."),
    "De Bruijn": ("De Bruijn sequences visit combinations of symbols with controlled coverage. They are useful when you want systematic variation with minimal immediate repetition.", "Последовательности De Bruijn проходят комбинации символов с контролируемым покрытием. Они полезны для систематического разнообразия при минимуме непосредственных повторов."),
    "Markov": ("Markov generates the next musical event from transition probabilities. Max Jump, Rest, Repeat, Leap and Seed control stability versus exploration.", "Markov выбирает следующее музыкальное событие по вероятностям переходов. Max Jump, Rest, Repeat, Leap и Seed управляют балансом стабильности и исследования."),
    "Random Walk": ("Random Walk moves through pitch or value space one bounded step at a time. Drift, return bias and range determine whether the line wanders or stays centered.", "Random Walk перемещается по пространству высоты или значения небольшими ограниченными шагами. Drift, Return Bias и Range определяют, будет ли линия блуждать или оставаться около центра."),
    "Interval Walker": ("Interval Walker chooses interval-sized moves rather than absolute notes. Step, range, leap chance and return behavior shape the melodic contour.", "Interval Walker выбирает движения по интервалам, а не абсолютным нотам. Step, Range, Leap Chance и Return Bias формируют мелодический контур."),
    "Scale Walker": ("Scale Walker moves through degrees of the selected scale. Direction, step size, leap probability and octave range provide controlled melodic motion.", "Scale Walker перемещается по ступеням выбранной гаммы. Direction, Step, Leap Chance и Octave Range дают контролируемое мелодическое движение."),
    "Weighted Scale": ("Weighted Scale assigns different probabilities to scale degrees. It is useful for biased tonal melodies where some notes occur more often than others.", "Weighted Scale назначает разные вероятности ступеням гаммы. Подходит для тональных мелодий с намеренным перевесом в сторону определённых нот."),
    "Arpeggiator": ("Arpeggiator cycles through chord/scale tones using an order, octave range and direction. It is useful for harmonic motion and repeating ostinatos.", "Arpeggiator перебирает тоны аккорда или гаммы с заданными порядком, диапазоном октав и направлением. Подходит для гармонического движения и остинато."),
    "Probability": ("Probability makes events stochastic according to a probability threshold. It is a direct way to turn a dense source into a sparse, evolving stream.", "Probability делает события стохастическими по заданному порогу вероятности. Это простой способ превратить плотный источник в разреженный развивающийся поток."),
    "Pattern": ("Pattern plays an explicit user-defined numeric pattern. Use it when you want algorithmic processing around a known rhythmic or melodic seed.", "Pattern воспроизводит явно заданный пользователем числовой паттерн. Используйте его, когда алгоритмическая обработка должна работать вокруг известного ритмического или мелодического зерна."),
    "Cellular Automaton": ("Cellular Automaton evolves a binary tape through local elementary rules. Choose a boundary mode and output either the final row, the full evolution trail or an XOR summary. Pitch mode treats inactive cells as rests.", "Cellular Automaton развивает бинарную ленту по локальным элементарным правилам. Выберите граничные условия и выводите последнюю строку, след эволюции или XOR-сводку. В режиме Pitch неактивные клетки становятся паузами."),
    "L-System": ("L-System expands an axiom through rewriting rules. In Turtle modes, + and - move the pitch degree, while [ and ] save and restore a branch position.", "L-System расширяет аксиому по правилам переписывания. В режимах Turtle символы + и - перемещают ступень, а [ и ] сохраняют и восстанавливают позицию ветви."),
    "Turing Machine": ("A finite binary tape is processed by a small state machine. Busy Beaver, Alternator and Growth use different transition rules; Marbles emits events when moving particles collide. Tape, density and edge wrapping shape the result.", "Небольшая машина состояний обрабатывает конечную бинарную ленту. Busy Beaver, Alternator и Growth используют разные правила переходов; Marbles создаёт события при столкновении движущихся частиц. Лента, плотность и циклические края формируют результат."),
    "Orbital Sequence": ("Two independent periodic orbits meet on the same step grid. Cycle lengths and phase offsets create long interference patterns; A, B, OR, AND, XOR and Interlock choose how the orbits interact.", "Две независимые периодические орбиты встречаются на общей сетке шагов. Длины циклов и фазовые смещения создают длинные интерференционные рисунки; A, B, OR, AND, XOR и Interlock задают характер взаимодействия."),
    "Geometry Collision": ("Particles bounce inside a box, triangle, hexagon or circle. Quantized boundary collisions become rhythm triggers or scale-degree notes. Particle count, speed and simulation substeps control density and complexity.", "Частицы отражаются внутри прямоугольника, треугольника, шестиугольника или круга. Квантованные столкновения с границами превращаются в ритмические события или ноты ступеней гаммы. Количество частиц, скорость и число шагов симуляции управляют плотностью и сложностью."),
    "Logistic Chaos": ("Logistic Chaos uses the logistic map to create deterministic but highly sensitive trajectories. Chaos R, initial state and smoothing control the degree of instability.", "Logistic Chaos использует логистическое отображение для детерминированных, но чувствительных траекторий. Chaos R, Initial X и Smooth управляют степенью нестабильности."),
}

PROCESSES = {
    "Counter": ("Adds a repeating ramp, triangle or sine control signal. Good for cyclic sweeps of pitch, density or velocity.", "Добавляет повторяющийся управляющий сигнал Ramp, Triangle или Sine. Подходит для циклических изменений pitch, density или velocity."),
    "Modulo": ("Creates a repeating modular control pattern. Use Add, Multiply or Gate modes to impose periodic structure.", "Создаёт повторяющийся модульный управляющий рисунок. Режимы Add, Multiply и Gate задают способ воздействия."),
    "Compare": ("Compares each value with a threshold and blends between true and false values. Useful for gates, accents and conditional transformations.", "Сравнивает каждое значение с порогом и смешивает true/false значения. Полезен для gate, accent и условных преобразований."),
    "Clock Divide": ("Slows a stream by periodically gating or holding events. Useful for creating slower envelopes and rhythmic subdivisions.", "Замедляет поток периодическим gate или удержанием. Полезен для медленных огибающих и ритмических делений."),
    "Clock Multiply": ("Repeats or gates a source according to a clock factor. Each source value is repeated for Factor steps; project BPM is unchanged.", "Повторяет или открывает источник с заданным коэффициентом clock. Каждое исходное значение повторяется на Factor шагах; BPM проекта не меняется."),
    "Memory": ("Reads a previous value and blends it with the current value. Delay and feedback create persistence and smoothing.", "Читает предыдущее значение и смешивает его с текущим. Delay и Feedback создают инерцию и сглаживание."),
    "Delay": ("Adds delayed copies of a stream. Repeats, feedback and decay control the resulting echo-like structure.", "Добавляет задержанные копии потока. Repeats, Feedback и Decay управляют структурой, похожей на эхо."),
    "Feedback": ("Feeds processed output back through the process for iterative evolution. Keep feedback bounded when using pitch or velocity.", "Возвращает обработанный выход обратно в процесс для итеративного развития. Для pitch и velocity рекомендуется ограничивать feedback."),
    "Parameter Modulation": ("Reads a musical stream as a control signal for a real numeric parameter. Modulation is applied with an event delay to avoid same-pass recursive feedback.", "Читает музыкальный поток как управляющий сигнал для реального числового параметра. Модуляция применяется с задержкой события, чтобы избежать рекурсивного feedback в одном проходе."),
}


BLOCKS = {
    "DRUM": ("A kit of independent Drum Voices. Each voice has its own source, processing and MIDI note/route; coordinated mode arranges role-based voices on a shared grid. Use Free for an independent voice.", "Набор независимых Drum Voice. У каждого голоса свои источник, обработка, MIDI-нота и маршрут. Согласованный режим размещает ролевые голоса на общей сетке; Free оставляет голос независимым."),
    "BASS": ("Low-register foundation. Groove Follow/Accent can couple it to drums; Harmonic Plan can anchor it to chord tones. Register Center/Width constrain its placement.", "Низкая опора композиции. Groove Follow/Accent связывают партию с ударными; Harmonic Plan привязывает её к аккордовым тонам. Register Center/Width ограничивают размещение по регистру."),
    "MELODY": ("A pitched lead line with scale/register shaping and optional chord-source or Harmonic Plan anchoring. Start with modest density so the contour remains clear.", "Тональная мелодическая линия с гаммой, регистром и необязательной привязкой к аккордовому источнику или Harmonic Plan. Умеренная плотность помогает сохранить читаемый контур."),
    "PAD": ("Sustained harmonic texture. Gate, Role Duration and Sustain control length; Chord Size/Spread/Inversion shape local voicings, or Harmonic Plan supplies explicit chords.", "Протяжённая гармоническая фактура. Gate, Role Duration и Sustain задают длительность; Chord Size/Spread/Inversion формируют локальные созвучия, либо Harmonic Plan задаёт явные аккорды."),
    "CHORD": ("Rhythmic chordal part. A generator supplies activity, while chord controls or Harmonic Plan determine voicing. Gate separates short stabs from connected chords.", "Ритмическая аккордовая партия. Генератор задаёт активность, а настройки аккорда или Harmonic Plan — созвучие. Gate разделяет короткие удары и связные аккорды."),
}

_TECH_RU = {
    "crescendo": "Постепенно усиливает динамику и заполнение.",
    "diminuendo": "Постепенно уменьшает динамику и заполнение.",
    "sforzando": "Короткий акцент с возвратом к исходной динамике.",
    "accelerando": "Увеличивает скорость шагов; BPM проекта сохраняется.",
    "ritardando": "Уменьшает скорость шагов; BPM проекта сохраняется.",
    "stringendo": "Ускоряет движение и усиливает динамику.",
    "smorzando": "Уменьшает динамику, заполнение и скорость движения.",
    "staccato": "Укорачивает Gate, делая ноты отрывистыми.",
    "tenuto": "Увеличивает Gate для связного звучания.",
    "rubato": "Добавляет мягкие временные колебания без постоянной смены BPM.",
    "register_rise": "Поднимает Center относительно ручной основы с сохранением классов высоты.",
    "register_fall": "Опускает Center относительно ручной основы с сохранением классов высоты.",
    "density_swell": "Увеличивает плотность и вероятность событий.",
    "density_drop": "Быстро уменьшает плотность и вероятность событий.",
    "accent_build": "Усиливает акцентность.",
    "dynamic_scatter": "Добавляет вариативность velocity.",
    "register_bloom": "Расширяет регистровое окно без смещения его центра.",
    "harmonic_resolve": "Усиливает привязку BASS/MELODY к аккордовым тонам Harmonic Plan.",
    "kit_evolution": "Развивает сбивки, синкопы, томы и вариативность согласованного Kit.",
}


def _language(language):
    return "ru" if str(language).lower().startswith("ru") else "en"


@lru_cache(maxsize=2)
def help_markdown(language="en"):
    """Build the reference from the same entries that supply widget tooltips."""
    lang = _language(language)
    ru = lang == "ru"
    def h(en, russian):
        return russian if ru else en
    lines = []
    def section(title, anchor, level=2):
        lines.extend([f'<a name="{anchor}"></a>', "", "#" * level + " " + title, ""])
    def p(en, russian):
        lines.extend([h(en, russian), ""])
    def table(scope, keys=None):
        keys = list(CATALOG[scope]) if keys is None else keys.split() if isinstance(keys, str) else keys
        lines.extend([h("| Parameter | Description |", "| Параметр | Описание |"), "| --- | --- |"])
        for key in keys:
            item = entry(scope, key)
            if item is None:
                raise ValueError(f"Undocumented parameter: {scope}.{key}")
            lines.append(f"| **{item.label}** | {item.text(lang).replace('|', '&#124;')} |")
        lines.append("")

    section(h("Auricle · User guide", "Auricle · Руководство пользователя"), "top", 1)
    p("This reference follows the current interface. English control names are kept so you can find the same setting in the UI. Hover over a control or its caption for a short description. Help language also selects tooltip language.",
      "Справка соответствует текущему интерфейсу. Английские имена контролов сохранены, чтобы легко найти настройку в программе. Наведите курсор на контрол или его подпись для краткого описания. Язык Help также задаёт язык подсказок.")
    contents = [("quickstart", "Quickstart", "Быстрый старт"), ("composition", "Composition", "Composition — форма и аранжировка"),
                ("blocks", "Blocks", "Blocks — типы блоков"), ("parameters", "Block parameters", "Параметры блоков"),
                ("generators", "Generators", "Генераторы"), ("drums", "Drum Kit", "Drum Kit и связи голосов"),
                ("strum", "CHORD / PAD · Strum", "CHORD / PAD · Strum"),
                ("motifs", "Motifs", "Мотивы"), ("mutators", "Mutators", "Мутаторы"), ("processes", "Process Layers", "Process Layers"),
                ("relations", "Relations / Dialogue", "Relations / Dialogue"), ("performance", "Perform / Global", "Perform / Global"),
                ("expression", "MIDI expression", "MIDI Expression"), ("midi", "MIDI Learn / Sync", "MIDI Learn / Sync"),
                ("piano-roll", "Monitor / Piano roll", "Monitor / Piano roll"),
                ("parameter-automation", "Parameter automation", "Автоматизация параметров"),
                ("troubleshooting", "Troubleshooting", "Диагностика")]
    lines += [f"- [{h(en, russian)}](#{anchor})" for anchor, en, russian in contents]
    lines.append("")
    section(h("Quickstart", "Быстрый старт"), "quickstart")
    for n, (en, russian) in enumerate([
        ("Connect a MIDI output to a receiving synth, sampler or DAW; Auricle generates MIDI, not audio.", "Выберите MIDI-выход к синтезатору, сэмплеру или DAW. Auricle генерирует MIDI, а звук создаёт принимающий инструмент."),
        ("Add a DRUM or pitched block. Set its channel, note/root, algorithm and density. Use header Play to audition Blocks.", "Добавьте DRUM или тональный блок. Настройте канал, ноту/корень, алгоритм и плотность. Главный Play прослушивает Blocks."),
        ("Edit source material in Generator, then shape Structure, Timing, Musical and Mutation. Process Layers transform streams; Relations connect instruments.", "Редактируйте источник в Generator, затем Structure, Timing, Musical и Mutation. Process Layers преобразуют потоки; Relations связывают инструменты."),
        ("In Composition add sections, set their bars, macro overrides and instrument Active/Density/Velocity. Start with Composition Play.", "В Composition добавьте секции, задайте такты, переопределения макросов и Active/Density/Velocity инструментов. Запустите Composition Play."),
        ("Save the project. Undo/Redo includes arrangement and parameter edits; Panic releases stuck notes.", "Сохраните проект. Undo/Redo охватывает аранжировку и параметры; Panic отпускает зависшие ноты."),
    ], 1):
        lines.append(f"{n}. {h(en, russian)}")
    lines.append("")
    table("project")
    p("Units: one beat is a quarter note; the ordinary base step is 0.25 beat (a sixteenth). MIDI channels are 1–16; note/controller values are 0–127. A value of zero is a rest in rhythm/Pattern material, but can be a valid root degree in pitch generators.",
      "Единицы: одна доля — четверть; обычный базовый шаг — 0.25 доли (шестнадцатая). MIDI-каналы — 1–16, ноты и значения контроллеров — 0–127. Ноль означает паузу в ритме/Pattern, но может быть полноценной корневой ступенью высотного генератора.")
    section(h("Composition · form and arrangement", "Composition · форма и аранжировка"), "composition")
    p("Composition schedules musical settings over sections on the same transport as Blocks. The form overview stays visible while SECTION, INSTRUMENTS and GLOBAL edit different scopes. Selecting a section changes the editor only. Header Play auditions Blocks without section automation or Perform; Composition Play starts the authored form.",
      "Composition распределяет музыкальные настройки по секциям на общем с Blocks транспорте. Обзор формы остаётся видимым; SECTION, INSTRUMENTS и GLOBAL редактируют разные уровни. Выбор секции меняет только редактор. Главный Play прослушивает Blocks без секционной автоматизации и Perform; Composition Play запускает подготовленную форму.")
    table("composition", "enabled meter play_button stop_button play_from ending section_list timeline total_label section_type_add add_button duplicate_button up_button down_button remove_button parameter_list_toggle")
    section(h("SECTION · identity and time", "SECTION · имя и время"), "composition-section", 3)
    table("composition", "section_name section_type section_bars transition_bars color_button apply_preset_button")
    p("Intro, Verse, Build, Drop, Break, Bridge, Transition and Outro supply starter settings. A single 8-bar Main section can be used as a simple loop. The section Duration and Composition Meter define its actual time; changing header LENGTH changes source material, not the form.",
      "Intro, Verse, Build, Drop, Break, Bridge, Transition и Outro дают стартовые настройки. Одну 8-тактовую Main можно использовать как простой цикл. Реальное время определяют Duration секции и Meter Composition. LENGTH в заголовке меняет исходный материал, а не форму.")
    section(h("SECTION · macros and curves", "SECTION · макросы и кривые"), "composition-macros", 3)
    table("macro")
    table("composition_curve")
    p("Override off → follows live Global. Override on + Curve off → fixed section value. Override on + Curve on → section curve. Blend in interpolates from the preceding section's final macro values into the incoming section, including a looping seam. The first start of the form begins at its own initial values. Blend in affects macros; it neither overlaps sections nor fades every local instrument coefficient.",
      "Override выключен → текущий Global. Override включён, Curve выключен → постоянное значение секции. Оба включены → кривая секции. Blend in интерполирует финальные макросы предыдущей секции во входящие значения, включая стык повтора. Первый запуск формы начинается с её собственных начальных значений. Blend in действует на макросы: секции не перекрываются и все локальные коэффициенты инструментов не затухают автоматически.")
    section(h("SECTION · Phrase", "SECTION · Phrase"), "composition-phrase", 3)
    table("section_phrase")
    p("A phrase is a sequence of stages; stage previews show the assigned techniques. Fit proportionally distributes those stages over the section. With Fit off the phrase finishes after Duration and fades out its layer. A local instrument technique with Fit off behaves differently: its endpoint remains held until the section ends. Section boundaries/seek re-establish the appropriate section assignments.",
      "Фраза состоит из этапов; превью этапов показывает назначенные приёмы. Fit пропорционально распределяет этапы по секции. Без Fit фраза заканчивается по Duration и плавно освобождает свой слой. Локальный приём инструмента без Fit ведёт себя иначе: его конец удерживается до завершения секции. При смене секции и перемотке восстанавливаются соответствующие секционные назначения.")
    section(h("INSTRUMENTS · local settings", "INSTRUMENTS · локальные настройки"), "composition-instruments", 3)
    table("section_instrument")
    table("composition", "details_toggle section_midi_override")
    p("Active and coefficients belong to the selected section; Mode and Mute are global. Card edits for DRUM fan out to all its voices; Details/Voices can differentiate individual voices. Density = 0 or Active off reliably silences that entity in the section. Register Center offsets the manual center before final scale/harmony placement; it preserves pitch classes through octave placement and does not retune fixed drum notes.",
      "Active и коэффициенты принадлежат выбранной секции; Mode и Mute глобальны. Карточка DRUM изменяет все его голоса; Details/Voices позволяет различить отдельные голоса. Density = 0 или выключенный Active отключает инструмент в секции. Register Center смещает ручной центр до финального размещения по гамме/гармонии, сохраняя классы высоты октавным размещением; фиксированные ноты ударных не перестраиваются.")
    section(h("GLOBAL · project-wide music", "GLOBAL · общие музыкальные настройки"), "composition-global", 3)
    p("Musical Director and Harmonic Plan apply across the project. They do not become section-local when another section is selected. Manual performance audition opens standalone Perform controls; it starts only from an explicit audition action. Use section Phrase/Technique assignments for a reproducible arrangement.",
      "Musical Director и Harmonic Plan действуют на весь проект. Выбор другой секции не делает их локальными. Manual performance audition открывает отдельный Perform и запускается только явным действием прослушивания. Для воспроизводимой аранжировки используйте секционные Phrase/Technique.")
    section(h("Example · an eight-bar build", "Пример · восьмитактовое нарастание"), "composition-example", 3)
    p("Add Build, set Duration to 8 bars and Meter to 4/4 (32 quarter-note beats). Enable Energy Override + Curve, with a low start and high end. Leave Density Override off to follow Global. Keep the bass Active throughout and disable the lead in the preceding section. Assign a fitted phrase or a fitted local technique. Start from Selected section, then choose Loop form to hear the transition back. To compare the original blocks, use header Play.",
      "Добавьте Build, задайте Duration = 8 тактов и Meter = 4/4 (32 четвертные доли). Включите Energy Override + Curve: начало низкое, конец высокий. Density Override оставьте выключенным для следования Global. Бас оставьте Active, а мелодию отключите в предыдущей секции. Назначьте фразу или локальный приём с Fit. Запустите From = Selected section, затем выберите Loop form для прослушивания стыка. Исходные блоки можно сравнить главным Play.")
    section(h("Blocks · musical roles", "Blocks · музыкальные роли"), "blocks")
    for kind in BLOCK_TYPES:
        section(kind, "block-" + kind.lower(), 3)
        p(*BLOCKS[kind])
    table("identity")
    section(h("Block parameters · common layers", "Параметры блоков · общие слои"), "parameters")
    p("Only controls applicable to the current block/voice are shown. Some stored legacy fields may coexist; the explicit Pattern Density has priority over Role Density. Knob drag/wheel edits the manual value; double-click restores its default; the context menu contains MIDI Learn and influence controls where supported.",
      "Показываются параметры, применимые к выбранному блоку/голосу. В проекте могут сосуществовать прежние поля: явная Pattern Density имеет приоритет над Role Density. Перетаскивание/колесо кноба меняет ручное значение; двойной щелчок возвращает значение по умолчанию; контекстное меню содержит MIDI Learn и управление влияниями, где это поддерживается.")
    groups = [ ("Structure / Density", "fill_density event_probability anchor_strength support_probability ornament_probability structure_length structure_rotation role_density"),
               ("Timing", "timing_rate timing_swing timing_humanize timing_offset gate live_gate live_min_beats live_max_beats role_duration pad_sustain"),
               ("Pitch / Register / Harmony", "scale_root scale_name transpose octave pitch_range role_center role_width role_root_bias harmony_size harmony_spread harmony_inversion harmonic_follow harmonic_strength voice_smooth"),
               ("Role relationships", "groove_follow groove_accent groove_offset groove_mode relation_drum_source harmony_anchor relation_chord_source"),
               ("Velocity / Mutation", "velocity_base velocity_range velocity_random velocity_accent mutation_pitch mutation_rhythm mutation_velocity mutation_timing variation_seed") ]
    for i, (title, keys) in enumerate(groups):
        section(title, f"parameters-{i}", 3)
        table("block", keys)
    section(h("Generators · every source parameter", "Генераторы · все параметры источников"), "generators")
    for i, name in enumerate(GENERATORS):
        section(name, f"generator-{i}", 3)
        p(*ALGORITHMS[name])
        table("generator", GENERATOR_KEYS[name])
    section("Drum Kit", "drums")
    table("kit")
    section("Metric / Barlow", "drum-metric", 3)
    p("An independent adaptation of Sioros & Guedes, Automatic Rhythmic Performance in Max/MSP: the kin.rhythmicator (NIME 2011, pp. 88–91). No Max patch or runtime is required. Select Metric / Barlow in the rhythm engine; Settings replaces the groove map with R, M, Fragment and a probability preview. Syncopation in the common kit row is PS.",
      "Независимая адаптация принципов Sioros & Guedes, Automatic Rhythmic Performance in Max/MSP: the kin.rhythmicator (NIME 2011, с. 88–91). Патч и среда Max не требуются. Выберите движок Metric / Barlow: Settings заменяет карту грува на R, M, Fragment и график вероятностей. Общий кноб Syncopation задаёт PS.")
    p("The meter is factored into ordered strata, then Barlow indispensability ranks determine pulse weights. 3/4 uses 3×2×2, 6/8 uses 2×3×2; their twelve sixteenths therefore have different accents. Additive 7/8 is an Auricle extension: a 3×3×2 parent is shortened to the 2+2+3 grouping while preserving rank order.",
      "Размер раскладывается на упорядоченные уровни, а ранги метрической важности Барлоу определяют веса пульсов. Для 3/4 используются уровни 3×2×2, для 6/8 — 2×3×2: одинаковые двенадцать шестнадцатых получают разные акценты. Аддитивный 7/8 — расширение Auricle: сетка 3×3×2 сокращается до группировки 2+2+3 с сохранением порядка рангов.")
    p("At stratum i the weights span R^i…R^(i−1). Event probability is p=n·W^M, with n=ΣW/Σ(W^M). M=0 gives uniform probabilities with the same expected event count, including when R=0. Velocity uses a fixed reference profile independent of R; reducing M shuffles its accent distribution. The preview shows this metric model before roles, anticipation, links, fills and output thinning, so it is not an exact note-count display.",
      "На уровне i веса занимают диапазон R^i…R^(i−1). Вероятность события p=n·W^M, где n=ΣW/Σ(W^M). При M=0 вероятности выравниваются с сохранением ожидаемого числа событий, в том числе при R=0. Velocity берётся из фиксированного опорного профиля независимо от R; снижение M перемешивает распределение акцентов. График показывает метрическую модель до ролей, упреждений, связей, сбивок и прореживания выхода, поэтому не является счётчиком итоговых нот.")
    p("Auricle orchestrates this model by role: kick owns the downbeat, snare/clap emphasize the backbeat, hats are denser and tom activity follows Toms. Complexity raises secondary activity. Half-time moves the principal snare accent to the bar midpoint; Broken changes percussion placement. Free voices remain independent. Master Density, voice probabilities and processing still shape the audible result.",
      "Auricle оркеструет модель по ролям: бочка выделяет начало такта, snare/clap — бэкбит, хэты играют плотнее, а активность томов следует Toms. Complexity повышает второстепенную активность. Half-time переносит главный акцент снейра к середине такта; Broken меняет размещение перкуссии. Голоса Free независимы. Master Density, вероятности голосов и обработка продолжают влиять на слышимый результат.")
    p("PS anticipates a pulse by exactly one sixteenth, carrying its probability and accent. Fragment caps consecutive anticipations; after the cap the next metric group resolves normally. A shorter run may suppress the immediately following stress. Collisions merge into one hit, and the first pulse of every bar remains a resolution point. This boundary rule is an Auricle adaptation that prevents notes escaping into the previous section or loop. PS=1 therefore cannot rotate the whole bar. Keep beat protects the resulting plan rather than recreating an anticipated source beat.",
      "PS переносит пульс ровно на одну шестнадцатую раньше вместе с его вероятностью и акцентом. Fragment ограничивает последовательные упреждения; после достижения предела следующая метрическая группа разрешается обычным ударом. Короткая серия может приглушить ближайшую следующую сильную долю. Совпавшие события объединяются в один удар, а первый пульс каждого такта остаётся точкой разрешения. Это правило границы — адаптация Auricle, предотвращающая выход нот в предыдущую секцию или петлю. Поэтому PS=1 не превращается в поворот всего такта. Keep beat защищает итоговый план и не восстанавливает исходную долю после упреждения.")
    p("Motifs, Development, Return, Composition cadences, voice links and shared fills also apply to Metric. Variation zero repeats stochastic choices in Theme/Return; optional Motifs can still develop the phrase. Replay, seeking and New variant remain deterministic. R and M use 0–1 automation; Fragment uses integer 1–8 sixteenths. MIDI Learn and the normal parameter-influence highlight work on all three controls.",
      "Мотивы, Development, Return, кадансы Composition, связи голосов и общие сбивки действуют и в Metric. Variation 0 повторяет вероятностный выбор в Theme/Return; включённые Motifs всё равно могут развивать фразу. Повтор, переход к позиции и New variant остаются воспроизводимыми. Автоматизация R и M использует диапазон 0–1, Fragment — целые 1–8 шестнадцатых. Для трёх параметров работают MIDI Learn и обычная подсветка влияний.")
    section(h("Drum Voice · Ratchet + Flam", "Drum Voice · Ratchet + Flam"), "drum-articulation", 3)
    table("articulation")
    p("Select a Drum Voice and open DRUM ARTICULATION in its Block Inspector. Settings belong to that voice. Both Chance knobs default to zero, preserving existing projects. Ratchet and Flam act after voice/kit processing, source probability and Composition gates, in SEQ, LIVE, Perform and every Coordinated Kit engine, including Metric / Barlow. They use the fixed voice MIDI note and route.",
      "Выберите Drum Voice и откройте DRUM ARTICULATION в Block Inspector. Настройки относятся к этому голосу. Оба Chance по умолчанию равны нулю, поэтому существующие проекты звучат как прежде. Ratchet и Flam действуют после обработки голоса/Kit, вероятности источника и допуска Composition, в SEQ, LIVE, Perform и во всех движках Coordinated Kit, включая Metric / Barlow. Они сохраняют фиксированную MIDI-ноту и маршрут голоса.")
    p("Ratchet Count includes the first principal. With Flam, the grace sounds on the original onset and the principal follows after Gap: this causal rule works identically in SEQ and LIVE without looking ahead. Only that first principal receives a grace, so a source hit produces at most nine notes. Gaps, onsets and gates follow musical time across BPM edits; short gates prevent repeat overlap.",
      "Count включает первый основной удар. При Flam предудар звучит на исходной позиции, а основной следует через Gap: это причинное правило одинаково работает в SEQ и LIVE без опережающего расчёта генератора. Предудар добавляется только к первому основному удару, поэтому один исходный удар создаёт максимум девять нот. Gap, моменты начала и длительности следуют музыкальному времени при смене BPM; короткие gate предотвращают наложение повторов.")
    p("All seven knobs support MIDI Learn, parameter-influence dots and Composition Set/Add/Multiply automation in their native ranges. Source/Plan grids remain the accepted trigger pattern; MIDI Monitor and piano-roll history receive the actual emitted sub-hits. An articulation snapshots its settings at the source hit; new values shape the next hit. Ratchet Chance zero also cancels outstanding repeats. Stop, Panic, Mute, seek, routing/mode changes and Composition section/loop boundaries cannot leak old queued notes; late worker ticks discard overdue repeats instead of catching up with a burst.",
      "Все семь кнобов поддерживают MIDI Learn, точки подсветки влияний и автоматизацию Composition Set/Add/Multiply в своих диапазонах. Сетки Source/Plan сохраняют рисунок принятых триггеров; MIDI Monitor и история piano roll получают фактически выданные подудары. Группа фиксирует настройки при принятии исходного удара; новые значения формируют следующий удар. Ratchet Chance 0 дополнительно отменяет оставшиеся повторы. Stop, Panic, Mute, переход к позиции, смена маршрута/режима и границы секций/петли Composition не пропускают старые ноты из очереди; при задержке рабочего потока просроченные повторы пропускаются без пачки догоняющих ударов.")
    section(h("Internal voice links", "Внутренние связи голосов"), "drum-links", 3)
    table("kit_link")
    p("Delay is causal time; Phase is cyclic placement. Links read a frozen candidate plan, so cycles remain deterministic and anchors/fills remain protected. A musical kit preset enables Rhythm map, motifs and suggested links while preserving generators, processing and MIDI routes. Auto roles infers names/GM notes without changing routes. Copy/Paste sound preserves voice identity, role, mode, mute and routing; Undo paste restores the previous sound.",
      "Delay — причинная задержка; Phase — циклическое размещение. Связи читают зафиксированный исходный план: циклы остаются детерминированными, опоры/сбивки защищены. Музыкальный пресет Kit включает Rhythm map, мотивы и предложенные связи, сохраняя генераторы, обработку и MIDI-маршруты. Auto roles определяет роли по именам/GM-нотам без изменения маршрутов. Copy/Paste sound сохраняет идентичность, роль, режим, Mute и маршрут голоса; Undo paste возвращает прежний звук.")
    p("Plan shows the coordinated candidate plan; Output shows accepted generator output, not incoming MIDI feedback; Source shows generator material. Length edits source steps (up to 128); paging shows up to 32 steps at once.",
      "Plan показывает согласованный исходный план; Output — принятый выход генератора, а не входящую MIDI-обратную связь; Source — материал генератора. Length меняет длину источника до 128 шагов; на одной странице видно до 32 шагов.")
    section("CHORD / PAD · Strum", "strum")
    table("strum")
    p("STRUM in the CHORD/PAD Block Inspector plays the finished voicing one note at a time. It runs after source probability, register/voicing, Dialogue and Composition processing, and uses the existing musical event scheduler in SEQ, LIVE, Perform and Composition. Chance defaults to zero, so existing projects retain their simultaneous chord output. Single-note events are unchanged.",
      "STRUM в Block Inspector для CHORD/PAD проигрывает готовый voicing по одной ноте. Он действует после вероятности источника, регистра/voicing, Dialogue и обработки Composition, используя существующий планировщик музыкальных событий в SEQ, LIVE, Perform и Composition. Chance по умолчанию равен нулю: существующие проекты сохраняют одновременные аккорды. Однонотные события не меняются.")
    p("Up and Down sort actual MIDI pitches after inversion, spread and voice leading. Alternate uses the absolute source-step parity; rests advance that parity too, so seeking needs no playback history. Random, chance and Humanize are reproducible for the same seed, block and source beat. Strum preserves chord tones and removes duplicate physical MIDI notes caused by clipping.",
      "Up и Down сортируют фактическую MIDI-высоту после обращения, spread и голосоведения. Alternate использует чётность абсолютного шага источника; паузы тоже продвигают этот шаг, поэтому для перехода к позиции не нужна история проигрывания. Random, Chance и Humanize воспроизводимы при одинаковых seed, блоке и позиции источника. Strum сохраняет ноты аккорда и убирает дубли физических MIDI-нот, возникающие при ограничении диапазона.")
    p("Gap is a requested interval in quarter-note beats, not milliseconds. A strum occupies at most 90% of the available source interval/gate or the remaining harmony/Dialogue window; wider settings compress automatically. Humanize keeps notes ordered. Shared end shortens later notes to the original chord deadline, even after a late worker tick or BPM change. Per note retains each note's source duration, allowing legato overlap as configured by Gate. Harmonic cutoffs still take precedence.",
      "Gap — запрошенный интервал в четвертных долях, а не в миллисекундах. Перебор занимает максимум 90% доступного интервала/gate источника либо оставшегося окна гармонии/Dialogue; более широкие настройки автоматически сжимаются. Humanize сохраняет порядок нот. Shared end укорачивает поздние ноты до исходного конца аккорда, в том числе после задержки рабочего потока или смены BPM. Per note сохраняет исходную длительность каждой ноты, позволяя legato-перекрытие согласно Gate. Граница гармонии имеет приоритет.")
    p("The four knobs support MIDI Learn and continuous Composition automation in native ranges. Direction and Gate support discrete Composition assignments through their context menu; source dots show active influences and the selectors show the effective choice without editing the manual value. Settings and voicing are captured once per accepted chord; later edits affect the next chord. Stop, Panic, Mute, seek, routing/mode/type changes and Composition section/loop changes cancel old pending tones. MIDI Monitor and piano-roll history receive individual emitted notes; source/plan buffers remain unchanged.",
      "Четыре кноба поддерживают MIDI Learn и непрерывную автоматизацию Composition в своих диапазонах. Direction и Gate поддерживают дискретные назначения Composition через контекстное меню; точки показывают действующие влияния, а селекторы — эффективный выбор без изменения ручного значения. Настройки и voicing фиксируются один раз на принятый аккорд; последующие правки относятся к следующему аккорду. Stop, Panic, Mute, переход к позиции, смена маршрута/режима/типа и границы секции/петли Composition отменяют старые отложенные тона. MIDI Monitor и история piano roll получают отдельные выданные ноты; буферы Source/Plan не меняются.")
    section(h("Motifs", "Мотивы"), "motifs")
    table("motif")
    section(h("Mutators", "Мутаторы"), "mutators")
    table("mutation")
    table("mutation_type")
    p("Stack order matters. Target-specific Mutation blends the transformed result with the original, preserving the operation's neutral point. Compatibility limits the menu: Transpose/Octave operate on pitch; Threshold on velocity/timing; Probability on rhythm/velocity/timing. Timing mutators transform gate, whereas Timing Humanize/Offset move note onsets.",
      "Порядок стека влияет на результат. Mutation цели смешивает результат с оригиналом, сохраняя нейтральную точку операции. Меню учитывает совместимость: Transpose/Octave — высота; Threshold — velocity/timing; Probability — rhythm/velocity/timing. Мутаторы Timing преобразуют gate, а Timing Humanize/Offset сдвигают начало нот.")
    section("Process Layers", "processes")
    p("Processes read/transform musical streams after generation and mutators; they are not audio effects. Delay values are source steps, not milliseconds. Clock primitives reshape the stream and do not change BPM. Reorder the stack to change the result.",
      "Процессы читают и преобразуют музыкальные потоки после генератора и мутаторов; это не аудиоэффекты. Delay измеряется исходными шагами, не миллисекундами. Clock-операции меняют поток, сохраняя BPM. Порядок процессов влияет на результат.")
    table("process", "type target amount")
    for i, name in enumerate(PROCESS_TYPES):
        section(name, f"process-{i}", 3)
        p(*PROCESSES[name])
        table("process." + name, PROCESS_KEYS[name])
    section("Relations / Dialogue", "relations")
    table("relation")
    section(h("Dialogue · call and response", "Dialogue · вопрос и ответ"), "dialogue", 3)
    table("dialogue")
    p("Cycle = Call + Gap + Response + Gap. Separation 1 enforces alternating turns; 0 bypasses separation. Cycle chance is tested once per whole cycle. Dialogue requires distinct instrument owners; a Drum Voice belongs to its kit. If an instrument appears in multiple Dialogue pairs, the earlier pair wins. Ordinary Relations use explicit streams, and cyclic graphs use delayed history rather than recursive same-pass updates.",
      "Цикл = Call + Gap + Response + Gap. Separation = 1 обеспечивает чередование; 0 обходит разделение. Cycle chance проверяется один раз на весь цикл. Нужны разные инструменты-владельцы: Drum Voice принадлежит своему Kit. Если инструмент входит в несколько пар Dialogue, приоритет у более ранней пары. Обычные Relations используют явные потоки; циклические графы читают задержанную историю без рекурсивного обновления в одном проходе.")
    section("Perform / Global", "performance")
    table("perform")
    table("macro_route")
    table("director")
    table("harmony")
    section(h("Parameter influence and knob feedback", "Влияния на параметры и индикация кнобов"), "influence", 3)
    table("influence")
    p("The manual base remains available while Perform, Composition or Relations contribute. Source dots distinguish assigned and active influences. The needle may display the effective parameter or an output-equivalent value; the short outer tick retains the manual setting. An output-equivalent indication summarizes event-level shaping rather than rewriting every block parameter.",
      "Ручная основа сохраняется при влиянии Perform, Composition и Relations. Цветные точки различают назначенное и активное влияние. Стрелка может показывать эффективный параметр или эквивалент влияния на выход; короткая внешняя риска хранит ручную установку. Эквивалент выхода суммирует обработку событий, не переписывая каждый параметр блока.")
    section(h("Common techniques", "Общие исполнительские приёмы"), "techniques", 3)
    lines += [h("| Technique | Action | Parameters |", "| Приём | Действие | Параметры |"), "| --- | --- | --- |"]
    for preset in (*COMMON, KIT_EVOLUTION):
        desc = _TECH_RU[preset.id] if ru else preset.description
        lines.append(f"| **{preset.name}** | {desc} | " + ", ".join(f"`{move.parameter}`" for move in preset.moves) + " |")
    lines.append("")
    section(h("Algorithm techniques", "Приёмы алгоритмов"), "algorithm-techniques", 3)
    p("These gestures automate the listed generator parameters. Amount, shape and duration control how far and how quickly the listed values change. Their parameter descriptions are in the generator reference above.",
      "Эти приёмы автоматизируют перечисленные параметры генератора. Amount, форма и длительность задают глубину и скорость изменения. Значение каждого параметра описано в справочнике генераторов выше.")
    lines += ["| Algorithm / Technique | " + h("Parameter movement", "Изменение параметров") + " |", "| --- | --- |"]
    for name, presets in ALGORITHM_GESTURES.items():
        for preset in presets:
            movement = "; ".join(f"`{m.parameter}`: {m.start:g} → {m.end:g}" for m in preset.moves)
            lines.append(f"| {name} / **{preset.name}** | {movement} |")
    lines.append("")
    section(h("Phrase catalog", "Каталог Phrase"), "phrases", 3)
    lines += ["| Phrase | " + h("Stages", "Этапы") + " |", "| --- | --- |"]
    for phrase in PHRASES:
        stages = " → ".join(f"{(stage.label or stage.technique_id)} ({stage.beats:g} b)" for stage in phrase.stages)
        lines.append(f"| **{phrase.name}** | {stages} |")
    lines.append("")
    section("MIDI Expression · CC / Pitch Bend / Aftertouch", "expression")
    p("These are outgoing MIDI controls sampled from the shared musical clock, independent of note generation. A receiving instrument must support the messages. Block expression may be inherited by Drum Voices; Composition can override it per section and entity. Curves use normalized coordinates; their actual scale is set by the lane.",
      "Это выходные MIDI-контролы, считываемые по общим музыкальным часам независимо от генерации нот. Принимающий инструмент должен поддерживать сообщения. Drum Voice может наследовать Expression набора; Composition может переопределить её для секции и инструмента. Координаты кривых нормированы; фактический диапазон задаётся линией.")
    table("midi_expression")
    section("MIDI Learn / Sync", "midi")
    table("midi_learn")
    p("Open MIDI IN, connect the input, then use a supported knob's context menu → MIDI Learn. CC, note velocity, pitch wheel, channel pressure and polyphonic pressure can be learned. Up to 512 mappings are stored in the project. Learning captures a mapping; subsequent movement applies it. The application does not automatically decode every relative encoder protocol.",
      "Откройте MIDI IN, подключите вход, затем выберите MIDI Learn в контекстном меню поддерживаемого кноба. Обучаются CC, velocity ноты, Pitch Wheel, Channel Pressure и Polyphonic Pressure. В проекте хранится до 512 назначений. Захват создаёт назначение; последующее движение применяет его. Программа не декодирует автоматически все протоколы относительных энкодеров.")
    table("midi_sync")
    section("Monitor / Piano roll", "piano-roll")
    p("The horizontal scale uses Length (steps), independent of the source pattern. During playback the right edge is the current time; old events leave the fixed window. When stopped or frozen the time anchor holds. At 120 BPM, 16 steps span 2 seconds; 64 steps span 8 seconds. Without MIDI history the generated preview uses the same fixed length and clips steps outside it. Selecting a Drum Voice monitors that voice; selecting the kit combines its voices.",
      "Горизонтальный масштаб задаёт Length (steps) независимо от исходного паттерна. Во время воспроизведения правый край — текущее время; старые события покидают фиксированное окно. При Stop и Freeze время окна останавливается. При 120 BPM 16 шагов занимают 2 секунды, 64 — 8 секунд. Без истории MIDI превью генератора использует ту же длину и обрезает шаги за её пределами. При выборе Drum Voice отображается этот голос, при выборе Kit — совокупная история голосов.")
    table("piano_roll")
    p("During playback the roll shows dispatched notes, not source triggers: every emitted Ratchet repeat, the causal Flam grace/principal pair and each shifted Strum tone. Bar widths follow actual MIDI Note Off, including retrigger, choke, Mute and Stop; held notes grow only to the current view anchor. Onset and release times are captured before the GUI queue. The grid follows quarter-note beats across tempo changes; the seconds caption is the equivalent span at the current tempo. Hover a note for pitch, velocity, onset, length, channel and source offset. Canceled and skipped sub-hits are absent. MIDI Monitor may remain off.",
      "Во время воспроизведения roll показывает выданные ноты: каждый фактический повтор Ratchet, причинную пару предудар/основной удар Flam и отдельные сдвинутые тона Strum. Ширина следует фактическому MIDI Note Off, включая повторный запуск, choke, Mute и Stop; удерживаемые ноты растут только до текущего края окна. Время начала и окончания фиксируется до очереди UI. Сетка следует четвертным долям при смене темпа; секунды в заголовке — эквивалент длины окна при текущем темпе. Наведение показывает высоту, velocity, начало, длину, канал и сдвиг относительно источника. Отменённые и пропущенные подудары отсутствуют. MIDI Monitor можно оставить выключенным.")
    p("Without a physical MIDI port the roll labels accepted generated notes separately and uses their planned gates. Before the first playback it previews the current buffers through the same Ratchet/Flam/Strum expansion; this preview cannot predict later section changes, Dialogue or random gates. Source buffers remain unchanged. Freeze preserves an immutable snapshot, including sounding tails and the musical anchor, through Inspector rebuilds. Play/seek starts a fresh unfrozen capture; a frozen snapshot remains until released. History is bounded to 8192 notes per owner and 32768 total.",
      "Без физического MIDI-порта roll отдельно обозначает принятые события генератора и использует их запланированные окончания. До первого запуска текущие буферы проходят те же функции Ratchet/Flam/Strum для превью; оно не предсказывает последующие секции, Dialogue и случайные фильтры. Исходные буферы сохраняются. Freeze удерживает неизменяемый снимок, включая звучащие хвосты и музыкальную позицию, при пересоздании Inspector. Play/перемотка начинает новую незамороженную историю; замороженный снимок остаётся до снятия Freeze. История ограничена 8192 нотами на владельца и 32768 суммарно.")
    section(h("Composition · parameter automation", "Composition · автоматизация параметров"), "parameter-automation")
    p("AUTOMATION edits exact block/voice parameters for the selected section. Right-click a knob or source caption and choose Automate in Composition. The action creates or opens a lane, preserves the manual base and leaves playback unchanged. Composition Play applies lanes; Blocks/Perform playback and stopped editing do not. Green source dots show assigned and contributing Composition layers.",
      "AUTOMATION задаёт точные параметры блоков/голосов для выбранной секции. Правый щелчок по кнобу или подписи источника → Automate in Composition создаёт или открывает дорожку, сохраняет ручную основу и не меняет воспроизведение. Дорожки действуют при Composition Play; при Blocks/Perform и остановленном редактировании они не применяются. Зелёные точки показывают назначенные и действующие слои Composition.")
    table("automation")
    p("Default priority is Composition → Technique → Modulation → Macro; partial weights reveal lower layers. Old source orders are preserved below the new Composition category. Numeric targets clamp and round after resolution. Choices/text always use stable source priority, including in blend mode. Continuous SEQ generation is batched to sixteenth-note boundaries; source-cycle timing captures the manual cycle at section entry. Stop/bypass removes automation and reveals the latest manual base. Section entry, looping and seek evaluate musical position without replaying earlier UI edits.",
      "Приоритет по умолчанию: Composition → Technique → Modulation → Macro; неполные веса пропускают нижние слои. Прежний порядок источников сохраняется под новой категорией Composition. Числа ограничиваются диапазоном и округляются после разрешения влияний. Списки/текст всегда выбираются по устойчивому приоритету, включая режим blend. Генерация SEQ объединяется на границах шестнадцатых; Source cycle фиксирует ручной цикл при входе в секцию. Stop/обход снимает автоматизацию и возвращает последнюю ручную основу. Вход в секцию, цикл формы и перемотка вычисляют музыкальную позицию без повторного исполнения прежних UI-правок.")
    p("Ratchet/Flam can target individual Drum Voices or single Drum/Percussion blocks; Strum targets CHORD/PAD. Use the family filter to find them. Each section stores its own Value, Section curve or Macro response assignment. Strum Direction/Gate are Value snapshots at musical boundaries. Numeric output uses native units: Ratchet Count is 1–8 hits, Flam Gap is 0.01–0.12 beats, Strum Spacing is 0–0.5 beats and Strum Dynamics is −1…+1. These controls affect future accepted events without rebuilding source patterns or resetting LIVE phase; scheduled hits keep their existing settings.",
      "Ratchet/Flam назначаются отдельным Drum Voices либо одиночным Drum/Percussion; Strum — CHORD/PAD. Найти их помогает фильтр семейства. Каждая секция хранит своё назначение Value, Section curve или Macro response. Strum Direction/Gate задаются снимками Value на музыкальных границах. Выход использует единицы параметра: Ratchet Count — 1–8 ударов, Flam Gap — 0.01–0.12 доли, Strum Spacing — 0–0.5 доли, Strum Dynamics — −1…+1. Настройки действуют на будущие принятые события без пересборки паттернов и сброса фазы LIVE; запланированные удары сохраняют прежние настройки.")
    p("Energy/Tension links are explicit: choose Macro response and its Source, or right-click an articulation control and choose Composition: link Energy/Tension. The input is the effective section macro, including section macro curves and Blend transitions. X is input 0–100%; Y is the selected target range. Reverse input evaluates 1−input. Set writes the mapped target; Add/Multiply apply an offset/factor to the latest manual base, then clamp and round. Weight and Parameter influences use the existing Composition policy and green highlights. Held timing samples the macro only at the selected boundary. Stop, disabled lanes and section changes release the layer. Section and response curves are stored separately, so switching modes preserves both.",
      "Связи Energy/Tension назначаются явно: выберите Macro response и Source либо правый щелчок по артикуляции → Composition: link Energy/Tension. Вход — действующий макрос секции с её кривой и переходом Blend. X — вход 0–100%; Y — выбранный диапазон цели. Reverse input вычисляет 1−вход. Set задаёт полученную цель; Add/Multiply прибавляют смещение/применяют множитель к последней ручной основе с последующим ограничением и округлением. Weight и Parameter influences используют существующую политику Composition и зелёную подсветку. Удерживаемая привязка считывает макрос только на выбранной границе. Stop, отключение дорожки и смена секции снимают слой. Кривая времени и кривая отклика сохраняются отдельно: переключение режима сохраняет обе.")
    section(h("Troubleshooting", "Диагностика"), "troubleshooting")
    for en, russian in [
        ("No sound: check receiving instrument, MIDI output/channel/note, global Mute, section Active and Density, event probability, Dialogue turn and velocity. MIDI Monitor confirms outgoing messages.", "Нет звука: проверьте принимающий инструмент, MIDI-выход/канал/ноту, глобальный Mute, Active и Density секции, вероятность событий, очередь Dialogue и velocity. MIDI Monitor подтверждает исходящие сообщения."),
        ("A section does not affect playback: start with Composition Play; confirm Enable composition and the desired From position. Selecting a section alone does not seek.", "Секция не влияет: запускайте Composition Play; проверьте Enable composition и From. Выбор секции сам по себе не перематывает форму."),
        ("A macro slider seems ignored: check Override, Curve, live Global and influence policy. A curve replaces the scalar slider while enabled.", "Ползунок макроса не действует: проверьте Override, Curve, текущий Global и политику влияний. Включённая кривая заменяет постоянный ползунок."),
        ("A learned control moves late: with Pickup enabled, cross the manual setting once. MIDI IN Diagnostics / Copy diagnostics shows input, GUI, pickup, queued and applied stages.", "Обученная ручка реагирует поздно: при Pickup один раз пересеките ручное значение. MIDI IN → Diagnostics / Copy diagnostics показывает этапы входа, GUI, pickup, очереди и применения."),
        ("Unexpected pitch: check semitone Transpose versus degree offset, Register Center, scale and Harmonic Plan. Drum Voice note selection remains separate.", "Неожиданная высота: сравните Transpose в полутонах и смещение ступеней, Register Center, гамму и Harmonic Plan. Выбор ноты Drum Voice независим."),
        ("Stuck notes: use Panic/Stop and inspect the receiver's sustain state. For sluggish UI, turn off unnecessary monitor traffic and reduce expensive Geometry Substeps or oversized processing stacks.", "Зависли ноты: используйте Panic/Stop и проверьте Sustain принимающего инструмента. При медленном UI отключите лишний поток монитора, уменьшите дорогой Geometry Substeps или избыточный стек обработки."),
    ]:
        lines.append("- " + h(en, russian))
    lines += ["", h("[Back to contents](#top)", "[К оглавлению](#top)"), ""]
    return "\n".join(lines)


def help_html(language="en"):
    """Compatibility for integrations; the application renders Markdown directly.

    Render only the small, controlled Markdown subset emitted above. This stays
    independent of QApplication and adds no Markdown dependency at startup.
    """
    def inline(value):
        value = escape(value)
        value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
        value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
        return re.sub(r"\[([^]]+)\]\((#[^)]+)\)", r'<a href="\2">\1</a>', value)
    out, in_table = [], False
    for line in help_markdown(language).splitlines():
        if not line.startswith("|") and in_table:
            out.append("</table>"); in_table = False
        if line.startswith('<a name="'):
            out.append(line)
        elif line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            out.append(f"<h{level}>{inline(line[level:].strip())}</h{level}>")
        elif line.startswith("| ---"):
            continue
        elif line.startswith("|"):
            if not in_table:
                out.append('<table border="1" cellspacing="0" cellpadding="6">'); in_table = True
            out.append("<tr>" + "".join(f"<td>{inline(cell.strip())}</td>" for cell in line.strip("|").split("|")) + "</tr>")
        elif line:
            out.append("<p>" + inline(line) + "</p>")
    if in_table:
        out.append("</table>")
    return "<html><body>" + "\n".join(out) + "</body></html>"
