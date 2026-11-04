# Auricle · Algorithmic MIDI Generator

**Auricle ** — настольный MIDI-генератор для драм-машин, синтезаторов и DAW. Программа создаёт MIDI-события; звук воспроизводит подключённый инструмент.


<img width="1440" height="1074" alt="изображение" src="https://github.com/user-attachments/assets/8fd57e10-00f3-4551-8e8c-6daf31c75a87" />

## Возможности

- DRUM, BASS, MELODY, CHORD и PAD; независимые генераторы и режимы SEQ/LIVE.
- Drum Voices/Kit, согласованные Classic/Map/Metric-ритмы, вариации, синкопы, Ratchet и Flam.
- Strum для CHORD/PAD: направление, интервал, динамика, Humanize и варианты окончания нот.
- Composition: секции, гармония, фразы, значения и кривые точных параметров. Настраиваемые связи артикуляций с Energy/Tension, музыкальные границы и подсветка влияний.
- Relations и диалог инструментов, процессы и мутации, MIDI Learn, MIDI Expression, Undo/Redo и восстановление сессии.
- Piano roll фактически отправленных нот: повторы, предудары и сдвиги; реальные Note On/Off, velocity, цвета и подсказки. Фиксированная длина и Freeze.
- Заводские и пользовательские пресеты алгоритмов и блоков: сравнение ручных параметров, импорт/экспорт JSON, сохранение MIDI-маршрутов и назначений.
- Темы интерфейса и справка RU/EN. Логотип и иконки формируются из `assets/auricle_logo.svg` через QSvgRenderer.

## Дистрибутивы

| Платформа | Файлы релиза |
| --- | --- |
| Windows x64 | `Auricle-v2.0.1-windows-x64.zip` — папка с `Auricle.exe` |
| Linux x64 | `Auricle-v2.0.1-linux-x64.AppImage` и `.tar.gz` |
| macOS Apple Silicon | `Auricle-v2.0.1-macos-arm64.dmg` |
| macOS Intel | `Auricle-v2.0.1-macos-x64.dmg` |
| Исходники | `Auricle-v2.0.1-source.zip`, Python wheel и sdist |

Нативные сборки содержат Python и необходимые библиотеки. Проверочные суммы всех файлов находятся в `SHA256SUMS.txt`.

## GitHub Actions

Workflow **Build and release Auricle** собирает все четыре платформы. Ручной запуск через **Run workflow** и push тега, совпадающего с `APP_VERSION` в `version.py`, одинаково публикуют полный релиз. GitHub сам предоставляет `GITHUB_TOKEN`; отдельный PAT не нужен.

Релиз публикуется после успешной проверки исходников, wheel и каждой нативной сборки. Все файлы сначала загружаются в черновик, проверяются, затем появляются в Releases вместе. При сбое сборки или загрузки неполный новый релиз остаётся неопубликованным.

Для нового выпуска согласованно меняются `version.py` и `RELEASE_NOTES.md`. Существующий тег не должен указывать на другой коммит. Подробности: [публикация](docs/PUBLISHING.md), [локальная сборка](docs/BUILDING.md).

## Запуск из исходников

Нужен Python 3.12. Linux/macOS: `bash run.sh`. Windows: `setup_windows.bat`, затем `run_windows.bat`. Для работы из чистого Python-окружения: установить `requirements.txt` и запустить `python auricle_gui.py`.

## Руководства

- [Справка RU](docs/HELP_RU.md) · [English help](docs/HELP_EN.md)
- [Composition и Perform](docs/UNIFIED_COMPOSITION_RU.md) · [Composition Planner](docs/COMPOSITION_PLANNER_RU.md)
- [Пресеты алгоритмов и блоков](docs/SOUND_PRESETS_RU.md)
- [Адресная автоматизация](docs/SECTION_AUTOMATION_RU.md)
- [Musical Drum Kit](docs/DRUM_MUSICAL_RU.md) · [Работа с Kit](docs/KIT_WORKFLOW_RU.md)
- [MIDI Learn](docs/MIDI_LEARN_RU.md) · [MIDI Expression](docs/MIDI_EXPRESSION_RU.md)
- [Диалог инструментов](docs/INSTRUMENT_DIALOGUE_RU.md)
- [Слои параметров](docs/PARAMETER_LAYERS_RU.md) · [Индикаторы источников](docs/PARAMETER_SOURCES_RU.md)

Готовые проекты находятся в `examples/`. В этом архиве сохранены все текущие функции и artwork; старые тесты, отчёты разработки, кэши и результаты предыдущих сборок исключены.
