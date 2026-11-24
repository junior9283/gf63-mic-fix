import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio  # noqa: E402

from .. import APP_ID, UPDATE_TIMER  # noqa: E402
from ..fix import Fixer  # noqa: E402
from ..install_type import install_type  # noqa: E402
from ..sysrun import Runner  # noqa: E402
from .window import MainWindow  # noqa: E402


class App(Adw.Application):
    def __init__(self, fixer: Fixer, runner: Runner, uninstall: bool = False, on_ready=None):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.fixer, self.runner = fixer, runner
        self.start_with_uninstall = uninstall
        self.on_ready = on_ready  # used by --screenshot

    def do_activate(self):
        win = self.props.active_window or MainWindow(self, self.fixer, self.runner, self.on_ready)
        win.present()
        if self.start_with_uninstall:
            win.ask_uninstall()
        if install_type() in ("arch", "universal"):
            cmd = ["systemctl", "--user", "enable", "--now", UPDATE_TIMER]
            threading.Thread(target=self.runner.run, args=(cmd,), daemon=True).start()


def run(
    uninstall: bool = False, fixer: Fixer | None = None, runner: Runner | None = None, on_ready=None
) -> int:
    runner = runner or Runner()
    app = App(fixer or Fixer(runner), runner, uninstall, on_ready)
    return app.run([])
