# MIDI Learn repair

## Причина
В последовательных патчах MIDI Expression и GUI/Transport Command Queue были перезаписаны общие файлы `auricle_model.py`, `auricle_persistence.py`, `auricle_transport.py` и `auricle_core.py`. Из-за этого UI MIDI Learn оставался в коде, но модель проекта теряла поля `midi_input_port` и `midi_mappings`, а публичный API не экспортировал обнаружение MIDI-входов.

## Исправления
- Объединены поля MIDI Learn с MIDI Expression в модели проекта и persistence.
- Восстановлено обнаружение MIDI IN и его экспорт через `auricle_core`.
- Сохранена актуальная версия Transport с MIDI Expression, lock domains и GUI command queue.
- Входящие Mido-сообщения декодируются в callback-потоке и передаются в Qt как простые данные через `QueuedConnection`.
- Learn остаётся вооружённым, если пользователь закрыл окно подключения до выбора MIDI-входа.
- В менеджере отображается последнее входящее MIDI-сообщение и список назначений обновляется сразу после Learn.
- Исправлена совместимость кэшированных конфигураций MIDI Expression и сохранение секционных MIDI Automation.

## Проверки
- MIDI Learn, MIDI Expression, Transport Command Queue и Transport Lock Domains: 49 тестов пройдены.
- Python-компиляция изменённых модулей пройдена.
- Публичный импорт `get_midi_input_names` через `auricle_core` проверен.
- GUI и физическое MIDI-устройство не тестировались: в среде отсутствует PySide6 и нет доступа к аппаратному MIDI-порту.
