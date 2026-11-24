"""Draws the README images (banner, how-it-works diagram, before/after chart) as SVG + PNG.

Usage: python3 scripts/readme_images.py      -> docs/assets/*.svg, *.png (light and dark)
The measurements live in MEASURED below; update them when the fix is measured again.
"""

import sys
from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/assets"
FONT = "Cantarell, 'Noto Sans', 'DejaVu Sans', sans-serif"

# GF63 Thin 10SC, 24/11/2026, RMS over 2 s: raw stereo input at 100% vs. GF63 Mic Fix.
MEASURED = {
    "noise": {"before": -4.2, "after": -29.4},  # level in silence, dBFS (lower is better)
    "tone": {"before": -0.8, "after": 14.5},  # 1 kHz test tone above the noise, dB (higher is better)
}

THEMES = {
    "light": {
        "surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
        "grid": "#e1e0d9", "axis": "#c3c2b7", "before": "#eb6834", "after": "#2a78d6",
        "box": "#ffffff", "accent": "#6a3fd0", "off": "#b5b3ad",
    },
    "dark": {
        "surface": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#898781",
        "grid": "#2c2c2a", "axis": "#383835", "before": "#d95926", "after": "#3987e5",
        "box": "#242423", "accent": "#a58cf0", "off": "#5d5c58",
    },
}  # fmt: skip


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg(width: int, height: int, body: str, background: str | None = None) -> str:
    bg = f'<rect width="{width}" height="{height}" fill="{background}"/>' if background else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT}">{bg}{body}</svg>\n'
    )


def text(x, y, s, size=16, fill="#000", weight=400, anchor="start") -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
        f'text-anchor="{anchor}">{esc(s)}</text>'
    )


def hline(x1, y1, x2, y2, color) -> str:
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1"/>'


# --- banner -------------------------------------------------------------------------------
def banner() -> str:
    icon = (ROOT / "data/io.github.junior9283.Gf63MicFix.svg").read_text()
    inner = icon[icon.index(">", icon.index("<svg")) + 1 : icon.rindex("</svg>")]
    body = (
        '<defs><linearGradient id="b" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#2b1260"/><stop offset="1" stop-color="#5b2bc4"/>'
        "</linearGradient></defs>"
        '<rect width="1280" height="320" rx="24" fill="url(#b)"/>'
        f'<g transform="translate(96 64) scale(1.5)">{inner}</g>'
        + text(352, 150, "GF63 Mic Fix", 72, "#ffffff", 700)
        + text(354, 204, "Fix the noisy internal mic of MSI GF63 Thin on Linux", 30, "#e6dcff")
        + text(354, 248, "PipeWire · rpm · deb · Arch · any distro", 22, "#c7b5f5")
    )
    return svg(1280, 320, body)


# --- how it works -------------------------------------------------------------------------
def diagram(t: dict) -> str:
    def box(x, y, w, h, title, sub, dashed=False, strong=False):
        stroke = t["accent"] if strong else t["axis"]
        dash = ' stroke-dasharray="7 6"' if dashed else ""
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{t["box"]}" '
            f'stroke="{stroke}" stroke-width="2"{dash}/>'
            + text(x + w / 2, y + h / 2 - 4, title, 19, t["ink"], 700, "middle")
            + text(x + w / 2, y + h / 2 + 22, sub, 15, t["ink2"], 400, "middle")
        )

    def arrow(x1, y1, x2, y2, color):
        return (
            f'<line x1="{x1}" y1="{y1}" x2="{x2 - 10}" y2="{y2}" stroke="{color}" stroke-width="2"/>'
            f'<path d="M{x2 - 12} {y2 - 7} L{x2} {y2} L{x2 - 12} {y2 + 7} Z" fill="{color}"/>'
        )

    y, h = 120, 96
    body = (
        text(40, 52, "How it works", 26, t["ink"], 700)
        + text(
            40,
            82,
            "A virtual microphone in PipeWire; the hardware and other apps are untouched.",
            16,
            t["ink2"],
        )
        # physical source with its two channels
        + f'<rect x="40" y="{y - 10}" width="230" height="{h + 20}" rx="14" fill="{t["box"]}" '
        f'stroke="{t["axis"]}" stroke-width="2"/>'
        + text(155, y + 16, "Built-in mic (stereo)", 17, t["ink"], 700, "middle")
        + text(64, y + 52, "L", 17, t["ink"], 700)
        + text(88, y + 52, "hiss only", 15, t["ink2"])
        + text(64, y + 84, "R", 17, t["ink"], 700)
        + text(88, y + 84, "your voice", 15, t["ink2"])
        # L is dropped
        + f'<line x1="270" y1="{y + 47}" x2="318" y2="{y + 47}" stroke="{t["off"]}" stroke-width="2" '
        'stroke-dasharray="4 4"/>'
        + f'<path d="M322 {y + 39} l16 16 M338 {y + 39} l-16 16" stroke="{t["off"]}" stroke-width="3"/>'
        + arrow(270, y + 79, 370, y + 79, t["accent"])
        + box(370, y, 190, h, "Right channel", "mono, no hiss")
        + arrow(560, y + h / 2, 610, y + h / 2, t["accent"])
        + box(610, y, 190, h, "High-pass", "120 Hz, removes hum")
        + arrow(800, y + h / 2, 850, y + h / 2, t["accent"])
        + box(850, y, 150, h, "RNNoise", "optional", dashed=True)
        + arrow(1000, y + h / 2, 1050, y + h / 2, t["accent"])
        + box(1050, y, 210, h, "Internal mic (fixed)", "what apps use", strong=True)
        + text(
            40,
            290,
            "Gain: the physical input is set to 20% (+18 dB) instead of up to +60 dB, so it no longer clips.",
            16,
            t["ink2"],
        )  # fmt: skip
    )
    return svg(1300, 320, body, t["surface"])


