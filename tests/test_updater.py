import io
import json
import shutil
import subprocess
import tarfile
import urllib.error

import pytest

from gf63_mic_fix import updater
from gf63_mic_fix.sysrun import Runner


def release_json(tag="v9.0.0"):
    name = f"gf63-mic-fix-{tag[1:]}.tar.gz"
    base = f"https://github.com/junior9283/gf63-mic-fix/releases/download/{tag}/"
    return json.dumps(
        {
            "tag_name": tag,
            "html_url": f"https://github.com/junior9283/gf63-mic-fix/releases/tag/{tag}",
            "assets": [
                {"name": name, "browser_download_url": base + name},
                {"name": name + ".asc", "browser_download_url": base + name + ".asc"},
            ],
        }
    ).encode()


def test_parse_version():
    assert updater.parse_version("v1.2.3") == (1, 2, 3)
    assert updater.parse_version("1.10.0") == (1, 10, 0)
    with pytest.raises(ValueError):
        updater.parse_version("latest")


def test_latest_release_parses():
    rel = updater.latest_release(lambda url: release_json())
    assert rel["version"] == (9, 0, 0)
    assert rel["assets"]["gf63-mic-fix-9.0.0.tar.gz"].endswith("/v9.0.0/gf63-mic-fix-9.0.0.tar.gz")


def test_check_handles_network_and_bad_json():
    def offline(url):
        raise urllib.error.URLError("no network")

    def rate_limited(url):
        raise urllib.error.HTTPError(url, 403, "rate limited", {}, io.BytesIO(b""))

    for fetch in (
        offline,
        rate_limited,
        lambda url: b"{",
        lambda url: b'{"tag_name": "nope"}',
        lambda url: b"[]",
    ):
        assert updater.latest_release(fetch) is None


class Spy:
    def __init__(self, result=True):
        self.calls, self.result = [], result

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


def test_scheduled_noop_on_rpm_deb():
    for kind in ("rpm", "deb", "source"):
        fetch, notifier = Spy(), Spy()
        updater.run_scheduled(kind=kind, fetch=fetch, notifier=notifier)
        assert not fetch.calls and not notifier.calls


def test_arch_notifies_only_when_newer():
    notifier = Spy()
    updater.run_scheduled(kind="arch", fetch=lambda u: release_json("v0.0.1"), notifier=notifier)
    assert not notifier.calls
    updater.run_scheduled(kind="arch", fetch=lambda u: release_json("v9.0.0"), notifier=notifier)
    assert len(notifier.calls) == 1 and "9.0.0" in notifier.calls[0][0]


def test_universal_without_fingerprint_only_notifies(monkeypatch):
    monkeypatch.setattr(updater, "SIGNING_FINGERPRINT", "")
    notifier, self_update = Spy(), Spy()
    updater.run_scheduled(
        kind="universal", fetch=lambda u: release_json(), notifier=notifier, updater=self_update
    )
    assert not self_update.calls and len(notifier.calls) == 1


def test_universal_self_updates(monkeypatch):
    monkeypatch.setattr(updater, "SIGNING_FINGERPRINT", "ABCD")
    notifier, self_update = Spy(True), Spy(True)
    updater.run_scheduled(
        kind="universal", fetch=lambda u: release_json(), notifier=notifier, updater=self_update
    )
    assert len(self_update.calls) == 1 and len(notifier.calls) == 1


def _tar(path, members):
    """members: list of (name, bytes | None for a symlink to '/etc')."""
    with tarfile.open(path, "w:gz") as t:
        for name, data in members:
            info = tarfile.TarInfo(name)
            if data is None:
                info.type, info.linkname = tarfile.SYMTYPE, "/etc"
                t.addfile(info)
            else:
                info.size, info.mode = len(data), 0o755
                t.addfile(info, io.BytesIO(data))


def test_safe_extract_rejects_traversal(tmp_path):
    _tar(tmp_path / "x.tar.gz", [("ok.txt", b"1"), ("../evil", b"x")])
    with pytest.raises(ValueError):
        updater.safe_extract(tmp_path / "x.tar.gz", tmp_path / "out")
    assert not (tmp_path / "evil").exists()


def test_safe_extract_rejects_absolute(tmp_path):
    _tar(tmp_path / "x.tar.gz", [("/tmp/gf63-evil", b"x")])
    with pytest.raises(ValueError):
        updater.safe_extract(tmp_path / "x.tar.gz", tmp_path / "out")


