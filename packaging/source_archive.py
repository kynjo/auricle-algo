"""Create the clean, GitHub-ready source distribution, including workflows."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import argparse
import runpy
import shutil
import tomllib

ROOT = Path(__file__).resolve().parents[1]
VERSION = runpy.run_path(str(ROOT / 'version.py'))['APP_VERSION']
SKIP = {'tests', 'build', 'dist', 'out', 'AppDir', '__pycache__', '.git', '.venv', '.venv-build', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'recovery'}
EXTRA = {'LICENSE', 'LICENSE.md', 'LICENSE.txt', 'COPYING', 'AUTHORS', 'README.md', 'CHANGELOG.md', 'RELEASE_NOTES.md', 'Auricle.spec', 'pyproject.toml',
         'MANIFEST.in', '.gitignore', '.gitattributes', 'build.sh', 'build_appimage.sh',
         'build_windows.bat', 'run.sh', 'run_windows.bat', 'setup_windows.bat',
         'requirements.txt', 'requirements-build.txt', 'requirements-windows.txt'}


def source_files(root=ROOT):
    config = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    modules = {name + '.py' for name in config['tool']['setuptools']['py-modules']}
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if not path.is_file() or any(part in SKIP or part.endswith('.egg-info') for part in rel.parts): continue
        if path.suffix in ('.pyc', '.pyo', '.log') or path.name in ('.DS_Store','Thumbs.db'): continue
        if len(rel.parts) == 1:
            allowed = rel.name in modules | EXTRA
        else:
            allowed = rel.parts[0] in ('assets','docs','examples','packaging','.github') or str(rel) == 'projects/README.md'
        if allowed:
            if path.is_symlink(): raise ValueError(f'Source symlink is not permitted: {rel}')
            yield path, rel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'out')
    parser.add_argument('--python-artifacts', action='store_true')
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / f'Auricle-{VERSION}-source.zip'
    with ZipFile(archive, 'w', ZIP_DEFLATED, compresslevel=9) as z:
        for path, rel in source_files():
            info = ZipInfo(f'Auricle-{VERSION}/{rel.as_posix()}', (2026,1,1,0,0,0))
            info.compress_type = ZIP_DEFLATED
            mode = 0o755 if path.suffix == '.sh' else 0o644
            info.create_system = 3; info.external_attr = (0o100000 | mode) << 16
            z.writestr(info, path.read_bytes())
    if args.python_artifacts:
        files = [*ROOT.glob('dist/*.whl'), *ROOT.glob('dist/*.tar.gz')]
        if len(files) != 2: raise SystemExit('Expected exactly one wheel and one source tarball in dist/')
        for path in files: shutil.copy2(path, args.output / path.name)
    print(archive)


if __name__ == '__main__': main()
