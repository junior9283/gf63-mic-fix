"""Entry point. Without options it opens the window; the options exist for the
packaging scripts, the update timer and the tests."""

import argparse
import sys

from . import __version__
from .fix import Fixer, FixError, Status
from .sysrun import Runner

EXIT_CODES = {
    Status.FIXED: 0,
    Status.NOT_FIXED: 1,
    Status.FIXED_NOT_DEFAULT: 1,
    Status.UNSUPPORTED: 2,
    Status.NEEDS_DIAGNOSIS: 2,
    Status.NO_PIPEWIRE: 3,
    Status.OLD_PIPEWIRE: 3,
}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gf63-mic-fix", description="GF63 Mic Fix")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--status", action="store_true", help="print the fix status")
    g.add_argument("--apply", action="store_true", help="apply the fix")
    g.add_argument("--undo", action="store_true", help="undo the fix")
    g.add_argument("--check-update", action="store_true", help="check for a new version (timer)")
    g.add_argument("--version", action="store_true", help="print the version")
    return p


def main(argv: list[str] | None = None, fixer: Fixer | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if args.check_update:
        from .updater import run_scheduled  # only the timer needs the network code

        run_scheduled()
        return 0
    if not (args.status or args.apply or args.undo):
        from .ui.app import run  # GTK is only imported for the window

        return run()
    fixer = fixer or Fixer(Runner())
    if args.status:
        st = fixer.status()
        print(st.name)
        return EXIT_CODES[st]
    try:
        fixer.apply() if args.apply else fixer.undo()
    except FixError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
