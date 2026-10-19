"""Validate the release tag and prepare portable GitHub release notes."""
from pathlib import Path
import os
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    version = runpy.run_path(str(ROOT / "version.py"))["APP_VERSION"]
    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        tag = os.environ.get("GITHUB_REF_NAME")
        if tag != version:
            sys.exit(f"Release tag {tag!r} does not match version.py ({version})")
    notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    if notes.splitlines()[0] != f"# Auricle {version}":
        sys.exit("Update RELEASE_NOTES.md to match version.py")
    repository = os.environ.get("GITHUB_REPOSITORY")
    revision = os.environ.get("GITHUB_SHA")
    if repository and revision:
        # Relative images/links work in README but not in a GitHub Release body.
        base = f"https://github.com/{repository}/blob/{revision}/"
        notes = notes.replace("(docs/", "(" + base + "docs/")
        notes = notes.replace("(README.md)", "(" + base + "README.md)")
        notes = notes.replace("(CHANGELOG.md)", "(" + base + "CHANGELOG.md)")
        notes = notes.replace("auricle-v111.png)", "auricle-v111.png?raw=true)")
    out = ROOT / "build"
    out.mkdir(exist_ok=True)
    (out / "release-notes.md").write_text(notes, encoding="utf-8")
    print(version)


if __name__ == "__main__":
    main()
