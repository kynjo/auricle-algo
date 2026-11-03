"""Resolve and validate one release version before native builds start."""
from pathlib import Path
import os
import re
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def release_version(require_target=False):
    values = runpy.run_path(str(ROOT/'version.py'))
    tag, version = values['APP_VERSION'], values['PACKAGE_VERSION']
    if tag != 'v'+version or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('APP_VERSION must be vX.Y.Z and PACKAGE_VERSION must be X.Y.Z')
    if os.environ.get('GITHUB_REF_TYPE') == 'tag' and os.environ.get('GITHUB_REF_NAME') != tag:
        raise ValueError(f'The pushed tag must match version.py: {tag}')
    if require_target and (ROOT/'.git').exists():
        exists = subprocess.run(['git','show-ref','--verify','--quiet',f'refs/tags/{tag}'], cwd=ROOT).returncode
        if exists == 0:
            target = subprocess.check_output(['git','rev-parse',f'{tag}^{{commit}}'], cwd=ROOT,text=True).strip()
            head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
            if target != head: raise ValueError(f'{tag} already points to another commit; increment version.py')
        elif exists != 1: raise ValueError('Could not inspect local release tags')
    return tag, version


def main():
    tag, version = release_version(require_target=os.environ.get('AURICLE_RELEASE') == '1')
    notes = (ROOT/'RELEASE_NOTES.md').read_text(encoding='utf-8')
    if not notes.startswith(f'# Auricle {tag}\n'): raise SystemExit('RELEASE_NOTES.md does not match version.py')
    out = ROOT/'build'; out.mkdir(exist_ok=True)
    (out/'release-notes.md').write_text(notes,encoding='utf-8')
    print(tag)


if __name__ == '__main__': main()
