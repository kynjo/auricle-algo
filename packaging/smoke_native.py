"""Start the native app outside the checkout; fail on crashes or missing data."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = {'win32': 'dist/Auricle/Auricle.exe', 'darwin': 'dist/Auricle.app/Contents/MacOS/Auricle'}
    executable = ROOT / paths.get(sys.platform, 'dist/Auricle/Auricle')
    if not executable.is_file(): raise SystemExit(f'Missing native executable: {executable}')
    with tempfile.TemporaryDirectory(prefix='auricle-native-smoke-') as temp:
        env = {**os.environ, 'QT_QPA_PLATFORM':'offscreen', 'AURICLE_RECOVERY_DIR':str(Path(temp)/'recovery')}
        env.pop('PYTHONPATH', None); env.pop('PYTHONHOME', None)
        subprocess.run([str(executable), '--smoke-test'], cwd=temp, env=env, timeout=90, check=True)
    print(f'Native startup OK: {executable.name}')


if __name__ == '__main__': main()
