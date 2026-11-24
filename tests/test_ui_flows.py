"""UI flow logic without a display: dialogs are replaced, the GLib loop is real."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import GLib  # noqa: E402

from gf63_mic_fix.i18n import _  # noqa: E402
from gf63_mic_fix.ui import uninstall as flow_mod  # noqa: E402


class FakeWindow:
    sensitive = True

    def set_sensitive(self, value):
        self.sensitive = value


def run_until(predicate, timeout_s=3.0):
    ctx = GLib.MainContext.default()
    deadline = GLib.get_monotonic_time() + int(timeout_s * 1e6)
    while not predicate() and GLib.get_monotonic_time() < deadline:
        ctx.iteration(False)
    return predicate()


def test_uninstall_crash_gives_the_window_back(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("pkexec vanished")

    monkeypatch.setattr(flow_mod.uninstall, "uninstall", boom)
    window = FakeWindow()
    flow = flow_mod.UninstallFlow(window, fixer=None, runner=None)
    alerts = []
    flow._alert = lambda heading, *a, **k: alerts.append(heading)

    flow._run("rpm")

    assert run_until(lambda: alerts)
    assert window.sensitive
    assert alerts == [_("The program was not removed")]
