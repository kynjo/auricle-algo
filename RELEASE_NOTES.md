# Auricle v2.0

Облегчён интерфейс: обновляются видимые панели, Drum Kit и карточки сохраняются
при обычных изменениях, а профиль algo_conf применяет только сохранённые параметры.
Callbacks отменяются при удалении владельца; планировщик не воспроизводит очереди
устаревших опросов после задержки. [Описание](docs/UI_PERFORMANCE_FIX_RU.md).

Musical Drum Kit: согласованная карта ритмов Map X/Y, развитие мотивов
Theme / Variation / Answer / Fill / Return и редактируемые связи voices.
Density сохраняет основу дольше украшений; каденции учитывают конец секции
Composition. Все три направления включаются кнопкой **Musical kit** в Drum.

[Руководство](docs/DRUM_MUSICAL_RU.md).
Демо: `examples/musical_drum_demo.json`.

Объединены Composition и Perform. Фразы и техники назначаются секциям,
цветная форма и компактные карточки показывают развитие исполнения.
Основной Play сохраняет независимое прослушивание Blocks.

Полная история релиза: [CHANGELOG.md](CHANGELOG.md).
Руководство нового интерфейса: [UNIFIED_COMPOSITION_RU.md](docs/UNIFIED_COMPOSITION_RU.md).
Демо: `examples/unified_composition_demo.json`.