# --- before / after -----------------------------------------------------------------------
def chart(t: dict) -> str:
    def panel(x0, title, note, unit, lo, hi, step, values):
        w, axis_y = 520, 230
        scale = lambda v: x0 + (v - lo) / (hi - lo) * w  # noqa: E731
        parts = [text(x0, 120, title, 20, t["ink"], 700), text(x0, 146, note, 15, t["ink2"])]
        v = lo
        while v <= hi:
            x = scale(v)
            parts.append(hline(x, 170, x, axis_y, t["grid"]))
            parts.append(text(x, axis_y + 24, f"{v:g}", 14, t["muted"], 400, "middle"))
            v += step
        parts.append(hline(x0, axis_y, x0 + w, axis_y, t["axis"]))
        parts.append(text(x0 + w, axis_y + 48, unit, 14, t["muted"], 400, "end"))
        b, a = scale(values["before"]), scale(values["after"])
        direction = 1 if a > b else -1
        parts.append(
            f'<line x1="{b + 12 * direction}" y1="200" x2="{a - 14 * direction}" y2="200" '
            f'stroke="{t["muted"]}" stroke-width="2"/>'
            f'<path d="M{a - 22 * direction} 193 L{a - 11 * direction} 200 L{a - 22 * direction} 207 Z" '
            f'fill="{t["muted"]}"/>'
        )
        for key, x in (("before", b), ("after", a)):
            ring = f'stroke="{t["surface"]}" stroke-width="2"'
            parts.append(f'<circle cx="{x}" cy="200" r="9" fill="{t[key]}" {ring}/>')
            parts.append(text(x, 182, f"{values[key]:+g}", 16, t["ink"], 700, "middle"))
        return "".join(parts)

    legend = (
        f'<circle cx="48" cy="64" r="7" fill="{t["before"]}"/>'
        + text(62, 70, "Before: input at 100%", 16, t["ink2"])
        + f'<circle cx="290" cy="64" r="7" fill="{t["after"]}"/>'
        + text(304, 70, "After: GF63 Mic Fix", 16, t["ink2"])
    )
    body = (
        text(40, 36, "Measured on a GF63 Thin 10SC", 22, t["ink"], 700)
        + legend
        + panel(40, "Hiss in silence", "lower is better", "dBFS", -40, 0, 5, MEASURED["noise"])
        + panel(660, "Test tone above the noise", "higher is better", "dB", -5, 20, 5, MEASURED["tone"])
    )
    return svg(1220, 300, body, t["surface"])


def write(name: str, content: str, width: int) -> None:
    path = OUT / f"{name}.svg"
    path.write_text(content)
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(path), width, -1)
    pixbuf.savev(str(OUT / f"{name}.png"), "png", [], [])
    print(OUT / f"{name}.png")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    write("banner", banner(), 1280)
    for mode, theme in THEMES.items():
        suffix = "" if mode == "light" else "-dark"
        write(f"how-it-works{suffix}", diagram(theme), 1300)
        write(f"before-after{suffix}", chart(theme), 1220)
    return 0


if __name__ == "__main__":
    sys.exit(main())
