# GitHub Actions → Releases

Workflow: `.github/workflows/release.yml`, название в Actions — **Build and release Auricle**.

## Запуск

Ручной **Run workflow** на нужной ветке и push тега `v2.0.1` выполняют один и тот же выпуск. Тег должен совпадать с `APP_VERSION` в `version.py`; Python-версия должна равняться тегу без `v`. Релизные заметки берутся из `RELEASE_NOTES.md`.

Если при ручном запуске тега ещё нет, публикация создаёт его на точном `GITHUB_SHA` запуска. Существующий тег другого коммита блокирует сборку: для следующего выпуска следует изменить версию. Содержимое релизов разных коммитов не смешивается. Обычный CI для веток не требует менять версию после каждого коммита: строгая проверка целевого коммита тега включается только для выпуска.

## Процесс

1. Проверяются inventory Python-модулей, artwork, SVG и JSON-примеры, версия и запуск исходников.
2. Собираются wheel/sdist; wheel устанавливается и запускается за пределами checkout. Готовится чистый исходный ZIP.
3. На четырёх нативных runners параллельно собираются EXE, Linux-приложение и два macOS .app. Каждый проходит проверку запуска из временного каталога. Linux AppImage дополнительно проверяется после упаковки без FUSE.
4. Загружаются все артефакты. Проверяется полный список и SHA256; создаётся или продолжается черновик Release.
5. После загрузки сверяются имена, размеры и доступные серверные digest. Только затем черновик публикуется.

Если отдельная ОС не собралась, публикация не запускается. Ошибка загрузки оставляет новый релиз черновиком. Повторный запуск может продолжить незавершённый черновик. Уже опубликованный полный релиз не перезаписывается. Выпуски сериализованы общей concurrency-группой.

## Файлы одного выпуска

- `Auricle-v2.0.1-windows-x64.zip`
- `Auricle-v2.0.1-linux-x64.AppImage`
- `Auricle-v2.0.1-linux-x64.tar.gz`
- `Auricle-v2.0.1-macos-arm64.dmg`
- `Auricle-v2.0.1-macos-x64.dmg`
- `Auricle-v2.0.1-source.zip`
- `auricle-2.0.1-py3-none-any.whl`
- `auricle-2.0.1.tar.gz`
- `SHA256SUMS.txt`

При изменении версии имена формируются автоматически. Публикацию выполняет стандартный `GITHUB_TOKEN` с `contents: write` только в последнем job. Остальным jobs доступен режим чтения; секреты и личный PAT в проекте не хранятся.

Нативные сборки без сертификатов издателя; сведения о подписи находятся в `BUILDING.md`. Запуск workflow в конкретном репозитории и публикация в нём происходят на стороне GitHub; исходный архив сам не создаёт удалённый репозиторий.

## Официальная документация

- [GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Artifacts: upload](https://github.com/actions/upload-artifact) · [download](https://github.com/actions/download-artifact)
- [GitHub CLI: создание Release](https://cli.github.com/manual/gh_release_create) · [загрузка файлов](https://cli.github.com/manual/gh_release_upload)
- [PyInstaller](https://pyinstaller.org/en/stable/usage.html)
