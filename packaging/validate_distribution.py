"""Release checks for source inventory and data, independent of obsolete tests."""
from pathlib import Path
import ast
import json
import runpy
import tomllib
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))
    modules = set(config['tool']['setuptools']['py-modules'])
    local = {p.stem for p in ROOT.glob('*.py')}
    for name in modules:
        path = ROOT / (name+'.py')
        if not path.is_file(): raise SystemExit(f'Missing runtime module: {name}')
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'), filename=str(path))):
            imports = [alias.name.split('.')[0] for alias in node.names] if isinstance(node, ast.Import) else [node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module else []
            if missing := (set(imports) & local) - modules:
                raise SystemExit(f'{name}: unlisted runtime imports {sorted(missing)}')
    assets = runpy.run_path(str(ROOT/'auricle_resources.py'))['REQUIRED_ASSETS']
    for name in assets:
        if not (ROOT/'assets'/name).is_file(): raise SystemExit(f'Missing artwork: {name}')
    for p in (ROOT/'assets').glob('*.svg'): ET.parse(p)
    for p in (ROOT/'examples').glob('*.json'): json.loads(p.read_text(encoding='utf-8'))
    for name in ('drum_articulation','strum','piano_roll_history','section_automation'):
        if name not in modules: raise SystemExit(f'Missing current feature: {name}')
    from source_archive import source_files
    if any('tests' in rel.parts or rel.name == 'requirements-dev.txt' for _,rel in source_files()):
        raise SystemExit('Development tests must not be in the source archive')
    for name in ('release.yml','ci.yml'):
        if not (ROOT/'.github/workflows'/name).is_file(): raise SystemExit(f'Missing workflow {name}')
    print(f'Distribution OK: {len(modules)} runtime modules, {len(assets)} required assets')


if __name__ == '__main__': main()
