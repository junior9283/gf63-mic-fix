"""Run slow work off the GTK main loop and hand the result back to it."""

import threading

from gi.repository import GLib


def on_main(fn, *args) -> None:
    """Calls fn(*args) once on the main loop, whatever fn returns."""

    def once():
        fn(*args)
        return GLib.SOURCE_REMOVE

    GLib.idle_add(once)


def run_in_thread(work, done=None) -> None:
    """Runs work() in a thread, then done(result, error) on the main loop."""

    def target():
        try:
            result, error = work(), None
        except Exception as e:  # shown to the user by `done`
            result, error = None, e
        if done:
            on_main(done, result, error)

    threading.Thread(target=target, daemon=True).start()
