"""Resource paths for source checkouts, installed wheels and frozen apps."""
from importlib.util import find_spec
from pathlib import Path
import sys

REQUIRED_ASSETS = (
    "auricle_logo.png", "auricle_logo2.png", "auricle_icon.png",
    "auricle.ico", "auricle.icns",
)


def asset_path(name: str) -> Path:
    """Return an artwork path without depending on the working directory."""
    source = Path(__file__).resolve().parent / "assets" / name
    if source.is_file():
        return source
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        frozen = Path(bundle) / "assets" / name
        if frozen.is_file():
            return frozen
    package = find_spec("auricle_assets")
    if package and package.origin:
        return Path(package.origin).parent / name
    return source
