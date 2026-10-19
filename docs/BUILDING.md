# Сборка Auricle v111

Рекомендуемая среда: Python 3.12, 64 бита. Каждая нативная сборка выполняется на целевой ОС и архитектуре; PyInstaller не является кросс-компилятором. Windows ARM и универсальный macOS universal2 этим workflow не собираются.

## Windows

Установите Python 3.12 x64 с Python Launcher. В каталоге проекта:

```bat
setup_windows.bat
build_windows.bat
```

Результат: `dist\Auricle\Auricle.exe` и `out\Auricle-v111-windows-x64.zip`. Переносите весь каталог Auricle вместе с `_internal`, а не один EXE. Иконка исполняемого файла берётся из `assets/auricle.ico`.

## Linux

Эталон сборки GitHub Actions — Ubuntu 22.04 x64. Установите системные зависимости:

```sh
sudo apt-get update
sudo apt-get install -y python3-venv libasound2-dev libgl1 libegl1 libdbus-1-3 libfontconfig1 \
  libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
  libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1
bash build.sh
```

На других дистрибутивах названия пакетов могут отличаться. Не следует собирать на системе с более новой glibc, чем у целевых пользователей.

Результат: `dist/Auricle/Auricle` и соседние файлы. Для AppImage потребуется [appimagetool](https://github.com/AppImage/appimagetool/releases), соответствующий архитектуре. В GitHub Actions используется версия 1.9.1; для локальной сборки скачайте её в `appimagetool`, затем:

```sh
chmod +x appimagetool
APPIMAGETOOL="$PWD/appimagetool" bash build_appimage.sh
```

Если PyInstaller уже отработал, достаточно `APPIMAGETOOL="$PWD/appimagetool" bash packaging/make_appimage.sh`. Иконка копируется из `assets/auricle_icon.png`; ImageMagick не требуется. Результат: `out/Auricle-v111-linux-x64.AppImage`. При упаковке без FUSE скрипт включает `APPIMAGE_EXTRACT_AND_RUN=1` для appimagetool.

## macOS

Установите Python 3.12 подходящей архитектуры и выполните:

```sh
bash build.sh
.venv-build/bin/python packaging/package_release.py macos-arm64
```

На Intel используйте `macos-x64`. Результат: `dist/Auricle.app` и соответствующий DMG в `out/`. Иконка берётся из `assets/auricle.icns`. Архитектура Python и компьютера должна соответствовать выбранной цели. Автоматическая Developer ID подпись и notarization не настроены.

## Python wheel и sdist

В активированном окружении:

```sh
python -m pip install -r requirements-build.txt
python -m build
```

Получатся `dist/auricle-111.0.0-py3-none-any.whl` и `dist/auricle-111.0.0.tar.gz`. Wheel содержит все рабочие модули и artwork-пакет `auricle_assets`; исходный архив также содержит тесты, примеры, документацию и сценарии сборки.

После установки wheel команда `auricle` работает из любого каталога. В `version.py` используются два представления одной версии: `APP_VERSION = "v111"` для приложения и GitHub, `PACKAGE_VERSION = "111.0.0"` для Python и macOS.

## Проверки

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python auricle_gui.py --smoke-test
```

На Linux без дисплея установите `QT_QPA_PLATFORM=offscreen`. Smoke test проверяет наличие artwork, создаёт окно, проверяет загрузку логотипа и закрывает приложение. Использует временный каталог восстановления и не запускает MIDI-воспроизведение.

Проверка нативной сборки:

```sh
QT_QPA_PLATFORM=offscreen dist/Auricle/Auricle --smoke-test
# macOS:
dist/Auricle.app/Contents/MacOS/Auricle --smoke-test
```

Windows PowerShell:

```powershell
$p = Start-Process dist/Auricle/Auricle.exe -ArgumentList '--smoke-test' -Wait -PassThru
if ($p.ExitCode -ne 0) { throw 'Auricle smoke test failed' }
```

Smoke test проверяет запуск, но не заменяет прослушивание и проверку MIDI-порта на настоящем оборудовании.

## Ресурсы и примеры в готовых приложениях

- Windows / Linux folder build: `dist/Auricle/_internal/examples/`, рядом `docs/` и `assets/`.
- macOS: `Auricle.app/Contents/Resources/examples/` (в Finder: Show Package Contents).
- AppImage: при необходимости выполните `./Auricle-v111-linux-x64.AppImage --appimage-extract`; примеры находятся в `squashfs-root/usr/bin/_internal/examples/`.

Открывайте проекты из примеров через диалог Open и сохраняйте рабочую копию в свой каталог. `asset_path()` разрешает artwork для исходников, wheel и замороженного приложения независимо от текущего каталога.

## GitHub Actions

`ci.yml` запускает тесты, собирает wheel/sdist и проверяет установленный wheel вне исходников. `release.yml` сначала вызывает CI, затем строит четыре нативные сборки и проверяет их запуск. Выходные файлы получают версию в имени. Только job публикации имеет `contents: write`.

[Публикация](PUBLISHING.md) · [PyInstaller: spec files](https://pyinstaller.org/en/stable/spec-files.html) · [PyInstaller: runtime resources](https://pyinstaller.org/en/stable/runtime-information.html)
