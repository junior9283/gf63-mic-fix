"""Applies and undoes the fix. Everything runs as the user; nothing here needs root."""

import re
import time
from collections.abc import Callable
from enum import Enum
from functools import cached_property
from pathlib import Path

from . import APPLY_VOLUME, CONFIG_DIR, GAIN_MAX, GAIN_MIN, SERVICE, VIRTUAL_SOURCE, format_version, state
from .hardware import (
    MIN_PIPEWIRE,
    Hardware,
    detect_hardware,
    find_physical_source,
    find_rnnoise_plugin,
    list_sources,
    pipewire_version,
)
from .i18n import _
from .pwconf import build_conf
from .sysrun import Runner

DIAGNOSIS_OK = "diagnosis-ok"
CONF_FILE = "pipewire.conf"


class Status(Enum):
    FIXED = "fixed"
    FIXED_NOT_DEFAULT = "fixed-not-default"
    NOT_FIXED = "not-fixed"
    UNSUPPORTED = "unsupported"
    NEEDS_DIAGNOSIS = "needs-diagnosis"
    NO_PIPEWIRE = "no-pipewire"
    OLD_PIPEWIRE = "old-pipewire"


class FixError(Exception):
    pass


def blocking_message(st: Status) -> str | None:
    """Why the fix cannot be applied in this state, or None if it can."""
    return {
        Status.UNSUPPORTED: _("This laptop is not an MSI GF63 Thin with a Realtek ALC233 codec."),
        Status.NO_PIPEWIRE: _("PipeWire is not the sound server. This fix needs PipeWire."),
        Status.OLD_PIPEWIRE: _("PipeWire is too old. Version %s or newer is required.")
        % format_version(MIN_PIPEWIRE),
        Status.NEEDS_DIAGNOSIS: _("Run the diagnosis first: this GF63 variant has not been verified yet."),
    }.get(st)


