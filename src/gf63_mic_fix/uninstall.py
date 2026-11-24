"""Removes the fix and the program, like an uninstaller on Windows."""

import shutil
from pathlib import Path

from . import APP_ID, SERVICE, UPDATE_TIMER
from .fix import Fixer, FixError
from .sysrun import Runner

ROOT_UNINSTALLER = "/usr/libexec/gf63-mic-fix-uninstall"

# Everything packaging/install.sh puts in the home directory (universal installer).
UNIVERSAL_PATHS = (
    ".local/share/gf63-mic-fix",
    ".local/bin/gf63-mic-fix",
    f".local/share/applications/{APP_ID}.desktop",
    f".local/share/applications/{APP_ID}.Uninstall.desktop",
    f".local/share/icons/hicolor/scalable/apps/{APP_ID}.svg",
    f".config/systemd/user/{SERVICE}",
    ".config/systemd/user/gf63-mic-fix-update.service",
    f".config/systemd/user/{UPDATE_TIMER}",
)


def uninstall_steps(kind: str) -> list[list[str]]:
    """Root commands needed to remove the program for this install type."""
    return [["pkexec", ROOT_UNINSTALLER]] if kind in ("rpm", "deb", "arch") else []


def _remove_universal(home: Path) -> None:
    for rel in UNIVERSAL_PATHS:
        p = home / rel
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p, ignore_errors=True)
        else:
            p.unlink(missing_ok=True)


def uninstall(kind: str, fixer: Fixer, runner: Runner, home: Path | None = None) -> bool:
    """Undoes the fix for this user, then removes the program. False if removal failed or was cancelled."""
    home = home or Path.home()
    try:
        fixer.undo(purge=True)
    except FixError:
        pass  # undo already stopped the service and forgot the state; keep removing
    runner.run(["systemctl", "--user", "disable", "--now", UPDATE_TIMER])
    if kind == "universal":
        _remove_universal(home)
        runner.run(["systemctl", "--user", "daemon-reload"])
        return True
    steps = uninstall_steps(kind)
    return bool(steps) and all(runner.run(cmd, timeout=600).ok for cmd in steps)
