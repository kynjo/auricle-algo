"""Bilingual Auricle user guide content.

UI imports this module instead of embedding the documentation in auricle_gui.py.
"""
from performance_presets import COMMON, ALGORITHM_GESTURES, PHRASES

ALGORITHMS = {
    "Euclidean": ("Euclidean rhythm distributes a chosen number of hits as evenly as possible across a cycle. Use Steps, Pulses and Rotation to move the accent pattern without changing its density.", "Ритм Евклида распределяет заданное число ударов максимально равномерно по циклу. Используйте Steps, Pulses и Rotation, чтобы менять рисунок акцентов, не меняя общую плотность."),
    "Bresenham": ("Bresenham treats rhythm as a discrete line-rasterization problem. It is useful for clean, mechanical distributions of events across a loop.", "Bresenham рассматривает ритм как дискретную растеризацию линии. Подходит для чётких механических распределений событий по циклу."),
    "Polyrhythm": ("Polyrhythm combines two independent cycles. Cycle A and Cycle B can create interference patterns whose combined period is longer than either source cycle.", "Polyrhythm объединяет два независимых цикла. Cycle A и Cycle B создают интерференционные рисунки, общий период которых может быть длиннее каждого исходного цикла."),
    "Thue-Morse": ("Thue-Morse generates a recursively structured binary pattern. It produces repetition with controlled self-similarity and is useful for non-obvious rhythmic symmetry.", "Thue-Morse создаёт рекурсивно организованный бинарный рисунок. Он даёт повторение с контролируемым самоподобием и хорошо подходит для необычной ритмической симметрии."),
    "Fibonacci Rhythm": ("Fibonacci Rhythm derives event placement from Fibonacci structure. Density and offset control how strongly the sequence is exposed as rhythm.", "Fibonacci Rhythm строит расположение событий на основе структуры Фибоначчи. Density и Offset определяют, насколько явно последовательность проявляется в ритме."),
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
    "Cellular Automaton": ("Cellular Automaton evolves a state pattern through local rules over generations. Rule, generations and density determine how quickly structure becomes complex.", "Cellular Automaton развивает состояние по локальным правилам через поколения. Rule, Generations и Density определяют скорость перехода от структуры к сложности."),
    "L-System": ("L-System expands an axiom through rewriting rules. Iterations, mapping and mode turn symbolic growth into rhythm, pitch or other musical material.", "L-System расширяет аксиому по правилам переписывания. Iterations, Mapping и Mode превращают символический рост в ритм, высоту или другой музыкальный материал."),
    "Logistic Chaos": ("Logistic Chaos uses the logistic map to create deterministic but highly sensitive trajectories. Chaos R, initial state and smoothing control the degree of instability.", "Logistic Chaos использует логистическое отображение для детерминированных, но чувствительных траекторий. Chaos R, Initial X и Smooth управляют степенью нестабильности."),
}

