"""Weekly update check for the Arch package and the universal installer.

rpm and deb installs are updated by dnf/apt from the project's signed repositories,
so this module does nothing for them. The only request made is to the public GitHub
releases API; no data about the user or the machine is sent.
"""

import json
import logging
import shutil
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

from . import APP_ID, __version__
from .i18n import _
from .install_type import app_dir, install_type
from .sysrun import Runner

REPO = "junior9283/gf63-mic-fix"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
SIGNING_FINGERPRINT = ""  # filled in when the signing key is created; empty disables self-update

log = logging.getLogger(__name__)
Fetch = Callable[[str], bytes]


def parse_version(tag: str) -> tuple[int, int, int]:
    parts = tag.removeprefix("v").split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"not a version: {tag!r}")
    return tuple(int(p) for p in parts)


def urllib_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"gf63-mic-fix/{__version__}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def latest_release(fetch: Fetch = urllib_fetch) -> dict | None:
    """{"version", "html_url", "assets": {name: url}}, or None on any error."""
    try:
        data = json.loads(fetch(API_LATEST))
        return {
            "version": parse_version(data["tag_name"]),
            "html_url": data["html_url"],
            "assets": {a["name"]: a["browser_download_url"] for a in data.get("assets", [])},
        }
    except Exception as e:  # network, HTTP, JSON or shape: never break the timer
        log.info("update check failed: %s", e)
        return None


def verify_signature(
    file: Path, sig: Path, pubkey: Path, runner: Runner, fingerprint: str | None = None
) -> bool:
    """True only for a good signature made by the pinned project key."""
    fingerprint = SIGNING_FINGERPRINT if fingerprint is None else fingerprint
    if not fingerprint:
        return False
    with tempfile.TemporaryDirectory() as home:
        gpg = ["gpg", "--batch", "--no-tty", "--homedir", home]
        try:
            if not runner.run([*gpg, "--import", str(pubkey)]).ok:
                return False
            r = runner.run([*gpg, "--status-fd", "1", "--verify", str(sig), str(file)])
        finally:
            runner.run(["gpgconf", "--homedir", home, "--kill", "all"])
    return r.ok and f"[GNUPG:] VALIDSIG {fingerprint.upper()} " in r.stdout


def _check_member(m: tarfile.TarInfo, dest: Path) -> None:
    target = (dest / m.name).resolve()
    if m.name.startswith("/") or not target.is_relative_to(dest):
        raise ValueError(f"unsafe path in archive: {m.name}")
    if m.issym() or m.islnk():
        link = (target.parent / m.linkname).resolve()
        if m.linkname.startswith("/") or not link.is_relative_to(dest):
            raise ValueError(f"unsafe link in archive: {m.name}")
    elif not (m.isfile() or m.isdir()):
        raise ValueError(f"unsupported member in archive: {m.name}")


def safe_extract(tar: Path, dest: Path) -> None:
    """Extracts only regular files, directories and links that stay inside `dest`."""
    dest.mkdir(parents=True, exist_ok=True)
    dest = dest.resolve()
    with tarfile.open(tar) as t:
        members = t.getmembers()
        for m in members:
            _check_member(m, dest)
        try:
            t.extractall(dest, members=members, filter="data")
        except tarfile.FilterError as e:
            raise ValueError(str(e)) from e


def self_update_universal(
    release: dict,
    runner: Runner,
    fetch: Fetch = urllib_fetch,
    verifier: Callable[..., bool] = verify_signature,
) -> bool:
    """Downloads, verifies and installs a release. Any failure leaves the current install as is."""
    version = ".".join(map(str, release["version"]))
    name = f"gf63-mic-fix-{version}.tar.gz"
    assets = release["assets"]
    if name not in assets or name + ".asc" not in assets:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tar, sig = tmp / name, tmp / (name + ".asc")
        try:
            tar.write_bytes(fetch(assets[name]))
            sig.write_bytes(fetch(assets[name + ".asc"]))
        except Exception as e:
            log.info("download failed: %s", e)
            return False
        if not verifier(tar, sig, app_dir() / "signing-key.asc", runner):
            log.warning("signature check failed for %s; not installing", name)
            return False
        try:
            safe_extract(tar, tmp / "x")
        except (ValueError, tarfile.TarError) as e:
            log.warning("bad archive %s: %s", name, e)
            return False
        tops = [p for p in (tmp / "x").iterdir() if p.is_dir()]
        if len(tops) != 1 or not (tops[0] / "install.sh").is_file():
            return False
        return runner.run(["sh", str(tops[0] / "install.sh"), "--from-dir", str(tops[0])], timeout=120).ok


def notify(title: str, body: str, url: str) -> None:
    """Desktop notification over D-Bus; silently does nothing without a session bus."""
    try:
        from gi.repository import Gio, GLib

        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications",
            "Notify",
            GLib.Variant("(susssasa{sv}i)", ("GF63 Mic Fix", 0, APP_ID, title, f"{body}\n{url}", [], {}, -1)),
            None,
            Gio.DBusCallFlags.NONE,
            5000,
            None,
        )
    except Exception as e:
        log.info("notification failed: %s", e)


def run_scheduled(
    runner: Runner | None = None,
    fetch: Fetch = urllib_fetch,
    kind: str | None = None,
    notifier: Callable[[str, str, str], None] = notify,
    updater: Callable[..., bool] = self_update_universal,
) -> None:
    kind = kind or install_type()
    if kind not in ("arch", "universal"):
        return
    release = latest_release(fetch)
    if not release or release["version"] <= parse_version(__version__):
        return
    version = ".".join(map(str, release["version"]))
    url = release["html_url"]
    if kind == "universal" and SIGNING_FINGERPRINT and shutil.which("gpg"):
        if updater(release, runner or Runner(), fetch):
            notifier(_("GF63 Mic Fix was updated"), _("Version %s is now installed.") % version, url)
            return
    notifier(_("GF63 Mic Fix %s is available") % version, _("Download the new version at:"), url)
