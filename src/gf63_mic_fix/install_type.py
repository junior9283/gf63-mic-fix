"""How this copy was installed. Packaging writes <app dir>/install-type."""

from pathlib import Path
from typing import Literal

InstallType = Literal["rpm", "deb", "arch", "universal", "source"]
KNOWN = ("rpm", "deb", "arch", "universal")


def app_dir() -> Path:
    """The directory that contains the gf63_mic_fix package."""
    return Path(__file__).resolve().parent.parent


def install_type() -> InstallType:
    try:
        kind = (app_dir() / "install-type").read_text().strip()
    except OSError:
        return "source"
    return kind if kind in KNOWN else "source"
