import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gf63_mic_fix import __version__, cli, i18n, install_type
from gf63_mic_fix.fix import FixError, Status

ROOT = Path(__file__).resolve().parents[1]


class StubFixer:
    def __init__(self, status=Status.NOT_FIXED, error=None):
        self._status, self.error, self.calls = status, error, []

    def status(self):
        return self._status

    def apply(self):
        self.calls.append("apply")
        if self.error:
            raise FixError(self.error)

    def undo(self):
        self.calls.append("undo")


@pytest.mark.parametrize(
    "status,code",
    [
        (Status.FIXED, 0),
        (Status.NOT_FIXED, 1),
        (Status.FIXED_NOT_DEFAULT, 1),
        (Status.UNSUPPORTED, 2),
        (Status.NEEDS_DIAGNOSIS, 2),
        (Status.NO_PIPEWIRE, 3),
        (Status.OLD_PIPEWIRE, 3),
    ],
)
def test_status_exit_codes(status, code, capsys):
    assert cli.main(["--status"], fixer=StubFixer(status)) == code
    assert capsys.readouterr().out.strip() == status.name


def test_apply_error_goes_to_stderr(capsys):
    f = StubFixer(error="boom")
    assert cli.main(["--apply"], fixer=f) == 1
    assert "boom" in capsys.readouterr().err
    assert f.calls == ["apply"]


def test_undo_ok():
    f = StubFixer()
    assert cli.main(["--undo"], fixer=f) == 0
    assert f.calls == ["undo"]


def test_version(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_install_type_default_source():
    assert install_type.install_type() == "source"


def test_install_type_reads_file(tmp_path, monkeypatch):
    (tmp_path / "install-type").write_text("deb\n")
    monkeypatch.setattr(install_type, "app_dir", lambda: tmp_path)
    assert install_type.install_type() == "deb"
    (tmp_path / "install-type").write_text("nonsense\n")
    assert install_type.install_type() == "source"


@pytest.fixture
def compiled_locale(tmp_path, monkeypatch):
    mo = tmp_path / "locale/pt_BR/LC_MESSAGES/gf63-mic-fix.mo"
    mo.parent.mkdir(parents=True)
    subprocess.run(["msgfmt", "-o", str(mo), str(ROOT / "po/pt_BR.po")], check=True)
    monkeypatch.setenv("LANGUAGE", "pt_BR")
    monkeypatch.setattr(i18n, "LOCALE_DIR", tmp_path / "locale")
    i18n.reload()
    yield
    monkeypatch.undo()
    i18n.reload()


def test_translation_pt_br(compiled_locale):
    assert i18n._("Internal microphone (fixed)") == "Microfone interno (corrigido)"


def _entries(po_text: str) -> dict[str, str]:
    """msgid -> msgstr, joining the continuation lines gettext uses for long strings."""
    out = {}
    for block in po_text.split("\n\n"):
        fields, key = {}, None
        for line in block.splitlines():
            if line.startswith(("msgid ", "msgstr ")):
                key, _, rest = line.partition(" ")
                fields[key] = rest[1:-1]
            elif line.startswith('"') and key:
                fields[key] += line[1:-1]
        if fields.get("msgid"):
            out[fields["msgid"]] = fields.get("msgstr", "")
    return out


@pytest.mark.skipif(not shutil.which("xgettext"), reason="needs gettext")
def test_pt_br_translates_every_string(tmp_path):
    pot = tmp_path / "x.pot"
    sources = sorted(str(p) for p in (ROOT / "src").rglob("*.py"))
    subprocess.run(
        ["xgettext", "-L", "Python", "--keyword=_", "--from-code=UTF-8", "-o", str(pot), *sources], check=True
    )
    po = _entries((ROOT / "po/pt_BR.po").read_text())
    missing = [m for m in _entries(pot.read_text()) if not po.get(m)]
    assert not missing, f"untranslated: {missing}"


def test_launcher_runs_from_app_dir():
    env = {**os.environ, "GF63_MIC_FIX_APPDIR": str(ROOT / "src")}
    out = subprocess.run(
        [str(ROOT / "bin/gf63-mic-fix"), "--version"], env=env, capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == __version__