def test_safe_extract_rejects_link_outside(tmp_path):
    _tar(tmp_path / "x.tar.gz", [("link", None), ("link/passwd", b"x")])
    with pytest.raises(ValueError):
        updater.safe_extract(tmp_path / "x.tar.gz", tmp_path / "out")


def _fake_release_files(tmp_path, script):
    _tar(tmp_path / "rel.tar.gz", [("gf63-mic-fix-9.0.0/install.sh", script.encode())])
    files = {
        "https://x/gf63-mic-fix-9.0.0.tar.gz": (tmp_path / "rel.tar.gz").read_bytes(),
        "https://x/gf63-mic-fix-9.0.0.tar.gz.asc": b"sig",
    }
    release = {
        "version": (9, 0, 0),
        "html_url": "https://x",
        "assets": {"gf63-mic-fix-9.0.0.tar.gz": "https://x/gf63-mic-fix-9.0.0.tar.gz",
                   "gf63-mic-fix-9.0.0.tar.gz.asc": "https://x/gf63-mic-fix-9.0.0.tar.gz.asc"},
    }  # fmt: skip
    return release, files.__getitem__


def test_self_update_keeps_install_on_bad_signature(tmp_path):
    marker = tmp_path / "installed"
    release, fetch = _fake_release_files(tmp_path, f"#!/bin/sh\ntouch {marker}\n")
    ok = updater.self_update_universal(release, Runner(), fetch, verifier=lambda *a: False)
    assert ok is False and not marker.exists()


def test_self_update_runs_new_installer_after_valid_signature(tmp_path):
    marker = tmp_path / "installed"
    release, fetch = _fake_release_files(tmp_path, f'#!/bin/sh\necho "$@" > {marker}\n')
    ok = updater.self_update_universal(release, Runner(), fetch, verifier=lambda *a: True)
    assert ok is True
    assert marker.read_text().startswith("--from-dir ")


@pytest.fixture(scope="module")
def signing_key(tmp_path_factory):
    if not shutil.which("gpg"):
        pytest.skip("needs gpg")
    home = tmp_path_factory.mktemp("gnupg")
    home.chmod(0o700)
    gpg = ["gpg", "--batch", "--homedir", str(home), "--passphrase", "", "--pinentry-mode", "loopback"]
    subprocess.run(
        [*gpg, "--quick-gen-key", "Test Key", "ed25519", "sign", "never"], check=True, capture_output=True
    )
    out = subprocess.run(
        [*gpg, "--with-colons", "--list-keys"], check=True, capture_output=True, text=True
    ).stdout
    fpr = next(line.split(":")[9] for line in out.splitlines() if line.startswith("fpr:"))
    pub = home / "pub.asc"
    pub.write_text(
        subprocess.run([*gpg, "--armor", "--export", fpr], check=True, capture_output=True, text=True).stdout
    )
    yield gpg, fpr, pub
    subprocess.run(["gpgconf", "--homedir", str(home), "--kill", "all"], capture_output=True)


@pytest.mark.slow
def test_verify_signature_accepts_valid(tmp_path, signing_key):
    gpg, fpr, pub = signing_key
    f = tmp_path / "file"
    f.write_bytes(b"payload")
    subprocess.run([*gpg, "--armor", "--detach-sign", "-o", str(f) + ".asc", str(f)], check=True)
    assert updater.verify_signature(f, tmp_path / "file.asc", pub, Runner(), fingerprint=fpr)


@pytest.mark.slow
def test_verify_signature_rejects_wrong_key_and_tampering(tmp_path, signing_key):
    gpg, fpr, pub = signing_key
    f = tmp_path / "file"
    f.write_bytes(b"payload")
    subprocess.run([*gpg, "--armor", "--detach-sign", "-o", str(f) + ".asc", str(f)], check=True)
    assert not updater.verify_signature(f, tmp_path / "file.asc", pub, Runner(), fingerprint="0" * 40)
    assert not updater.verify_signature(f, tmp_path / "file.asc", pub, Runner(), fingerprint="")
    f.write_bytes(b"tampered")
    assert not updater.verify_signature(f, tmp_path / "file.asc", pub, Runner(), fingerprint=fpr)
