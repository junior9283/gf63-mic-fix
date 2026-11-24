import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gf63_mic_fix.sysrun import Result, Runner  # noqa: E402


def _starts_with(args, prefix) -> bool:
    return tuple(args[: len(prefix)]) == tuple(prefix)


class FakeRunner(Runner):
    """Records every call and answers from rules keyed by an argument prefix.

    A rule value is a Result or a callable(args, input) -> Result. The longest
    matching prefix wins; unmatched calls return Result(0, "", "").
    """

    def __init__(self, rules=None):
        self.rules = dict(rules or {})
        self.calls: list[list[str]] = []

    def run(self, args, *, input=None, timeout=10):
        self.calls.append(list(args))
        matches = [prefix for prefix in self.rules if _starts_with(args, prefix)]
        if not matches:
            return Result(0, "", "")
        answer = self.rules[max(matches, key=len)]
        return answer(args, input) if callable(answer) else answer

    def popen(self, args):
        raise NotImplementedError("FakeRunner.popen")

    def called(self, *prefix) -> bool:
        return any(_starts_with(c, prefix) for c in self.calls)


@pytest.fixture
def fake_runner():
    return FakeRunner()


PHYS = "alsa_input.pci-0000_00_1f.3.analog-stereo"
ALC233 = "Codec: Realtek ALC233\nVendor Id: 0x10ec0235\n"


HDMI = "Codec: Intel Kabylake HDMI\nVendor Id: 0x8086280b\n"


def make_root(tmp_path, product="GF63 Thin 10SC", codecs=None):
    """Fake / with DMI product name and /proc/asound codecs ({card: [codec texts]})."""
    root = tmp_path / "root"
    dmi = root / "sys/class/dmi/id"
    dmi.mkdir(parents=True)
    if product is not None:
        (dmi / "product_name").write_text(product + "\n")
    for card, files in (codecs if codecs is not None else {0: [ALC233, HDMI]}).items():
        d = root / f"proc/asound/card{card}"
        d.mkdir(parents=True)
        for i, text in enumerate(files):
            (d / f"codec#{i}").write_text(text)
    return root


class FakeSystem(FakeRunner):
    """A stateful stand-in for pactl + systemctl --user.

    Starting the service makes the virtual source appear unless node_appears is False.
    """

    def __init__(self, default=PHYS, volume=54, pipewire="1.6.11", node_appears=True):
        super().__init__()
        self.default = default
        self.sources = [PHYS]
        self.volumes = {PHYS: volume}
        self.pipewire = pipewire
        self.node_appears = node_appears
        self.active = False
        self.enabled = False
        self.fail_volume = False
        self.fail_starts = 0  # the next N (re)starts do not bring the node up

    def run(self, args, *, input=None, timeout=10):
        self.calls.append(list(args))
        a = list(args)
        if a[:2] == ["pactl", "info"]:
            name = f"PulseAudio (on PipeWire {self.pipewire})" if self.pipewire else "pulseaudio"
            return Result(0, f"Server Name: {name}\n", "")
        if a[:5] == ["pactl", "-f", "json", "list", "sources"]:
            data = [
                {
                    "name": s,
                    "monitor_source": "",
                    "properties": {"alsa.card": "0", "device.class": "sound"}
                    if s.startswith("alsa_")
                    else {},
                }
                for s in self.sources
            ]
            return Result(0, json.dumps(data), "")
        if a[:2] == ["pactl", "get-default-source"]:
            return Result(0, (self.default or "") + "\n", "")
        if a[:2] == ["pactl", "set-default-source"]:
            self.default = a[2]
            return Result(0, "", "")
        if a[:2] == ["pactl", "get-source-volume"]:
            v = self.volumes.get(a[2], 100)
            return Result(
                0, f"Volume: front-left: 1 / {v:3d}% / -1.00 dB,   front-right: 1 / {v:3d}% / -1 dB\n", ""
            )
        if a[:2] == ["pactl", "set-source-volume"]:
            if self.fail_volume:
                return Result(1, "", "Failure: No such entity")
            self.volumes[a[2]] = int(a[3].rstrip("%"))
            return Result(0, "", "")
        if a[:2] == ["systemctl", "--user"]:
            return self._systemctl(a[2:])
        return Result(0, "", "")

    def _systemctl(self, a):
        from gf63_mic_fix import VIRTUAL_SOURCE

        verb = a[0]
        if verb == "is-active":
            return Result(0 if self.active else 3, "active\n" if self.active else "inactive\n", "")
        if verb in ("restart", "start") or (verb == "enable" and "--now" in a):
            self.enabled = self.enabled or verb == "enable"
            self.active = True
            # A (re)start tears the node down and brings it back only if the chain loads.
            if VIRTUAL_SOURCE in self.sources:
                self.sources.remove(VIRTUAL_SOURCE)
            if self.fail_starts:
                self.fail_starts -= 1
            elif self.node_appears:
                self.sources.append(VIRTUAL_SOURCE)
        elif verb == "enable":
            self.enabled = True
        elif verb in ("disable", "stop"):
            self.enabled = self.enabled and verb == "stop"
            if verb == "stop" or "--now" in a:
                self.active = False
                if VIRTUAL_SOURCE in self.sources:
                    self.sources.remove(VIRTUAL_SOURCE)
                if self.default == VIRTUAL_SOURCE:
                    self.default = PHYS  # WirePlumber elects another source
        return Result(0, "", "")


@pytest.fixture
def system():
    return FakeSystem()
