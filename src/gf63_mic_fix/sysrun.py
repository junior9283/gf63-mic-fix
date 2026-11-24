"""Single entry point for external commands, so tests can replace it."""

import os
import subprocess
from dataclasses import dataclass


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _env() -> dict[str, str]:
    # pactl and friends translate their output; parsing needs the C locale.
    return {**os.environ, "LC_ALL": "C"}


class Runner:
    def run(self, args: list[str], *, input: bytes | None = None, timeout: float = 10) -> Result:
        try:
            p = subprocess.run(args, input=input, capture_output=True, timeout=timeout, env=_env())
        except FileNotFoundError as e:
            return Result(127, "", str(e))
        except subprocess.TimeoutExpired as e:
            return Result(124, "", f"timeout: {e}")
        return Result(p.returncode, p.stdout.decode(errors="replace"), p.stderr.decode(errors="replace"))

    def popen(self, args: list[str]) -> subprocess.Popen:
        return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=_env())
