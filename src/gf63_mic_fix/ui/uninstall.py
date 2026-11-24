"""Uninstall dialogs: confirm, undo the fix, remove the program, say goodbye."""

import threading

from gi.repository import Adw, GLib

from .. import uninstall
from ..i18n import _
from ..install_type import install_type


class UninstallFlow:
    def __init__(self, window, fixer, runner):
        self.window, self.fixer, self.runner = window, fixer, runner

    def _alert(self, heading, body, responses, on_response=None, destructive=None):
        dialog = Adw.AlertDialog(heading=heading, body=body)
        for rid, label in responses:
            dialog.add_response(rid, label)
        if destructive:
            dialog.set_response_appearance(destructive, Adw.ResponseAppearance.DESTRUCTIVE)
        if on_response:
            dialog.connect("response", lambda d, r: on_response(r))
        dialog.present(self.window)

    def start(self):
        kind = install_type()
        if kind == "source":
            self._alert(
                _("Nothing to uninstall"),
                _("This copy runs from the source code. Use “Fix active” to undo the fix."),
                [("ok", _("OK"))],
            )
            return
        password = _("Your password will be asked to remove the program.") if kind != "universal" else ""
        self._alert(
            _("Uninstall GF63 Mic Fix?"),
            _("The microphone goes back to how it was before the fix, and the program is removed.")
            + (" " + password if password else ""),
            [("cancel", _("Cancel")), ("uninstall", _("Uninstall"))],
            lambda r: r == "uninstall" and self._run(kind),
            destructive="uninstall",
        )

    def _run(self, kind):
        self.window.set_sensitive(False)

        def work():
            ok = uninstall.uninstall(kind, self.fixer, self.runner)
            GLib.idle_add(lambda: self._finished(ok) and False)

        threading.Thread(target=work, daemon=True).start()

    def _finished(self, ok):
        self.window.set_sensitive(True)
        if ok:
            self._alert(
                _("GF63 Mic Fix was removed"),
                _("The microphone settings were restored. Thank you for using it."),
                [("close", _("Close"))],
                lambda r: self.window.get_application().quit(),
            )
        else:
            self._alert(
                _("The program was not removed"),
                _("The fix was turned off, but removing the program was cancelled or failed."),
                [("ok", _("OK"))],
                lambda r: self.window.refresh(),
            )
