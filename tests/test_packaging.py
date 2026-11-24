"""The universal installer and the build script, run for real against a throwaway HOME."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from gf63_mic_fix import __version__, updater
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
    assert r.stdout.strip() == __version__


def test_apt_source_keeps_its_key_after_apt_remove():
    # `apt remove` keeps conffiles (all of /etc) but deletes /usr: the key must live in /etc too,
    # or every later `apt update` fails on a source with a missing key.
    sources = (ROOT / "data/gf63-mic-fix.sources").read_text()
    key = re.search(r"^Signed-By: (\S+)$", sources, re.M).group(1)
    assert key.startswith("/etc/")
    nfpm = (ROOT / "packaging/nfpm.yaml").read_text()
    assert f"dst: {key}\n    type: config\n    packager: deb" in nfpm


def test_installer_explains_a_release_without_version(tmp_path, sandbox):
    _, env, _ = sandbox
    bad = tmp_path / "release.json"
    bad.write_text('{"html_url": "https://example.invalid"}')
    r = subprocess.run(
        ["sh", str(INSTALL)], env={**env, "GF63_API_URL": bad.as_uri()}, capture_output=True, text=True
    )
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert "unexpected release data" in r.stderr


POSTREMOVE = ROOT / "packaging/postremove.sh"


@pytest.fixture
def user_links(tmp_path):
    """A user whose enabled units outlived the removed package, plus a healthy link."""
    units = tmp_path / "home/ana/.config/systemd/user"
    (units / "pipewire.service.wants").mkdir(parents=True)
    (units / "timers.target.wants").mkdir()
    dead = [
        units / "pipewire.service.wants/gf63-mic-fix.service",
        units / "timers.target.wants/gf63-mic-fix-update.timer",
    ]
    for link in dead:
        link.symlink_to(tmp_path / "usr/lib/systemd/user" / link.name)  # target is gone
    healthy = units / "pipewire.service.wants/other.service"
    healthy.symlink_to(POSTREMOVE)
    return tmp_path, dead, healthy


@pytest.mark.parametrize("arg", ["0", "remove", "purge", ""])
def test_postremove_cleans_dangling_links_on_removal(user_links, arg):
    root, dead, healthy = user_links
    subprocess.run(["sh", str(POSTREMOVE), arg], env={**os.environ, "GF63_ROOT": str(root)}, check=True)
    assert not any(p.is_symlink() for p in dead)
    assert healthy.is_symlink()


@pytest.mark.parametrize("arg", ["1", "upgrade", "failed-upgrade"])
def test_postremove_keeps_links_on_upgrade(user_links, arg):
    root, dead, _ = user_links
    subprocess.run(["sh", str(POSTREMOVE), arg], env={**os.environ, "GF63_ROOT": str(root)}, check=True)
    assert all(p.is_symlink() for p in dead)


def test_packages_run_the_postremove_cleanup():
    assert "postremove: packaging/postremove.sh" in (ROOT / "packaging/nfpm.yaml").read_text()
