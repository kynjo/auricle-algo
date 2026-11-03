"""Publish one complete release; never expose a partly uploaded new release."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

from release_metadata import ROOT, release_version


def expected_assets(tag, version):
    return {f'Auricle-{tag}-{target}{suffix}' for target, suffix in (
        ('windows-x64','.zip'), ('linux-x64','.AppImage'), ('linux-x64','.tar.gz'),
        ('macos-arm64','.dmg'), ('macos-x64','.dmg'), ('source','.zip'))} | {
        f'auricle-{version}-py3-none-any.whl', f'auricle-{version}.tar.gz', 'SHA256SUMS.txt'}


def validate_assets(directory, tag, version):
    expected = expected_assets(tag, version)
    actual = {path.name for path in directory.iterdir() if path.is_file()}
    if actual != expected:
        raise ValueError(f'Incomplete release: missing={sorted(expected-actual)}, unexpected={sorted(actual-expected)}')
    checksums = {}
    for line in (directory/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        if name in checksums: raise ValueError(f'Duplicate checksum: {name}')
        checksums[name] = digest
    if set(checksums) != expected - {'SHA256SUMS.txt'}: raise ValueError('Checksum inventory mismatch')
    for name, digest in checksums.items():
        path = directory / name
        with path.open('rb') as stream: actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if path.stat().st_size == 0 or actual != digest:
            raise ValueError(f'Checksum mismatch or empty asset: {name}')
    return sorted(directory/name for name in expected)


def gh(*args, json_result=False, missing_ok=False):
    result = subprocess.run(['gh', *args], text=True, capture_output=True, check=False)
    if result.returncode:
        if missing_ok and ('HTTP 404' in result.stderr or 'release not found' in result.stderr.lower()): return None
        raise RuntimeError(result.stderr.strip() or 'GitHub CLI failed')
    if json_result: return json.loads(result.stdout)
    return result.stdout.strip()


def view_release(repo, tag, missing_ok=False):
    # gh handles draft releases whose tag has not been created yet.
    value = gh('release','view',tag,'--repo',repo,'--json','isDraft,assets,url',
               json_result=True, missing_ok=missing_ok)
    return None if value is None else {'draft':value['isDraft'], 'assets':value['assets'], 'html_url':value['url']}


def publish(directory=ROOT/'out'):
    tag, version = release_version(require_target=True)
    files = validate_assets(directory, tag, version)  # No API mutation before all nine assets exist.
    repo = os.environ.get('GITHUB_REPOSITORY')
    commit = os.environ.get('GITHUB_SHA')
    if not repo or not commit or not os.environ.get('GH_TOKEN'):
        raise RuntimeError('Run publication from GitHub Actions with GITHUB_REPOSITORY, GITHUB_SHA and GH_TOKEN')
    release = view_release(repo, tag, missing_ok=True)
    expected = {path.name for path in files}
    if release and not release['draft']:
        existing = {asset['name'] for asset in release.get('assets', [])}
        if not expected <= existing:
            raise RuntimeError('This published release is incomplete; increment version.py for a new release')
        print('Release already complete:', release['html_url'])
        return
    notes = ROOT/'build/release-notes.md'
    if not notes.is_file(): raise RuntimeError('Run packaging/release_metadata.py first')
    if release is None:
        gh('release','create',tag,'--repo',repo,'--target',commit,'--draft',
           '--title',f'Auricle {tag}','--notes-file',str(notes))
    else:
        gh('release','edit',tag,'--repo',repo,'--target',commit,'--title',f'Auricle {tag}','--notes-file',str(notes))
    gh('release','upload',tag,*map(str,files),'--repo',repo,'--clobber')
    release = view_release(repo, tag)
    remote = {asset['name']:asset for asset in release['assets']}
    for path in files:
        asset = remote.get(path.name)
        if asset is None or asset['size'] != path.stat().st_size: raise RuntimeError(f'Asset upload incomplete: {path.name}')
        if digest := asset.get('digest'):
            with path.open('rb') as stream: local = 'sha256:'+hashlib.file_digest(stream,'sha256').hexdigest()
            if digest != local: raise RuntimeError(f'Remote checksum mismatch: {path.name}')
    gh('release','edit',tag,'--repo',repo,'--draft=false','--latest')
    print('Published:',release['html_url'])


if __name__ == '__main__':
    try: publish()
    except (RuntimeError, ValueError) as exc: sys.exit(str(exc))
