"""GF63 Mic Fix: fixes the noisy internal microphone of MSI GF63 Thin laptops on Linux."""

from pathlib import Path

__version__ = "1.0.1"

APP_ID = "io.github.junior9283.Gf63MicFix"
PACKAGE = "gf63-mic-fix"
SERVICE = "gf63-mic-fix.service"
UPDATE_TIMER = "gf63-mic-fix-update.timer"

# The correction, as measured on a GF63 Thin 10SC (ALC233) on 2026-11-24.
VIRTUAL_SOURCE = "gf63_mic_fix"
CHANNEL = "FR"  # the only channel wired to the digital microphone
HIGHPASS = ((120.0, 0.54), (120.0, 1.31))  # 4th-order Butterworth as two biquads
APPLY_VOLUME = 20  # % of the physical source: +18 dB, no boost
GAIN_MIN, GAIN_MAX = 10, 30  # % (0 to +28 dB); above this the capture clips
PRIORITY = 3000

CONFIG_DIR = Path.home() / ".config" / "gf63-mic-fix"


def format_version(v: tuple[int, ...]) -> str:
    return ".".join(map(str, v))
