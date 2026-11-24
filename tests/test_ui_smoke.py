"""Opens the real window under GTK's broadway backend (no screen, no browser) for every status."""

import os
import shutil
import struct
import subprocess
import time
from pathlib import Path

import pytest

from gf63_mic_fix.fix import Status

ROOT = Path(__file__).resolve().parents[1]
DISPLAY = ":17"

pytestmark = [
    pytest.mark.ui,
    pytest.mark.skipif(not shutil.which("gtk4-broadwayd"), reason="needs gtk4-broadwayd"),
]


@pytest.fixture(scope="module")
def broadway(tmp_path_factory):
    runtime = tmp_path_factory.mktemp("xdg")
    runtime.chmod(0o700)
    env = {**os.environ, "XDG_RUNTIME_DIR": str(runtime)}
    proc = subprocess.Popen(
        ["gtk4-broadwayd", DISPLAY], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(0.5)
    yield {**env, "GDK_BACKEND": "broadway", "BROADWAY_DISPLAY": DISPLAY, "GSK_RENDERER": "cairo"}
    proc.terminate()
    proc.wait(timeout=5)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


@pytest.mark.parametrize("status", list(Status))
def test_window_opens_for_each_status(status, broadway, tmp_path):
    out = tmp_path / f"{status.name}.png"
    env = {**broadway, "GF63_MIC_FIX_APPDIR": str(ROOT / "src")}
    r = subprocess.run(
        [str(ROOT / "bin/gf63-mic-fix"), "--screenshot", str(out), "--fake-status", status.name],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    width, height = png_size(out)
    assert width > 300 and height > 300