PROCESSES = {
    "Counter": ("Adds a repeating ramp, triangle or sine control signal. Good for cyclic sweeps of pitch, density or velocity.", "Добавляет повторяющийся управляющий сигнал Ramp, Triangle или Sine. Подходит для циклических изменений pitch, density или velocity."),
    "Modulo": ("Creates a repeating modular control pattern. Use Add, Multiply or Gate modes to impose periodic structure.", "Создаёт повторяющийся модульный управляющий рисунок. Режимы Add, Multiply и Gate задают способ воздействия."),
    "Compare": ("Compares each value with a threshold and blends between true and false values. Useful for gates, accents and conditional transformations.", "Сравнивает каждое значение с порогом и смешивает true/false значения. Полезен для gate, accent и условных преобразований."),
    "Clock Divide": ("Slows a stream by periodically gating or holding events. Useful for creating slower envelopes and rhythmic subdivisions.", "Замедляет поток периодическим gate или удержанием. Полезен для медленных огибающих и ритмических делений."),
    "Clock Multiply": ("Repeats or gates a source according to a clock factor. Useful for subdivisions and denser rhythmic grids.", "Повторяет или открывает источник с заданным коэффициентом clock. Полезен для дробления и уплотнения ритмической сетки."),
    "Memory": ("Reads a previous value and blends it with the current value. Delay and feedback create persistence and smoothing.", "Читает предыдущее значение и смешивает его с текущим. Delay и Feedback создают инерцию и сглаживание."),
    "Delay": ("Adds delayed copies of a stream. Repeats, feedback and decay control the resulting echo-like structure.", "Добавляет задержанные копии потока. Repeats, Feedback и Decay управляют структурой, похожей на эхо."),
    "Feedback": ("Feeds processed output back through the process for iterative evolution. Keep feedback bounded when using pitch or velocity.", "Возвращает обработанный выход обратно в процесс для итеративного развития. Для pitch и velocity рекомендуется ограничивать feedback."),
    "Parameter Modulation": ("Reads a musical stream as a control signal for a real numeric parameter. Modulation is applied with an event delay to avoid same-pass recursive feedback.", "Читает музыкальный поток как управляющий сигнал для реального числового параметра. Модуляция применяется с задержкой события, чтобы избежать рекурсивного feedback в одном проходе."),
}


