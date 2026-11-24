"""Detects the GF63 Thin, its Realtek ALC233 codec, PipeWire and the physical mic source."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .sysrun import Runner

PRODUCT_PREFIX = "GF63 Thin"
VERIFIED_PRODUCTS = {"GF63 Thin 10SC"}
ALC233_VENDOR_ID = "0x10ec0235"
MIN_PIPEWIRE = (1, 0, 0)
RNNOISE_LIB = "librnnoise_ladspa.so"
LADSPA_DIRS = (
    "/usr/lib64/ladspa",
    "/usr/lib/ladspa",
    "/usr/lib/x86_64-linux-gnu/ladspa",
    "~/.ladspa",
)


@dataclass
class Hardware:
    product: str
    verified: bool
    codec_card: int | None
    supported: bool


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _alc233_card(root: Path) -> int | None:
    for codec in sorted((root / "proc/asound").glob("card*/codec#*")):
        if re.search(rf"^Vendor Id:\s*{ALC233_VENDOR_ID}\b", _read(codec), re.M | re.I):
            return int(codec.parent.name.removeprefix("card"))
    return None


def detect_hardware(root: Path = Path("/")) -> Hardware:
    product = _read(root / "sys/class/dmi/id/product_name").strip()
    card = _alc233_card(root)
    return Hardware(
        product=product,
        verified=product in VERIFIED_PRODUCTS,
        codec_card=card,
        supported=product.startswith(PRODUCT_PREFIX) and card is not None,
    )


def pipewire_version(runner: Runner) -> tuple[int, int, int] | None:
    r = runner.run(["pactl", "info"])
    m = re.search(r"on PipeWire (\d+)\.(\d+)\.(\d+)", r.stdout) if r.ok else None
    return tuple(int(g) for g in m.groups()) if m else None


def find_physical_source(runner: Runner, card: int) -> str | None:
    """The capture source of the ALC233 card, found by card index, never by a fixed name."""
    r = runner.run(["pactl", "-f", "json", "list", "sources"])
    if not r.ok:
        return None
    try:
        sources = json.loads(r.stdout)
    except ValueError:
        return None
    for s in sources:
        props = s.get("properties", {})
        card_prop = props.get("alsa.card", props.get("api.alsa.card"))
        if card_prop == str(card) and props.get("device.class") == "sound" and not s.get("monitor_source"):
            return s["name"]
    return None


def find_rnnoise_plugin(dirs: tuple[str, ...] = LADSPA_DIRS) -> str | None:
    for d in dirs:
        p = Path(d).expanduser() / RNNOISE_LIB
        if p.is_file():
            return str(p)
    return None
