"""Fetch versioned, SHA256-pinned Linux x64 AppImage build components."""
from pathlib import Path
import hashlib
import platform
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = {
    'appimagetool': ('https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage',
                     'ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0'),
    'runtime-x86_64': ('https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64',
                      '2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d'),
}


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    if sys.platform != 'linux' or platform.machine().lower() not in ('x86_64','amd64'):
        raise SystemExit('The bundled AppImage build targets Linux x64')
    directory = ROOT/'build/appimage'; directory.mkdir(parents=True,exist_ok=True)
    for name,(url,expected) in COMPONENTS.items():
        target = directory/name
        if not target.is_file() or digest(target) != expected:
            temporary = target.with_suffix('.part')
            for attempt in range(3):
                try:
                    with urlopen(url,timeout=60) as response, temporary.open('wb') as stream:
                        for chunk in iter(lambda: response.read(1024*1024), b''): stream.write(chunk)
                    if digest(temporary) != expected: raise RuntimeError(f'SHA256 mismatch: {name}')
                    temporary.replace(target)
                    break
                except (URLError, TimeoutError):
                    if attempt == 2: raise
                    time.sleep(2)
        target.chmod(0o755)
        print(f'Verified {name}')


if __name__ == '__main__': main()
