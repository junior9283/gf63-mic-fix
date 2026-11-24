"""Live input level for the window, read from pw-record while the window is visible."""

import math
import os
import sys
from array import array
from collections.abc import Callable

from .sysrun import Runner

SILENCE_DB = -120.0
RATE = 48000
CHUNK_BYTES = 2400 * 2  # 50 ms of mono s16


def peak_dbfs(chunk: bytes) -> float:
    """Peak of little-endian s16 samples, in dBFS (0 = full scale)."""
    samples = array("h", chunk[: len(chunk) - len(chunk) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    peak = max((abs(v) for v in samples), default=0)
    return 20 * math.log10(peak / 32768) if peak else SILENCE_DB


class LevelMeter:
    def __init__(self, runner: Runner, source: str, callback: Callable[[float], None]):
        self.runner, self.source, self.callback = runner, source, callback
        self._proc = None
        self._watch = 0

    def start(self) -> None:
        from gi.repository import GLib

        if self._proc:
            return
        try:
            self._proc = self.runner.popen(
                ["pw-record", "--raw", "--target", self.source, "--channels", "1", "--format", "s16",
                 "--rate", str(RATE), "-"]
            )  # fmt: skip
        except OSError:
            self._proc = None
            return
        self._watch = GLib.unix_fd_add_full(
            GLib.PRIORITY_DEFAULT,
            self._proc.stdout.fileno(),
            GLib.IOCondition.IN | GLib.IOCondition.HUP | GLib.IOCondition.ERR,
            self._on_data,
        )

    def _on_data(self, fd, condition) -> bool:
        data = os.read(fd, CHUNK_BYTES) if condition & 1 else b""  # G_IO_IN
        if not data:
            self._watch = 0
            self.stop()
            return False
        self.callback(peak_dbfs(data))
        return True

    def stop(self) -> None:
        from gi.repository import GLib

        if self._watch:
            GLib.source_remove(self._watch)
            self._watch = 0
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.kill()
            self._proc = None
