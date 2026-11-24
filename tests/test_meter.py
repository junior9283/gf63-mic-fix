import struct
import subprocess

from gf63_mic_fix.meter import SILENCE_DB, LevelMeter, peak_dbfs
from gf63_mic_fix.sysrun import Runner


class _PopenRunner(Runner):
    """pw-record stand-in: a process that writes nothing until it is stopped."""

    def popen(self, args):
        return subprocess.Popen(["sleep", "30"], stdout=subprocess.PIPE)


def test_peak_dbfs_full_scale():
    assert abs(peak_dbfs(struct.pack("<3h", 0, -32768, 100))) < 0.01


def test_peak_dbfs_half_scale():
    assert abs(peak_dbfs(struct.pack("<2h", 16384, 0)) - (-6.02)) < 0.05


def test_peak_dbfs_silence():
    assert peak_dbfs(struct.pack("<4h", 0, 0, 0, 0)) == SILENCE_DB == -120.0


def test_peak_dbfs_ignores_odd_trailing_byte():
    assert peak_dbfs(b"") == SILENCE_DB
    assert abs(peak_dbfs(struct.pack("<h", 32767) + b"\x01")) < 0.01


def test_running_follows_start_and_stop():
    m = LevelMeter(_PopenRunner(), "src", lambda db: None)
    assert not m.running
    m.start()
    assert m.running
    m.stop()
    assert not m.running
