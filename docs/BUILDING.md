# Сборка Auricle

## Состав

Python 3.12, PySide6 6.12.0, Mido 1.3.3, python-rtmidi 1.5.8; PyInstaller 6.22.3. Версии заданы в `requirements.txt` и `requirements-build.txt`. Нативные пакеты собираются на соответствующей ОС, без кросс-компиляции.

| Цель | GitHub runner | Результат |
| --- | --- | --- |
| Windows x64 | windows-2022 | portable ZIP с EXE |
| Linux x64 | ubuntu-22.04 | AppImage и tar.gz |
| macOS ARM64 | macos-15 | DMG с Auricle.app |
| macOS x64 | macos-15-intel | DMG с Auricle.app |

## Локальная сборка

- Windows: `build_windows.bat`. Скрипт сам создаёт `.venv-build` через Python Launcher 3.12.
- Linux/macOS: `bash build.sh`. Переменная `PYTHON` может выбрать интерпретатор для создания окружения.
- Linux AppImage: `bash build_appimage.sh`; appimagetool 1.9.1 и runtime 20251108 загружаются автоматически с проверкой закреплённых SHA256. То же выполняется в GitHub Actions.

Результаты PyInstaller находятся в `dist/`, архивы — в `out/`. `packaging/smoke_native.py` запускает собранное приложение из временного каталога с offscreen Qt и проверяет код завершения. Пустое окно без artwork не считается успешным запуском.

На Linux до сборки нужны библиотеки ALSA, OpenGL/EGL, DBus, fontconfig и XCB. Полный список установки сохранён в workflow; наличие их при сборке позволяет PyInstaller собрать соответствующие зависимости Qt. AppImage не устраняет ограничения glibc: runner Ubuntu 22.04 выбран как базовая Linux-система.

## Ресурсы

`Auricle.spec` включает runtime-модули, SVG/PNG/ICO/ICNS, текущие руководства, примеры и metadata зависимостей. Системные иконки повторно формируются через QSvgRenderer из `assets/auricle_logo.svg`. Пути работают при запуске из произвольного каталога.

`python -m build` создаёт wheel и sdist. `python packaging/source_archive.py` создаёт полный чистый ZIP, включая `.github/workflows`. Тесты и служебные каталоги исключены из обоих форматов.

## Подпись

Пайплайн не требует сертификатов Apple/Microsoft. macOS-сборка получает локальную ad-hoc подпись PyInstaller; доверенная Developer ID-подпись и notarization не настроены. Windows EXE также не подписан сертификатом издателя. Для публичного выпуска с доверенной подписью нужны сертификаты владельца проекта.
