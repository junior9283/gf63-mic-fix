"""gettext setup. Source strings are English; translations live in <app dir>/locale."""

import gettext
from pathlib import Path

DOMAIN = "gf63-mic-fix"
LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"


def _load() -> gettext.NullTranslations:
    return gettext.translation(DOMAIN, LOCALE_DIR, fallback=True)


_translation = _load()


def _(s: str) -> str:
    return _translation.gettext(s)


def reload() -> None:
    """Re-reads the catalogue (used by tests after changing LANGUAGE)."""
    global _translation
    _translation = _load()
