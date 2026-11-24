import math
import random
import struct
import wave

from conftest import PHYS, FakeSystem, make_root
from gf63_mic_fix import diagnose
from gf63_mic_fix.diagnose import Verdict
from gf63_mic_fix.fix import DIAGNOSIS_OK, Fixer

RATE = 48000


def stereo(seconds, left_tone=0.0, right_tone=0.0, noise=0.01, seed=1):
    """s16 interleaved stereo: white noise plus an optional 1 kHz tone per channel."""
    rnd = random.Random(seed)
    frames = []
    for i in range(int(seconds * RATE)):
        s = math.sin(2 * math.pi * 1000 * i / RATE)
        left = left_tone * s + rnd.uniform(-noise, noise)
        right = right_tone * s + rnd.uniform(-noise, noise)
        frames.append(struct.pack("<hh", int(left * 32767), int(right * 32767)))
    return b"".join(frames)


def test_goertzel_detects_1khz():
    tone = [math.sin(2 * math.pi * 1000 * i / RATE) for i in range(4800)]
    on = diagnose.goertzel_power(tone, RATE, 1000.0)
    off = diagnose.goertzel_power(tone, RATE, 3000.0)
    assert on > 1000 * off


def test_analyse_defect_confirmed():
    verdict, left_db, right_db = diagnose.analyse(stereo(1), stereo(1, right_tone=0.5, seed=2))
    assert verdict is Verdict.DEFECT_CONFIRMED
    assert right_db - left_db >= 20


def test_analyse_no_defect():
    verdict, _, _ = diagnose.analyse(stereo(1), stereo(1, left_tone=0.5, right_tone=0.5, seed=2))
    assert verdict is Verdict.NO_DEFECT


def test_analyse_inconclusive_when_silent():
    verdict, _, right_db = diagnose.analyse(stereo(1), stereo(1, seed=2))
    assert verdict is Verdict.INCONCLUSIVE
    assert right_db < 10


def test_analyse_inconclusive_on_empty_recording():
    assert diagnose.analyse(b"", b"")[0] is Verdict.INCONCLUSIVE


def test_tone_wav_header(tmp_path):
    p = tmp_path / "t.wav"
    diagnose.tone_wav(p)
    with wave.open(str(p)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (48000, 2, 2)
        assert w.getnframes() == 96000


class FakeRecorder:
    def __init__(self, recordings):
        self.recordings = list(recordings)
        self.volumes_seen = []

    def __call__(self, runner, source, seconds, rate=RATE):
        assert source == PHYS
        self.volumes_seen.append(runner.volumes[PHYS])
        return self.recordings.pop(0)


def _fixer(tmp_path, system):
    return Fixer(system, config_dir=tmp_path / "cfg", root=make_root(tmp_path, "GF63 Thin 11UC"))


def test_run_diagnosis_marks_ok_and_restores_volume(tmp_path):
    system = FakeSystem(volume=54)
    rec = FakeRecorder([stereo(0.5), stereo(0.5, right_tone=0.5, seed=2)])
    verdict = diagnose.run_diagnosis(
        _fixer(tmp_path, system), system, recorder=rec, player=lambda r, p: StubPlayback()
    )
    assert verdict is Verdict.DEFECT_CONFIRMED
    assert (tmp_path / "cfg" / DIAGNOSIS_OK).exists()
    assert rec.volumes_seen == [20, 20]  # measured at the fix's gain, not a clipping one
    assert system.volumes[PHYS] == 54


def test_run_diagnosis_no_defect_writes_nothing(tmp_path):
    system = FakeSystem()
    rec = FakeRecorder([stereo(0.5), stereo(0.5, left_tone=0.5, right_tone=0.5, seed=2)])
    verdict = diagnose.run_diagnosis(
        _fixer(tmp_path, system), system, recorder=rec, player=lambda r, p: StubPlayback()
    )
    assert verdict is Verdict.NO_DEFECT
    assert not (tmp_path / "cfg" / DIAGNOSIS_OK).exists()


class StubPlayback:
    def wait(self, timeout=None):
        return 0


def test_record_gives_up_when_recorder_hangs():
    import subprocess
    import time

    from conftest import FakeRunner

    class Silent(FakeRunner):
        def popen(self, args):
            return subprocess.Popen(["sleep", "30"], stdout=subprocess.PIPE)

    start = time.monotonic()
    data = diagnose.record(Silent(), PHYS, 0.1, deadline_s=0.5)
    assert data == b"" and time.monotonic() - start < 3


def test_run_diagnosis_without_pw_tools_raises_fix_error(tmp_path):
    import pytest

    from gf63_mic_fix.fix import FixError

    def missing(*args, **kwargs):
        raise FileNotFoundError("pw-record")

    system = FakeSystem(volume=54)
    with pytest.raises(FixError):
        diagnose.run_diagnosis(
            _fixer(tmp_path, system), system, recorder=missing, player=lambda r, p: StubPlayback()
        )
    assert system.volumes[PHYS] == 54


def no_playback(runner, wav):
    return StubPlayback()
