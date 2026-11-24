"""The universal installer and the build script, run for real against a throwaway HOME."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from gf63_mic_fix import updater
from gf63_mic_fix.uninstall import UNIVERSAL_PATHS, _remove_universal

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "packaging/install.sh"


def test_installer_embeds_the_project_key():
    text = INSTALL.read_text()
    assert (ROOT / "data/signing-key.asc").read_text().strip() in text
    assert f"FINGERPRINT={updater.SIGNING_FINGERPRINT}\n" in text
    assert updater.SIGNING_FINGERPRINT


def test_build_refuses_a_version_that_is_not_the_code_version(tmp_path):
    r = subprocess.run(
        ["sh", str(ROOT / "packaging/build.sh"), "9.9.9", str(tmp_path)], capture_output=True, text=True
    )
    assert r.returncode == 1
    assert "does not match" in r.stderr


@pytest.fixture
def release(tmp_path):
    """An extracted release, laid out like the universal tarball."""
    top = tmp_path / "gf63-mic-fix-1.0.0"
    shutil.copytree(ROOT / "src/gf63_mic_fix", top / "app/gf63_mic_fix")
    shutil.copytree(ROOT / "bin", top / "bin")
    shutil.copytree(ROOT / "data", top / "data")
    return top


@pytest.fixture
def sandbox(tmp_path):
    """HOME in tmp; systemctl only records what it was asked."""
    home = tmp_path / "home"
    fakebin = tmp_path / "fakebin"
    home.mkdir()
    fakebin.mkdir()
    log = tmp_path / "systemctl.log"
    (fakebin / "systemctl").write_text(f'#!/bin/sh\necho "$*" >> {log}\n')
    (fakebin / "systemctl").chmod(0o755)
    env = {**os.environ, "HOME": str(home), "PATH": f"{fakebin}:{os.environ['PATH']}"}
    return home, env, log


def install(release, env):
    return subprocess.run(
        ["sh", str(INSTALL), "--from-dir", str(release)], env=env, capture_output=True, text=True, timeout=60
    )


def installed_files(home: Path) -> set[str]:
    return {str(p.relative_to(home)) for p in home.rglob("*") if p.is_file()}


def test_install_puts_exactly_what_the_uninstaller_removes(release, sandbox):
    home, env, _ = sandbox
    r = install(release, env)
    assert r.returncode == 0, r.stderr

    top_level = set()
    for f in installed_files(home):
        owner = [p for p in UNIVERSAL_PATHS if f == p or f.startswith(p + "/")]
        assert owner, f"installed but never uninstalled: {f}"
        top_level.add(owner[0])
    assert top_level == set(UNIVERSAL_PATHS)

    _remove_universal(home)
    assert installed_files(home) == set()


def test_install_points_menu_and_timer_at_the_user_copy(release, sandbox):
    home, env, log = sandbox
    assert install(release, env).returncode == 0
    exe = home / ".local/bin/gf63-mic-fix"
    desktop = (home / ".local/share/applications/io.github.junior9283.Gf63MicFix.desktop").read_text()
    assert f"Exec={exe}\n" in desktop
    unit = (home / ".config/systemd/user/gf63-mic-fix-update.service").read_text()
    assert f"ExecStart={exe} --check-update" in unit
    assert (home / ".local/share/gf63-mic-fix/install-type").read_text().strip() == "universal"
    assert os.access(exe, os.X_OK)
    assert "enable --now gf63-mic-fix-update.timer" in log.read_text()


def test_install_twice_is_an_update_not_a_mess(release, sandbox):
    home, env, _ = sandbox
    assert install(release, env).returncode == 0
    first = installed_files(home)
    (release / "app/gf63_mic_fix/new_module.py").write_text("")
    assert install(release, env).returncode == 0
    assert installed_files(home) == first | {".local/share/gf63-mic-fix/gf63_mic_fix/new_module.py"}
    assert not any(re.search(r"\.(new|old|tmp)$", f) for f in installed_files(home))


def test_installed_launcher_runs_from_the_user_copy(release, sandbox):
    home, env, _ = sandbox
    assert install(release, env).returncode == 0
    r = subprocess.run(
        [str(home / ".local/bin/gf63-mic-fix"), "--version"], env=env, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
    assert "1.0.0" in r.stdout
