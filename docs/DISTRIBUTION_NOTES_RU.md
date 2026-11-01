# Auricle v2.0.0 — полный дистрибутив

> Заметки о более ранней сборке. Сведения о текущей уборке и фактических проверках
> приведены в [CLEANUP_RU.md](CLEANUP_RU.md). Числа ниже сохранены как история.

Сборка объединяет исходный пакет Auricle v2.0.0 и последовательно применённые патчи проекта, включая последнюю правку MIDI IN.

## Включено
- Общая музыкальная шкала времени и модель MIDI-событий.
- Опорные удары, вероятностная генерация, Rhythm Map и Intelligent Relations.
- Память, развитие и преобразование мотивов.
- Экспериментальные генераторы.
- Реорганизация Composition.
- MIDI Expression: CC Automation, Pitch Bend, Aftertouch, MIDI Clock Sync.
- MIDI Learn и исправленный приём входящих MIDI-событий через отдельный reader-поток.
- Оптимизации транспортного цикла, разделение блокировок и GUI → Transport Command Queue.
- 10 тем интерфейса: 5 тёмных и 5 светлых.

## Сборка
- Python: 3.10+
- Установка: `pip install .`
- Запуск установленной программы: `auricle`
- Для разработки: `pip install .[dev]`
- Для сборки приложения: `pip install .[build]`

Зависимости GUI и MIDI указаны в `pyproject.toml`.

## Проверки этой сборки
- Python-компиляция: 197 файлов, ошибок нет.
- Целевой набор тестов (MIDI Learn/Input, MIDI Expression, Transport Queue/Locks, performance, musical time, rhythm, experimental generators, motif): 107 passed.
- Полный прогон: 1819 passed, 7 skipped; 62 GUI-зависимых ошибки сбора/запуска из-за отсутствия PySide6 в среде проверки. GUI end-to-end не подтверждён.
- Wheel `auricle-2.0.0-py3-none-any.whl` собран успешно.
- Проверено наличие всех 57 объявленных Python-модулей в wheel, включая `midi_input_reader.py`; проверены ресурсы приложения.

Физический MIDI-контроллер в среде сборки недоступен. Поэтому приём MIDI проверен модульными тестами reader-loop, но аппаратный end-to-end тест не заявляется.
