"""Development only: renders the window with a pretend status and saves it as PNG.

Used by tests (under GTK's broadway backend) and to make the README screenshots, so the
window never has to appear on anybody's screen.
"""

import sys
import traceback

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")

from gi.repository import GLib, Graphene, Gtk  # noqa: E402

from ..fix import FixError, Status  # noqa: E402
from ..hardware import Hardware  # noqa: E402
from ..sysrun import Result, Runner  # noqa: E402

PREVIEW_LEVEL_DB = -22.0  # what a normal voice shows on the meter
SETTLE_MS = 600  # switches animate when their state is set; wait for them to finish


class PreviewFixer:
    """Answers like a GF63 Thin 10SC in the given status; changes nothing."""

    hardware = Hardware("GF63 Thin 10SC", 0)

    def __init__(self, status: Status):
        self._status = status

    def status(self):
        return self._status

    def get_gain(self):
        return 20

    def noise_suppression(self):
        return False

    def physical_source(self):
        raise FixError("preview: no sound server")  # keeps the level meter off


class NullRunner(Runner):
    def run(self, args, *, input=None, timeout=10):
        return Result(0, "", "")


def save_png(widget: Gtk.Widget, path: str) -> bool:
    """False while the widget has not produced a frame yet."""
    w, h = widget.get_width(), widget.get_height()
    snapshot = Gtk.Snapshot()
    Gtk.WidgetPaintable.new(widget).snapshot(snapshot, w, h)
    node = snapshot.to_node()
    if node is None or not w or not h:
        return False
    rect = Graphene.Rect().init(0, 0, w, h)
    widget.get_native().get_renderer().render_texture(node, rect).save_to_png(path)
    return True


def screenshot(path: str, status_name: str) -> int:
    from .app import run

    outcome = {"ok": False, "tries": 0}

    def ready(window):
        window.on_ready = None
        window.show_level(PREVIEW_LEVEL_DB)

        def capture():
            outcome["tries"] += 1
            try:
                outcome["ok"] = save_png(window, path)
            except Exception:
                traceback.print_exc()
                outcome["tries"] = 99
            if outcome["ok"] or outcome["tries"] >= 20:
                window.get_application().quit()
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(SETTLE_MS, lambda: GLib.timeout_add(250, capture) and False)

    run(fixer=PreviewFixer(Status[status_name]), runner=NullRunner(), on_ready=ready)
    if not outcome["ok"]:
        print("screenshot failed: the window produced no frame", file=sys.stderr)
    return 0 if outcome["ok"] else 1
