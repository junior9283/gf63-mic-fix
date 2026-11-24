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
        best = None
        for prefix, answer in self.rules.items():
            if _starts_with(args, prefix) and (best is None or len(prefix) > len(best[0])):
                best = (prefix, answer)
        if best is None:
            return Result(0, "", "")
        answer = best[1]
        return answer(args, input) if callable(answer) else answer

    def popen(self, args):
        raise NotImplementedError("FakeRunner.popen")

    def called(self, *prefix) -> bool:
        return any(_starts_with(c, prefix) for c in self.calls)


@pytest.fixture
def fake_runner():
    return FakeRunner()