def _html(lang: str) -> str:
    ru = lang == "ru"
    def h(en, ru_text): return ru_text if ru else en
    sections = []
    sections.append(f"<h1>Auricle — {h('Algorithmic Music Generator', 'Алгоритмический музыкальный генератор')}</h1>")
    sections.append(f"<p>{h('Auricle builds music as a network of independent algorithmic blocks. Each block generates musical material, transforms it, and sends it to MIDI. The program is designed for both repeatable patterns and live, evolving generation.', 'Auricle строит музыку как сеть независимых алгоритмических блоков. Каждый блок генерирует музыкальный материал, преобразует его и отправляет в MIDI. Программа рассчитана как на повторяемые паттерны, так и на живую развивающуюся генерацию.')}</p>")
    sections.append(f"<h2>{h('Quick start', 'Быстрый старт')}</h2><ol>" + "".join(f"<li>{x}</li>" for x in ([
        'Create a block with <b>Add block</b> and choose its musical type.', 'Select an algorithm and set Fill / Density first; then tune algorithm-specific parameters.', 'Choose <b>SEQ</b> for a generated/cached pattern or <b>LIVE</b> when events should be generated during playback.', 'Adjust Musical Representation: velocity, duration, scale and root.', 'Add Mutators for controlled transformations and Process Layers for time-based or algorithmic processing.', 'Use <b>RELATIONS</b> when one block should influence another.', 'Use <b>PERFORM</b> for musical gestures, techniques and multi-block phrases.', 'Select a MIDI output, press PLAY, and use MIDI MONITOR to inspect outgoing messages.' ] if not ru else [
        'Создайте блок через <b>Add block</b> и выберите его музыкальный тип.', 'Выберите алгоритм и сначала настройте Fill / Density, затем специфические параметры алгоритма.', 'Выберите <b>SEQ</b> для сгенерированного/закэшированного паттерна или <b>LIVE</b>, если события должны генерироваться во время воспроизведения.', 'Настройте Musical Representation: velocity, duration, scale и root.', 'Добавляйте Mutators для контролируемых преобразований и Process Layers для временной/алгоритмической обработки.', 'Используйте <b>RELATIONS</b>, когда один блок должен влиять на другой.', 'Используйте <b>PERFORM</b> для музыкальных приёмов и многоблочных Phrase.', 'Выберите MIDI output, нажмите PLAY и используйте MIDI MONITOR для проверки исходящих сообщений.'])) + "</ol>")
    sections.append(f"<h2>{h('How a block works', 'Как работает блок')}</h2><p><b>Generator → Musical Representation → Mutators → Process Layers → Relations → MIDI.</b> {h('The generator creates raw material. Musical Representation interprets it as rhythm, pitch, velocity, duration, density and accent. Mutators transform the representation. Processes apply ordered transformations. Relations exchange information between blocks. The final result is converted to MIDI notes and messages.', 'Generator создаёт исходный материал. Musical Representation интерпретирует его как rhythm, pitch, velocity, duration, density и accent. Mutators преобразуют представление. Processes выполняют последовательную обработку. Relations передают информацию между блоками. Итог превращается в MIDI-ноты и сообщения.')}</p>")
    sections.append(f"<h2>{h('SEQ vs LIVE', 'SEQ и LIVE')}</h2><p>{h('<b>SEQ</b> generates a deterministic material buffer. It is ideal for loops, visual inspection and repeatable arrangements. <b>LIVE</b> emits events during transport, so parameter changes can affect upcoming events without rebuilding the whole musical phrase.', '<b>SEQ</b> создаёт детерминированный буфер материала. Он удобен для циклов, визуального контроля и повторяемых аранжировок. <b>LIVE</b> выдаёт события во время transport, поэтому изменения параметров могут влиять на следующие события без полной перестройки фразы.')}</p>")
    sections.append(f"<h2>{h('Musical roles', 'Музыкальные роли')}</h2><p>{h('<b>BASS</b> is a low-register foundation with compact motion and a controlled root/fifth bias. <b>MELODY</b> occupies a mid/high register and favors melodic articulation. <b>PAD</b> is sparse and sustained, automatically expanding events into diatonic polyphonic voicings. <b>CHORD</b> is an explicit harmonic-event role with simultaneous chord voices, spread and inversion. The same generator can therefore be reused for different musical jobs without creating separate role-specific algorithms.', '<b>BASS</b> — низовой фундамент с компактным движением и контролируемым приоритетом тоники/квинты. <b>MELODY</b> занимает средне-высокий регистр и ориентирован на мелодическую артикуляцию. <b>PAD</b> создаёт редкую, длительную гармоническую текстуру и автоматически расширяет события в диатонические аккорды. <b>CHORD</b> — явная гармоническая роль с одновременными голосами, spread и inversion. Один и тот же генератор поэтому можно использовать для разных музыкальных задач без создания отдельных алгоритмов для каждой роли.')}</p>")
    sections.append(f"<h2>{h('Algorithms', 'Алгоритмы')}</h2>")
    for name, (en, ru_text) in ALGORITHMS.items(): sections.append(f"<h3>{name}</h3><p>{ru_text if ru else en}</p>")
    sections.append(f"<h2>{h('Mutators', 'Mutators')}</h2><p>{h('Mutators transform generated material without replacing the generator. Rotate and Reverse alter order; Invert, Transpose and Octave alter pitch; Stretch and Compress alter time; Probability and Shuffle introduce controlled variation; Humanize adds small deviations; Scale constrains pitch to a scale; Threshold makes conditional changes.', 'Mutators преобразуют сгенерированный материал, не заменяя сам генератор. Rotate и Reverse меняют порядок; Invert, Transpose и Octave изменяют pitch; Stretch и Compress меняют время; Probability и Shuffle добавляют контролируемую вариативность; Humanize добавляет небольшие отклонения; Scale ограничивает pitch гаммой; Threshold выполняет условные изменения.')}</p>")
    sections.append(f"<h2>{h('Process Layers', 'Process Layers')}</h2><p>{h('Processes are ordered and composable. A process operates on one musical dimension such as rhythm, pitch, velocity, duration, density or accent. Put a shaping process before a feedback or delay process when you want the latter to react to the already-shaped signal.', 'Processes выполняются последовательно и могут комбинироваться. Каждый process работает с одним музыкальным измерением: rhythm, pitch, velocity, duration, density или accent. Если feedback или delay должны реагировать уже на обработанный сигнал, ставьте формирующий process перед ними.')}</p>")
    for name,(en,ru_text) in PROCESSES.items(): sections.append(f"<h3>{name}</h3><p>{ru_text if ru else en}</p>")
    sections.append(f"<h2>{h('Relations', 'Relations')}</h2><p>{h('A Relation is a signal path from one block output to another block input. The compact editor reads as <b>Source → Output → Relation → Destination → Input → Amount → Curve → Delay → Probability → State</b>. Use Copy for direct transfer, Mix/Follow for blending, Quantize To for quantization, Modulate for additive influence and Trigger for event-like gating.', 'Relation — это путь сигнала от выхода одного блока ко входу другого. Компактный редактор читается как <b>Source → Output → Relation → Destination → Input → Amount → Curve → Delay → Probability → State</b>. Используйте Copy для прямой передачи, Mix/Follow для смешивания, Quantize To для квантования, Modulate для добавочного влияния и Trigger для событийного gate.')}</p><p>{h('Curve shapes the influence of Amount. Delay postpones the source event. Probability makes the relation stochastic. Relations are evaluated from a snapshot, so cycles are diagnosed rather than recursively evaluated in the same pass.', 'Curve задаёт форму влияния Amount. Delay откладывает применение исходного события. Probability делает связь вероятностной. Relations вычисляются на основе snapshot, поэтому циклы диагностируются, а не вычисляются рекурсивно в одном проходе.')}</p>")
    sections.append("<p>" + h(
        'Click <b>+ Add</b> in Mutation, Process or Relations to insert an editable row immediately. Mutation type, target and amount can be changed in place. In Relations, every route has its own controls, Enabled, COPY and remove (×) buttons. Source and Destination show the block colour. Selecting a Drum Voice directs new mutations and processes to that voice.',
        'Нажмите <b>+ Add</b> в Mutation, Process или Relations: сразу появится редактируемая строка. Тип мутации, цель и Amount можно менять прямо в ней. В Relations каждая связь имеет свои настройки, Enabled, COPY и удаление (×). В Source и Destination отображается цвет блока. Если выбран Drum Voice, новые мутации и процессы добавляются к этому голосу.'
    ) + "</p>")
    sections.append(f"<h3>{h('Instrument dialogue', 'Диалог между инструментами')}</h3>")
    sections.append("<p>" + h(
        '<b>Relations → + Dialogue</b> adds call/response between Source and Destination. Set Call/Response bars, Meter and Pause in quarter-note beats. Separation 1 gives strict turns, 0 bypasses the dialogue; intermediate values soften the waiting instrument. Cycle chance applies to a whole cycle. Own phrase keeps each part, Echo follows the call contour and accents, Contrast inverts them; Follow controls the amount. Reply rhythm remains its own. CHORD/PAD/DRUM follow accents only. The timeline and Perform cards show the turn. Each block belongs to one active pair; conflicting later rows show a bypass explanation. Settings support save and Undo/Redo. See docs/INSTRUMENT_DIALOGUE_RU.md and examples/instrument_dialogue_demo.json.',
        '<b>Relations → + Dialogue</b> добавляет вопрос и ответ между Source и Destination. Настройте длины Call/Response в тактах, Meter и Pause в четвертных долях. Separation 1 даёт строгое чередование, 0 — обход, промежуточные значения делают ожидающий инструмент тише. Cycle chance действует на целый цикл. Own phrase сохраняет собственный материал, Echo заимствует контур и акценты вопроса, Contrast инвертирует их; Follow задаёт силу заимствования. Ритм ответа остаётся собственным. CHORD/PAD/DRUM заимствуют только акценты. Timeline и карточки Perform показывают очередь. Один блок участвует в одной активной паре; у конфликтующих строк показана причина обхода. Настройки сохраняются и поддерживают Undo/Redo. Подробности: docs/INSTRUMENT_DIALOGUE_RU.md; демо: examples/instrument_dialogue_demo.json.'
    ) + "</p>")
    sections.append(f"<h2>{h('Perform: Techniques, Phrases and Director', 'Perform: Techniques, Phrase и Director')}</h2>")
    sections.append("<p>" + h(
        'Perform is a musical gesture system. A Technique changes one block over time; a Phrase coordinates several stages across multiple blocks. PhraseState is the single runtime state for the active phrase, while TensionCurve drives global energy, density, probability and register behavior. MUTE is shared between the BLOCKS list and Perform: muting in either place immediately silences that block.',
        'Perform — система музыкальных жестов. Technique изменяет один блок во времени; Phrase координирует несколько стадий сразу между несколькими блоками. PhraseState является единым runtime-состоянием активной Phrase, а TensionCurve управляет глобальными Energy, Density, Probability и Register. MUTE общий для списка BLOCKS и Perform: выключение блока в любом из этих мест сразу заглушает его.'
    ) + "</p>")

    sections.append("<p>" + h(
        '<b>Duration · beats</b> in Global Phrase sets the whole phrase length (4–256 quarter-note beats). Stages stretch proportionally. Live edits preserve progress; the setting is saved with the project. For example, 16 beats is four bars in 4/4 or eight seconds at 120 BPM. The Length in each block card controls its individual technique.',
        '<b>Duration · beats</b> в Global Phrase задаёт длительность всей фразы (4–256 четвертных долей). Этапы растягиваются пропорционально. Изменение во время игры сохраняет текущий прогресс; настройка сохраняется в проекте. Например, 16 долей — это четыре такта 4/4 или восемь секунд при 120 BPM. Length в карточке блока задаёт длительность отдельной technique.'
    ) + "</p>")
    sections.append(f"<h3>{h('Phrase catalog', 'Каталог Phrase')}</h3>")
    phrase_notes_en = {
        "opening_bloom": "Opening form: Crescendo → Density Swell → Register Rise. Builds presence and opens the register.",
        "tension_rise": "Tension build: Stringendo → Accent Build → Register Rise, with role-aware substitutions for rhythm and harmonic blocks.",
        "climax_release": "Peak and release: Crescendo → Sforzando → Ritardando → Diminuendo/Smorzando depending on role.",
        "breath": "Expansion and breathing space: Density Swell → Tenuto → Rubato → Smorzando.",
        "accelerando_release": "Tempo-led build and release: Accelerando → Density/Crescendo → Ritardando.",
    }
    phrase_notes_ru = {
        "opening_bloom": "Открывающая форма: Crescendo → Density Swell → Register Rise. Постепенно раскрывает плотность и регистр.",
        "tension_rise": "Рост напряжения: Stringendo → Accent Build → Register Rise, с заменами приёмов в зависимости от роли блока.",
        "climax_release": "Пик и спад: Crescendo → Sforzando → Ritardando → Diminuendo/Smorzando в зависимости от роли.",
        "breath": "Расширение и пространство для дыхания: Density Swell → Tenuto → Rubato → Smorzando.",
        "accelerando_release": "Развитие через темп: Accelerando → Density/Crescendo → Ritardando.",
    }
    sections.append("<table cellspacing='0' cellpadding='5' border='1'><tr><th>Phrase</th><th>" + h("Length", "Длина") + "</th><th>" + h("Form / purpose", "Форма / назначение") + "</th></tr>")
    for phrase in PHRASES:
        total = sum(float(stage.beats) for stage in phrase.stages)
        note = (phrase_notes_ru if ru else phrase_notes_en).get(phrase.id, phrase.description)
        sections.append(f"<tr><td><b>{phrase.name}</b></td><td>{total:g} beats</td><td>{note}</td></tr>")
    sections.append("</table>")
    sections.append("<p>" + h(
        'Phrases are role-aware. The same dramaturgical stage can resolve to a different Technique for DRUM, PERCUSSION, BASS, MELODY, PAD or CHORD. This lets one Phrase coordinate the arrangement without forcing every block to perform the same gesture.',
        'Phrase учитывают роль блока. Одна и та же драматургическая стадия может использовать разные Technique для DRUM, PERCUSSION, BASS, MELODY, PAD или CHORD. Поэтому одна Phrase координирует аранжировку, не заставляя все блоки выполнять один и тот же жест.'
    ) + "</p>")

    sections.append(f"<h3>{h('Common Techniques', 'Основные Techniques')}</h3>")
    common_en = {
        "crescendo":"Gradually increases loudness and density.", "diminuendo":"Gradually reduces loudness and density.",
        "sforzando":"Short dynamic accent.", "accelerando":"Gradually increases timing rate.", "ritardando":"Gradually slows the timing rate.",
        "stringendo":"Accelerates while increasing intensity.", "smorzando":"Fades dynamics, density and motion toward rest.",
        "staccato":"Shortens note gates.", "tenuto":"Lengthens gates for a connected feel.", "rubato":"Adds gentle timing fluctuation.",
        "register_rise":"Moves pitch register upward.", "register_fall":"Moves pitch register downward.",
        "density_swell":"Increases event density and probability.", "density_drop":"Quickly opens space by reducing density.",
        "accent_build":"Builds accent strength without requiring a large average-volume increase."
    }
    common_ru = {
        "crescendo":"Постепенно увеличивает громкость и плотность.", "diminuendo":"Постепенно уменьшает громкость и плотность.",
        "sforzando":"Короткий динамический акцент.", "accelerando":"Постепенно ускоряет временной поток.", "ritardando":"Постепенно замедляет временной поток.",
        "stringendo":"Ускоряет движение одновременно с ростом интенсивности.", "smorzando":"Уводит динамику, плотность и движение к покою.",
        "staccato":"Укорачивает длительность звучания.", "tenuto":"Удлиняет звучание и делает подачу связнее.", "rubato":"Добавляет мягкие временные отклонения.",
        "register_rise":"Постепенно поднимает регистр.", "register_fall":"Постепенно опускает регистр.",
        "density_swell":"Увеличивает плотность и вероятность событий.", "density_drop":"Быстро освобождает пространство, уменьшая плотность.",
        "accent_build":"Наращивает акцентность без обязательного сильного роста средней громкости."
    }
    sections.append("<table cellspacing='0' cellpadding='5' border='1'><tr><th>Technique</th><th>" + h("Family", "Группа") + "</th><th>" + h("Action", "Действие") + "</th></tr>")
    for preset in COMMON:
        desc = (common_ru if ru else common_en).get(preset.id, preset.description)
        sections.append(f"<tr><td><b>{preset.name}</b></td><td>{preset.family}</td><td>{desc}</td></tr>")
    sections.append("</table>")

    sections.append(f"<h3>{h('Algorithm-specific Techniques', 'Techniques конкретных алгоритмов')}</h3>")
    sections.append("<p>" + h(
        'In addition to the common musical gestures, each generator can expose Techniques that manipulate its own structure. The Perform Technique menu merges the block-role catalog with the current algorithm catalog.',
        'Кроме общих музыкальных жестов, каждый генератор может иметь Techniques, управляющие именно его структурой. Меню Technique в Perform объединяет каталог музыкальной роли блока и каталог текущего алгоритма.'
    ) + "</p>")
    sections.append("<table cellspacing='0' cellpadding='5' border='1'><tr><th>" + h("Algorithm", "Алгоритм") + "</th><th>Techniques</th></tr>")
    for algorithm, presets in ALGORITHM_GESTURES.items():
        names = ", ".join(preset.name for preset in presets)
        sections.append(f"<tr><td><b>{algorithm}</b></td><td>{names}</td></tr>")
    sections.append("</table>")

    sections.append(f"<h3>{h('TensionCurve and Motifs', 'TensionCurve и Motifs')}</h3><p>" + h(
        'TensionCurve describes the phrase-level dramatic contour. Its value is evaluated over PhraseState time and is translated by the Musical Director into Energy (velocity), Density (event density), Probability (event survival) and Register movement. Curve presets include Gentle rise, Crescendo and Peak and release; smoothing controls how abruptly the contour changes.',
        'TensionCurve описывает драматургический контур Phrase. Значение вычисляется по времени PhraseState и через Musical Director преобразуется в Energy (velocity), Density (плотность событий), Probability (вероятность событий) и движение Register. Доступны формы Gentle rise, Crescendo и Peak and release; smoothing определяет плавность изменения контура.'
    ) + "</p><p>" + h(
        'Motifs are reusable phrase-level musical identities. Active motif IDs live inside PhraseState and are resolved by MotifEngine, so SEQ and LIVE generation can receive the same motif influence. Motifs belong to the project and are restored with it.',
        'Motifs — повторно используемые музыкальные идентичности уровня Phrase. ID активных Motif находятся внутри PhraseState и разрешаются через MotifEngine, поэтому одинаковое влияние Motif доступно и в SEQ, и в LIVE. Motifs принадлежат проекту и восстанавливаются вместе с ним.'
    ) + "</p>")

    sections.append(f"<h2>{h('Recommended workflow', 'Рекомендуемый workflow')}</h2><ol>" + "".join(f"<li>{x}</li>" for x in ([
        'Build the rhythmic foundation first (DRUM/PERCUSSION).', 'Add BASS and constrain it to the project scale.', 'Use PAD/CHORD to establish harmonic space.', 'Add MELODY last and keep its density lower than the rhythm section at first.', 'Use Process Layers for local motion; use Relations for cross-block influence.', 'Use Perform for musical transitions and phrases rather than continuous manual knob riding.', 'Save projects after major structural changes; keep MIDI MONITOR open while diagnosing routing.' ] if not ru else [
        'Сначала создайте ритмическую основу (DRUM/PERCUSSION).', 'Добавьте BASS и ограничьте его выбранной гаммой проекта.', 'Используйте PAD/CHORD для создания гармонического пространства.', 'Добавляйте MELODY последней и сначала держите её плотность ниже ритм-секции.', 'Используйте Process Layers для локального движения, Relations — для взаимного влияния блоков.', 'Используйте Perform для музыкальных переходов и Phrase вместо постоянного ручного движения knob.', 'Сохраняйте проект после крупных структурных изменений; при диагностике маршрутизации держите MIDI MONITOR открытым.'])) + "</ol>")
    sections.append(f"<h2>{h('Troubleshooting', 'Диагностика')}</h2><ul><li>{h('No MIDI: check the selected MIDI output, the block MUTE state and MIDI channel.', 'Нет MIDI: проверьте выбранный MIDI output, MUTE у блока и MIDI channel.')}</li><li>{h('Too many notes: reduce Fill/Density, Probability or Relation Amount.', 'Слишком много нот: уменьшите Fill/Density, Probability или Relation Amount.')}</li><li>{h('Unstable pitch: reduce Feedback/Chaos/Leap and constrain Scale.', 'Нестабильный pitch: уменьшите Feedback/Chaos/Leap и ограничьте Scale.')}</li><li>{h('Unexpected cross-block changes: inspect RELATIONS and Parameter Modulation processes.', 'Неожиданные изменения между блоками: проверьте RELATIONS и процессы Parameter Modulation.')}</li></ul>")
    return "<html><body style='font-family: sans-serif; font-size: 10pt; line-height: 1.35;'><div style='max-width: 1100px;'>" + ''.join(sections) + "</div></body></html>"


def help_html(language: str = "en") -> str:
    return _html("ru" if language.lower().startswith("ru") else "en")
