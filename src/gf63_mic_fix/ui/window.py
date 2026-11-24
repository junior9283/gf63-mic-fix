"""The single window: status, live level, fix switch, gain, noise suppression, test."""

import tempfile
import threading
import wave
from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk

from .. import APP_ID, GAIN_MAX, GAIN_MIN, VIRTUAL_SOURCE, __version__, diagnose
from ..fix import Fixer, FixError, Status, blocking_message
from ..hardware import find_rnnoise_plugin
from ..i18n import _
from ..install_type import install_type
from ..meter import LevelMeter
from ..sysrun import Runner
from .uninstall import UninstallFlow

TEST_SECONDS = 5.0


def run_in_thread(work, done):
    """Runs work() off the main loop, then done(result, error) back on it."""

    def target():
        try:
            result, error = work(), None
        except Exception as e:  # shown to the user as a toast
            result, error = None, e
        GLib.idle_add(lambda: done(result, error) and False)

    threading.Thread(target=target, daemon=True).start()


ICON_STYLE = {Status.FIXED: "success", Status.FIXED_NOT_DEFAULT: "warning", Status.NEEDS_DIAGNOSIS: "accent"}


def _status_text(st: Status, product: str) -> tuple[str, str, str]:
    """(icon, title, description) for the status page."""
    fixed_name = _("Internal microphone (fixed)")
    return {
        Status.FIXED: (
            "emblem-ok-symbolic",
            _("Microphone fixed"),
            _("Apps now use “%s”.") % fixed_name,
        ),
        Status.FIXED_NOT_DEFAULT: (
            "dialog-warning-symbolic",
            _("Fix active, but not in use"),
            _("Another microphone is the default. Choose “%s” or use the button below.") % fixed_name,
        ),
        Status.NOT_FIXED: (
            "audio-input-microphone-symbolic",
            _("Microphone not fixed"),
            _("Turn on the fix below to remove the noise."),
        ),
        Status.NEEDS_DIAGNOSIS: (
            "system-search-symbolic",
            _("Diagnosis needed"),
            _("This GF63 variant has not been verified yet. A short beep confirms the defect first."),
        ),
    }.get(st) or ("action-unavailable-symbolic", _("Fix unavailable"), blocking_message(st) or product)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, fixer: Fixer, runner: Runner, on_ready=None):
        super().__init__(application=app, title="GF63 Mic Fix", default_width=460, default_height=640)
        self.fixer, self.runner, self.on_ready = fixer, runner, on_ready
        self.status = None
        self._syncing = False  # True while widgets are updated from code
        self._gain_timer = 0
        self.meter = None
        self._build()
        self.connect("map", lambda *_: self.refresh())
        self.connect("unmap", lambda *_: self._stop_meter())

    # --- layout -------------------------------------------------------------------------
    def _build(self):
        menu = Gio.Menu()
        for label, name, callback in (
            (_("Diagnosis"), "diagnose", self.ask_diagnosis),
            (_("About GF63 Mic Fix"), "about", self.show_about),
            (_("Uninstall…"), "uninstall", self.ask_uninstall),
        ):
            menu.append(label, f"win.{name}")
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_a, cb=callback: cb())
            self.add_action(action)

        header = Adw.HeaderBar()
        header.pack_end(
            Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text=_("Menu"))
        )

        # A plain header instead of Adw.StatusPage, whose inner scrolling clips the text in a box.
        self.icon = Gtk.Image(pixel_size=72, margin_top=12)
        self.title = Gtk.Label(css_classes=["title-1"], wrap=True, justify=Gtk.Justification.CENTER)
        self.description = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, max_width_chars=44)
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for w in (self.icon, self.title, self.description):
            self.page.append(w)
        self.product = Gtk.Label(css_classes=["dim-label", "caption"])

        self.level = Gtk.LevelBar(min_value=0, max_value=1, hexpand=True, valign=Gtk.Align.CENTER)
        self.level.set_size_request(160, -1)
        level_row = Adw.ActionRow(title=_("Level"))
        level_row.add_suffix(self.level)

        self.fix_row = Adw.SwitchRow(
            title=_("Fix active"), subtitle=_("Use only the working channel, without hum")
        )
        self.fix_row.connect("notify::active", self._on_fix_toggled)

        self.gain = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, GAIN_MIN, GAIN_MAX, 1)
        self.gain.set_hexpand(True)
        self.gain.set_draw_value(False)
        self.gain.set_size_request(180, -1)
        self.gain.connect("value-changed", self._on_gain_changed)
        self.gain_row = Adw.ActionRow(
            title=_("Microphone gain"), subtitle=_("Raise it if your voice is too low")
        )
        self.gain_row.add_suffix(self.gain)

        self.noise_row = Adw.SwitchRow(title=_("Noise suppression (RNNoise)"))
        self.noise_row.connect("notify::active", self._on_noise_toggled)

        group = Adw.PreferencesGroup()
        for row in (level_row, self.fix_row, self.gain_row, self.noise_row):
            group.add(row)
        self.controls = group

        self.default_button = self._pill(
            _("Use as default microphone"), self._on_make_default, suggested=True
        )
        self.diag_button = self._pill(_("Run diagnosis"), lambda *_: self.ask_diagnosis(), suggested=True)
        self.test_button = self._pill(_("Test microphone"), self._on_test)

        kind = install_type()
        updates = {
            "rpm": _("updated by the system"),
            "deb": _("updated by the system"),
            "arch": _("weekly update check"),
            "universal": _("automatic weekly updates"),
        }.get(kind, _("development copy"))
        footer = Gtk.Label(label=f"v{__version__} · {updates}", css_classes=["dim-label", "caption"])

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=6, margin_bottom=18)
        box.set_margin_start(12)
        box.set_margin_end(12)
        for w in (
            self.page,
            self.product,
            group,
            self.default_button,
            self.diag_button,
            self.test_button,
            footer,
        ):
            box.append(w)
        clamp = Adw.Clamp(maximum_size=520, child=box)

        self.toasts = Adw.ToastOverlay(child=Gtk.ScrolledWindow(child=clamp, vexpand=True))
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(header)
        self.set_content(view)

    def _pill(self, label, callback, suggested=False):
        b = Gtk.Button(label=label, halign=Gtk.Align.CENTER, css_classes=["pill"])
        if suggested:
            b.add_css_class("suggested-action")
        b.connect("clicked", callback)
        return b

    # --- state --------------------------------------------------------------------------
    def toast(self, text: str):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=5))

    def _busy(self, busy: bool):
        for w in (self.controls, self.default_button, self.diag_button, self.test_button):
            w.set_sensitive(not busy)

    def refresh(self):
        def work():
            st = self.fixer.status()
            gain = None
            if st in (Status.FIXED, Status.FIXED_NOT_DEFAULT, Status.NOT_FIXED):
                gain = self.fixer.get_gain()
            return st, gain, self.fixer.noise_suppression()

        run_in_thread(work, self._apply_state)

    def _apply_state(self, result, error):
        if error:
            self.toast(str(error))
            return
        st, gain, noise = result
        self.status = st
        icon, title, desc = _status_text(st, self.fixer.hardware.product)
        self.icon.set_from_icon_name(icon)
        self.icon.set_css_classes([ICON_STYLE.get(st, "dim-label")])
        self.title.set_label(title)
        self.description.set_label(desc)
        hw = self.fixer.hardware
        self.product.set_label(
            f"{hw.product or _('Unknown laptop')} · Realtek ALC233" if hw.supported else ""
        )

        usable = st in (Status.FIXED, Status.FIXED_NOT_DEFAULT, Status.NOT_FIXED)
        fixed = st in (Status.FIXED, Status.FIXED_NOT_DEFAULT)
        self._syncing = True
        self.controls.set_visible(usable)
        self.fix_row.set_active(fixed)
        if gain is not None:
            self.gain.set_value(max(GAIN_MIN, min(GAIN_MAX, gain)))
        plugin = find_rnnoise_plugin()
        self.noise_row.set_sensitive(bool(plugin))
        self.noise_row.set_subtitle(
            _("Removes fan and keyboard noise")
            if plugin
            else _("Install the package noise-suppression-for-voice")
        )
        self.noise_row.set_active(noise and bool(plugin))
        self._syncing = False
        self.default_button.set_visible(st is Status.FIXED_NOT_DEFAULT)
        self.diag_button.set_visible(st is Status.NEEDS_DIAGNOSIS)
        self.test_button.set_visible(usable)
        self._busy(False)
        self._restart_meter(VIRTUAL_SOURCE if fixed else None)
        if self.on_ready:
            self.on_ready(self)

    # --- meter --------------------------------------------------------------------------
    def _restart_meter(self, source):
        self._stop_meter()
        if self.status not in (Status.FIXED, Status.FIXED_NOT_DEFAULT, Status.NOT_FIXED):
            return
        try:
            source = source or self.fixer.physical_source()
        except FixError:
            return
        self.meter = LevelMeter(self.runner, source, self.show_level)
        self.meter.start()

    def _stop_meter(self):
        if self.meter:
            self.meter.stop()
            self.meter = None

    def show_level(self, db: float):
        self.level.set_value(max(0.0, min(1.0, (db + 60) / 60)))  # -60..0 dBFS

    # --- actions ------------------------------------------------------------------------
    def _act(self, work, success_message=None):
        self._busy(True)

        def done(_result, error):
            if error:
                self.toast(str(error))
            elif success_message:
                self.toast(success_message)
            self.refresh()

        run_in_thread(work, done)

    def _on_fix_toggled(self, row, _pspec):
        if self._syncing:
            return
        if row.get_active():
            self._act(self.fixer.apply, _("Microphone fixed"))
        else:
            self._act(self.fixer.undo, _("Fix turned off; previous settings restored"))

    def _on_gain_changed(self, scale):
        if self._syncing:
            return
        if self._gain_timer:
            GLib.source_remove(self._gain_timer)

        def commit():
            self._gain_timer = 0
            value = int(scale.get_value())
            run_in_thread(lambda: self.fixer.set_gain(value), lambda r, e: e and self.toast(str(e)))
            return False

        self._gain_timer = GLib.timeout_add(200, commit)

    def _on_noise_toggled(self, row, _pspec):
        if not self._syncing:
            on = row.get_active()
            self._act(lambda: self.fixer.set_noise_suppression(on))

    def _on_make_default(self, *_):
        self._act(self.fixer.make_default)

    def _on_test(self, *_):
        self._busy(True)
        self.test_button.set_label(_("Recording… speak now"))
        source = VIRTUAL_SOURCE if self.status in (Status.FIXED, Status.FIXED_NOT_DEFAULT) else None

        def work():
            pcm = diagnose.record(self.runner, source or self.fixer.physical_source(), TEST_SECONDS)
            with tempfile.TemporaryDirectory() as tmp:
                wav = Path(tmp) / "test.wav"
                with wave.open(str(wav), "wb") as w:
                    w.setnchannels(2)
                    w.setsampwidth(2)
                    w.setframerate(diagnose.RATE)
                    w.writeframes(pcm)
                GLib.idle_add(lambda: self.test_button.set_label(_("Playing back…")) and False)
                self.runner.run(["pw-play", str(wav)], timeout=TEST_SECONDS + 5)

        def done(_r, error):
            self.test_button.set_label(_("Test microphone"))
            if error:
                self.toast(str(error))
            self._busy(False)

        run_in_thread(work, done)

    def ask_diagnosis(self, *_):
        dialog = Adw.AlertDialog(
            heading=_("Run the diagnosis?"),
            body=_("Unplug headphones and turn the volume up. A beep will play for about 2 seconds."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("run", _("Run"))
        dialog.set_response_appearance("run", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", lambda d, r: r == "run" and self._run_diagnosis())
        dialog.present(self)

    def _run_diagnosis(self):
        self._busy(True)
        messages = {
            diagnose.Verdict.DEFECT_CONFIRMED: _("Defect confirmed. You can turn on the fix now."),
            diagnose.Verdict.NO_DEFECT: _("This laptop does not have the known defect. Nothing was changed."),
            diagnose.Verdict.INCONCLUSIVE: _(
                "The beep was not heard. Unplug headphones, turn the volume up and try again."
            ),
        }

        def done(verdict, error):
            if error:
                self.toast(str(error))
            else:
                alert = Adw.AlertDialog(heading=_("Diagnosis"), body=messages[verdict])
                alert.add_response("ok", _("OK"))
                alert.present(self)
            self.refresh()

        run_in_thread(lambda: diagnose.run_diagnosis(self.fixer, self.runner), done)

    def show_about(self, *_):
        about = Adw.AboutDialog(
            application_name="GF63 Mic Fix",
            application_icon=APP_ID,
            version=__version__,
            developer_name="junior9283",
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/junior9283/gf63-mic-fix",
            issue_url="https://github.com/junior9283/gf63-mic-fix/issues",
            comments=_("Fixes the noisy internal microphone of MSI GF63 Thin laptops on Linux."),
        )
        about.present(self)

    def ask_uninstall(self, *_):
        UninstallFlow(self, self.fixer, self.runner).start()
