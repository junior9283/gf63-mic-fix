from conftest import FakeSystem, make_root
from gf63_mic_fix import UPDATE_TIMER, uninstall
from gf63_mic_fix.fix import Fixer
from gf63_mic_fix.sysrun import Result

UNIVERSAL_FILES = [
    ".local/share/gf63-mic-fix/gf63_mic_fix/__init__.py",
    ".local/bin/gf63-mic-fix",
    ".local/share/applications/io.github.junior9283.Gf63MicFix.desktop",
    ".local/share/applications/io.github.junior9283.Gf63MicFix.Uninstall.desktop",
    ".local/share/icons/hicolor/scalable/apps/io.github.junior9283.Gf63MicFix.svg",
    ".config/systemd/user/gf63-mic-fix.service",
    ".config/systemd/user/gf63-mic-fix-update.service",
    ".config/systemd/user/gf63-mic-fix-update.timer",
]


def test_uninstall_steps_per_type():
    root_cmd = [["pkexec", "/usr/libexec/gf63-mic-fix-uninstall"]]
    for kind in ("rpm", "deb", "arch"):
        assert uninstall.uninstall_steps(kind) == root_cmd
    assert uninstall.uninstall_steps("universal") == []
    assert uninstall.uninstall_steps("source") == []


def _fixer(tmp_path, system):
    return Fixer(system, config_dir=tmp_path / "home/.config/gf63-mic-fix", root=make_root(tmp_path))


def test_uninstall_universal_removes_files(tmp_path):
    home = tmp_path / "home"
    for rel in UNIVERSAL_FILES:
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_text("x")
    (home / ".local/share/applications/other.desktop").write_text("keep me")
    system = FakeSystem()
    fixer = _fixer(tmp_path, system)
    fixer.apply()

    assert uninstall.uninstall("universal", fixer, system, home=home) is True

    for rel in UNIVERSAL_FILES:
        assert not (home / rel).exists(), rel
    assert not (home / ".local/share/gf63-mic-fix").exists()
    assert not (home / ".config/gf63-mic-fix").exists()
    assert (home / ".local/share/applications/other.desktop").exists()
    assert system.called("systemctl", "--user", "disable", "--now", UPDATE_TIMER)
    assert not system.active


def test_uninstall_package_runs_pkexec_after_undo(tmp_path):
    system = FakeSystem()
    fixer = _fixer(tmp_path, system)
    fixer.apply()
    assert uninstall.uninstall("deb", fixer, system, home=tmp_path / "home") is True
    calls = system.calls
    undo_at = calls.index(["systemctl", "--user", "disable", "--now", "gf63-mic-fix.service"])
    assert calls.index(["pkexec", "/usr/libexec/gf63-mic-fix-uninstall"]) > undo_at


def test_uninstall_package_reports_cancelled_password(tmp_path):
    system = FakeSystem()
    system.rules[("pkexec",)] = Result(126, "", "dismissed")
    assert uninstall.uninstall("rpm", _fixer(tmp_path, system), system, home=tmp_path / "home") is False
