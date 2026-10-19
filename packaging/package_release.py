"""Create Windows ZIP / macOS DMG next to Linux AppImage output."""
from __future__ import annotations

import argparse
from pathlib import Path
import platform
import runpy
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("windows-x64", "macos-arm64", "macos-x64"))
    args = parser.parse_args()
    expected_os = "Windows" if args.target.startswith("windows-") else "Darwin"
    if platform.system() != expected_os:
        parser.error(f"{args.target} must be packaged on {expected_os}")
    expected_arch = "arm64" if args.target.endswith("arm64") else "x64"
    actual_arch = {"arm64": "arm64", "aarch64": "arm64", "amd64": "x64",
                   "x86_64": "x64"}.get(platform.machine().lower())
    if actual_arch != expected_arch:
        parser.error(f"Target architecture {expected_arch} does not match this machine")
    version = runpy.run_path(str(ROOT / "version.py"))["APP_VERSION"]
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    base = out / f"Auricle-{version}-{args.target}"
    if args.target.startswith("windows-"):
        if not (ROOT / "dist/Auricle/Auricle.exe").is_file():
            parser.error("Build dist/Auricle/Auricle.exe first")
        result = shutil.make_archive(str(base), "zip", ROOT / "dist", "Auricle")
    else:
        bundle = ROOT / "dist/Auricle.app"
        if not bundle.is_dir():
            parser.error("Build dist/Auricle.app first")
        with tempfile.TemporaryDirectory(prefix="auricle-dmg-") as directory:
            staging = Path(directory)
            shutil.copytree(bundle, staging / "Auricle.app", symlinks=True)
            (staging / "Applications").symlink_to("/Applications", target_is_directory=True)
            result = str(base) + ".dmg"
            subprocess.run(["hdiutil", "create", "-volname", f"Auricle {version}",
                            "-srcfolder", str(staging), "-ov", "-format", "UDZO", result], check=True)
    print(result)


if __name__ == "__main__":
    main()
