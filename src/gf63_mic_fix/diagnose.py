"""Confirms the known defect on GF63 Thin variants that were not verified yet.

A 1 kHz tone is played on the speakers while both capture channels are recorded.
The defect is confirmed when the right channel picks the tone up and the left one
does not: the left channel is not wired to the microphone.
"""

import math
import struct
import tempfile
import time
import wave
from collections.abc import Callable, Sequence
from enum import Enum
from pathlib import Path

from . import APPLY_VOLUME
from .fix import DIAGNOSIS_OK, Fixer
from .sysrun import Runner

RATE = 48000
FREQ = 1000.0
MIN_RIGHT_GAIN_DB = 10.0  # the tone must rise at least this much over silence on the right
MIN_CHANNEL_GAP_DB = 20.0  # ...and this much more than on the left
SILENCE_S = 1.5
TONE_S = 2.0
SETTLE_S = 0.3  # skip the start of playback


class Verdict(Enum):
    DEFECT_CONFIRMED = "defect-confirmed"
    NO_DEFECT = "no-defect"
    INCONCLUSIVE = "inconclusive"


def tone_wav(path: Path, freq=FREQ, seconds=TONE_S, rate=RATE, amplitude=0.3) -> None:
    n = int(seconds * rate)
    frames = bytearray()
    for i in range(n):
        v = int(amplitude * 32767 * math.sin(2 * math.pi * freq * i / rate))
        frames += struct.pack("<hh", v, v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def goertzel_power(samples: Sequence[float], rate: int, freq: float) -> float:
    """Power of one frequency bin, normalised by the number of samples."""
    n = len(samples)
    if n == 0:
        return 0.0
    coeff = 2 * math.cos(2 * math.pi * freq / rate)
    s1 = s2 = 0.0
    for x in samples:
        s1, s2 = x + coeff * s1 - s2, s1
    return (s1 * s1 + s2 * s2 - coeff * s1 * s2) / (n * n)


def _channels(pcm: bytes) -> tuple[list[float], list[float]]:
    usable = len(pcm) - len(pcm) % 4
    values = struct.unpack(f"<{usable // 2}h", pcm[:usable])
    return [v / 32768 for v in values[0::2]], [v / 32768 for v in values[1::2]]


def analyse(silence: bytes, tone: bytes, rate: int = RATE) -> tuple[Verdict, float, float]:
    """Returns (verdict, left gain dB, right gain dB): how much the 1 kHz bin rose with the tone."""
    gains = []
    for quiet, loud in zip(_channels(silence), _channels(tone), strict=True):
        before = goertzel_power(quiet, rate, FREQ)
        after = goertzel_power(loud, rate, FREQ)
        gains.append(10 * math.log10((after + 1e-15) / (before + 1e-15)))
    left, right = gains
    if right < MIN_RIGHT_GAIN_DB:
        return Verdict.INCONCLUSIVE, left, right
    if right - left >= MIN_CHANNEL_GAP_DB:
        return Verdict.DEFECT_CONFIRMED, left, right
    return Verdict.NO_DEFECT, left, right


def record(runner: Runner, source: str, seconds: float, rate: int = RATE) -> bytes:
    """Raw s16 stereo from `source`, read from pw-record's stdout."""
    wanted = int(seconds * rate) * 4
    p = runner.popen(
        ["pw-record", "--raw", "--target", source, "--channels", "2", "--format", "s16",
         "--rate", str(rate), "-"]
    )  # fmt: skip
    data = bytearray()
    try:
        while len(data) < wanted:
            chunk = p.stdout.read(wanted - len(data))
            if not chunk:
                break
            data += chunk
    finally:
        p.terminate()
        p.wait(timeout=5)
    return bytes(data)


def play(runner: Runner, wav: Path):
    return runner.popen(["pw-play", str(wav)])


def run_diagnosis(
    fixer: Fixer,
    runner: Runner,
    recorder: Callable[..., bytes] = record,
    player: Callable[[Runner, Path], object] = play,
) -> Verdict:
    physical = fixer.physical_source()
    previous = fixer.get_gain()
    fixer.set_physical_volume(APPLY_VOLUME)  # a clipping capture would hide the tone
    try:
        silence = recorder(runner, physical, SILENCE_S)
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "tone.wav"
            tone_wav(wav)
            proc = player(runner, wav)
            time.sleep(SETTLE_S if proc is not None else 0)
            tone = recorder(runner, physical, TONE_S - SETTLE_S - 0.2)
            if proc is not None:
                proc.wait(timeout=10)
    finally:
        fixer.set_physical_volume(previous)
    verdict, _, _ = analyse(silence, tone)
    if verdict is Verdict.DEFECT_CONFIRMED:
        fixer.config_dir.mkdir(parents=True, exist_ok=True)
        (fixer.config_dir / DIAGNOSIS_OK).write_text("")
    return verdict
