"""Write checksums for the files attached to a release."""
import hashlib
from pathlib import Path
import sys


def main():
    directory = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
    entries = sorted(p for p in directory.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
    if not entries:
        sys.exit("No release files to checksum")
    lines = []
    for path in entries:
        with path.open("rb") as stream:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        lines.append(f"{digest.hexdigest()}  {path.name}\n")
    (directory / "SHA256SUMS.txt").write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