class Fixer:
    def __init__(
        self,
        runner: Runner,
        config_dir: Path = CONFIG_DIR,
        root: Path = Path("/"),
        wait_s: float = 5.0,
        rnnoise_finder: Callable[[], str | None] = find_rnnoise_plugin,
    ):
        self.runner = runner
        self.config_dir = config_dir
        self.root = root
        self.wait_s = wait_s
        self.rnnoise_finder = rnnoise_finder

    @cached_property
    def hardware(self) -> Hardware:
        return detect_hardware(self.root)  # does not change while the app runs

    # --- small pactl/systemctl helpers -------------------------------------------------
    def _pactl(self, *args: str) -> str:
        r = self.runner.run(["pactl", *args])
        if not r.ok:
            raise FixError(_("Sound server command failed: %s") % (r.stderr.strip() or " ".join(args)))
        return r.stdout

    def _systemctl(self, *args: str) -> bool:
        return self.runner.run(["systemctl", "--user", *args]).ok

    def _sources(self) -> list[str]:
        return [s.get("name") for s in list_sources(self.runner)]

    def _default(self) -> str:
        return self._pactl("get-default-source").strip()

    def _volume(self, source: str) -> int:
        m = re.search(r"(\d+)%", self._pactl("get-source-volume", source))
        if not m:
            raise FixError(_("Could not read the microphone volume."))
        return int(m.group(1))

    def _set_volume(self, source: str, percent: int) -> None:
        self._pactl("set-source-volume", source, f"{percent}%")

    def _saved(self) -> state.SavedState:
        return state.load(self.config_dir) or state.SavedState(None, None)

    def _plugin(self, on: bool) -> str | None:
        if not on:
            return None
        plugin = self.rnnoise_finder()
        if not plugin:
            raise FixError(_("The RNNoise noise suppression plugin is not installed."))
        return plugin

    def _start(self, physical: str, plugin: str | None) -> bool:
        """Writes the config and (re)starts the service. True once the virtual source exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        conf = build_conf(physical, plugin, _("Internal microphone (fixed)"))
        (self.config_dir / CONF_FILE).write_text(conf)
        self._systemctl("daemon-reload")
        self._systemctl("enable", SERVICE)
        self._systemctl("restart", SERVICE)
        deadline = time.monotonic() + self.wait_s
        while VIRTUAL_SOURCE not in self._sources():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.25)
        return True

    # --- public API ---------------------------------------------------------------------
    def physical_source(self) -> str:
        card = self.hardware.codec_card
        name = find_physical_source(self.runner, card) if card is not None else None
        if not name:
            raise FixError(_("The internal microphone was not found by the sound server."))
        return name

    def status(self) -> Status:
        hw = self.hardware
        if not hw.supported:
            return Status.UNSUPPORTED
        version = pipewire_version(self.runner)
        if version is None:
            return Status.NO_PIPEWIRE
        if version < MIN_PIPEWIRE:
            return Status.OLD_PIPEWIRE
        if not hw.verified and not (self.config_dir / DIAGNOSIS_OK).exists():
            return Status.NEEDS_DIAGNOSIS
        if not self._systemctl("is-active", "--quiet", SERVICE):
            return Status.NOT_FIXED
        return Status.FIXED if self._default() == VIRTUAL_SOURCE else Status.FIXED_NOT_DEFAULT

    def noise_suppression(self) -> bool:
        return self._saved().noise_suppression

    def apply(self, noise_suppression: bool | None = None) -> None:
        msg = blocking_message(self.status())
        if msg:
            raise FixError(msg)
        physical = self.physical_source()
        saved = state.load(self.config_dir)
        first_time = saved is None
        if first_time:
            # Remember the system as it was, unless it already points at our source.
            default = self._default()
            saved = (
                state.SavedState(default, self._volume(physical))
                if default != VIRTUAL_SOURCE
                else state.SavedState(None, None)
            )
        if noise_suppression is not None:
            saved.noise_suppression = noise_suppression
        elif saved.noise_suppression and not self.rnnoise_finder():
            saved.noise_suppression = False  # its package was removed: fix without it
        plugin = self._plugin(saved.noise_suppression)
        state.save(self.config_dir, saved)
        if not self._start(physical, plugin):
            self.undo()
            raise FixError(_("The fixed microphone did not start. Nothing was changed."))
        self.make_default()
        if first_time:  # applying again keeps the gain chosen with the slider
            self._set_volume(physical, APPLY_VOLUME)

    def set_noise_suppression(self, on: bool) -> None:
        plugin = self._plugin(on)
        saved = self._saved()
        saved.noise_suppression = on
        state.save(self.config_dir, saved)
        if not self._systemctl("is-active", "--quiet", SERVICE):
            return
        physical = self.physical_source()
        if self._start(physical, plugin):
            self.make_default()
            return
        # The new chain did not come up: fall back to the plain fix instead of losing it.
        saved.noise_suppression = False
        state.save(self.config_dir, saved)
        if self._start(physical, None):
            self.make_default()
        else:
            self.undo()
        raise FixError(_("Noise suppression could not start, so it was turned off."))

    def undo(self, purge: bool = False) -> None:
        """Puts the system back as it was. Always stops the service and forgets the saved state."""
        try:
            ours = self._default() == VIRTUAL_SOURCE
            self._systemctl("disable", "--now", SERVICE)
            saved = state.load(self.config_dir) or state.SavedState(None, None)
            restored = saved.default_source in self._sources() if saved.default_source else False
            if restored:
                self._pactl("set-default-source", saved.default_source)
            # The saved input is gone (or was never saved): never leave apps on a removed mic.
            point_at_mic = ours and not restored
            if point_at_mic or saved.physical_volume_percent is not None:
                try:
                    physical = self.physical_source()
                except FixError:
                    physical = None
                if physical and point_at_mic:
                    self._pactl("set-default-source", physical)
                if physical and saved.physical_volume_percent is not None:
                    self._set_volume(physical, saved.physical_volume_percent)
        finally:
            if purge:
                state.clear(self.config_dir)
            else:
                state.discard(self.config_dir)
                (self.config_dir / CONF_FILE).unlink(missing_ok=True)

    def mark_diagnosed(self) -> None:
        """Records that the diagnosis confirmed the known defect on this laptop."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / DIAGNOSIS_OK).write_text("")

    def make_default(self) -> None:
        self._pactl("set-default-source", VIRTUAL_SOURCE)

    def get_gain(self) -> int:
        """Volume of the physical source, in % (100% = +60 dB on this codec)."""
        return self._volume(self.physical_source())

    def set_physical_volume(self, percent: int) -> None:
        """Unclamped; only for restoring a value read with get_gain()."""
        self._set_volume(self.physical_source(), percent)

    def set_gain(self, percent: int) -> None:
        self.set_physical_volume(max(GAIN_MIN, min(GAIN_MAX, percent)))
