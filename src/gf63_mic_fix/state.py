"""What the system looked like before the fix, so undo can put it back."""

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

STATE_FILE = "state.json"


@dataclass
class SavedState:
    default_source: str | None
    physical_volume_percent: int | None
    noise_suppression: bool = False


def load(dir: Path) -> SavedState | None:
    try:
        return SavedState(**json.loads((dir / STATE_FILE).read_text()))
    except (OSError, ValueError, TypeError):
        return None


def save(dir: Path, s: SavedState) -> None:
    dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir, prefix=".state-")
    with os.fdopen(fd, "w") as f:
        json.dump(asdict(s), f)
    os.replace(tmp, dir / STATE_FILE)


def clear(dir: Path) -> None:
    shutil.rmtree(dir, ignore_errors=True)
