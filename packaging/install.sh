#!/bin/sh
# GF63 Mic Fix - universal installer for any Linux distribution. No root needed.
#
#   curl -fsSL https://github.com/junior9283/gf63-mic-fix/releases/latest/download/install.sh | sh
#
# Downloads the latest release, checks its signature (when gpg is present) and installs it for
# the current user under ~/.local. Running it again updates or repairs the installation.
# Remove it from the app menu: "Uninstall GF63 Mic Fix".
set -eu

REPO=junior9283/gf63-mic-fix
FINGERPRINT=5972B2DCEFAF53DC842CC3EA20072D0D235CAC26
ID=io.github.junior9283.Gf63MicFix

say() { printf '%s\n' "$*"; }
die() { printf 'gf63-mic-fix: %s\n' "$*" >&2; exit 1; }
usage() {
    cat <<'EOF'
Installs GF63 Mic Fix for the current user (no root needed).
  install.sh                  download, verify and install the latest release
  install.sh --from-dir DIR   install an already extracted release (used by the updater)
EOF
}

from_dir=
while [ $# -gt 0 ]; do
    case $1 in
    --from-dir) from_dir=${2:?--from-dir needs a directory}; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
    esac
done

# --- dependencies -------------------------------------------------------------------------
missing=
python3 -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null || missing="$missing python"
python3 - 2>/dev/null <<'EOF' || missing="$missing gtk"
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw
assert (Adw.MAJOR_VERSION, Adw.MINOR_VERSION) >= (1, 5)
EOF
command -v pipewire >/dev/null || missing="$missing pipewire"
command -v pw-record >/dev/null || missing="$missing pw-tools"
command -v pactl >/dev/null || missing="$missing pactl"

if [ -n "$missing" ]; then
    say "Some programs are missing:$missing"
    say "Install them, then run this installer again:"
    if command -v dnf >/dev/null; then
        say "  sudo dnf install python3-gobject gtk4 libadwaita pipewire-utils pulseaudio-utils"
    elif command -v apt-get >/dev/null; then
        say "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 pipewire-bin pulseaudio-utils"
    elif command -v pacman >/dev/null; then
        say "  sudo pacman -S python-gobject gtk4 libadwaita pipewire libpulse"
    elif command -v zypper >/dev/null; then
        say "  sudo zypper install python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 pipewire-tools pulseaudio-utils"
    else
        say "  Python 3.11+, PyGObject, GTK 4, libadwaita 1.5+, PipeWire tools (pw-record) and pactl"
    fi
    exit 1
fi

# --- download -----------------------------------------------------------------------------
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fetch() { # url file
    python3 -I -c 'import sys, urllib.request
req = urllib.request.Request(sys.argv[1], headers={"User-Agent": "gf63-mic-fix-installer"})
with urllib.request.urlopen(req, timeout=60) as r, open(sys.argv[2], "wb") as f:
    f.write(r.read())' "$1" "$2"
}

if [ -z "$from_dir" ]; then
    fetch "${GF63_API_URL:-https://api.github.com/repos/$REPO/releases/latest}" "$work/release.json" ||
        die "could not reach GitHub"
    version=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["tag_name"].lstrip("v"))' \
        "$work/release.json" 2>/dev/null) || die "unexpected release data from GitHub; try again later"
    case $version in *[!0-9.]* | "") die "unexpected release version: $version" ;; esac
    name=gf63-mic-fix-$version.tar.gz
    base=https://github.com/$REPO/releases/download/v$version
    say "Downloading GF63 Mic Fix $version..."
    fetch "$base/$name" "$work/$name" || die "download failed: $name"
    if command -v gpg >/dev/null; then
        fetch "$base/$name.asc" "$work/$name.asc" || die "download failed: $name.asc"
        mkdir -m 700 "$work/gnupg"
        cat >"$work/key.asc" <<'EOF'
-----BEGIN PGP PUBLIC KEY BLOCK-----

mDMEawXGoBYJKwYBBAHaRw8BAQdAcHV0PPf4Qep8g6e96IsCEKLPiE7Z4aCmXkAr
hIIw4Ke0GEdGNjMgTWljIEZpeCBTaWduaW5nIEtleYiTBBMWCgA7FiEEWXKy3O+v
U9yELMPqIActDSNcrCYFAmsFxqACGwMFCwkIBwICIgIGFQoJCAsCBBYCAwECHgcC
F4AACgkQIActDSNcrCZRUAEA25CRGgVhOnr/wFd5XKOVbNDB2n9FK4MLF6SLJ1hi
PKUA/Ruk5U4P3rAuCvSoDzvaGM93cGme8J7cFbc0hgnEY90C
=eKdN
-----END PGP PUBLIC KEY BLOCK-----
EOF
        gpg --batch --no-tty --homedir "$work/gnupg" --import "$work/key.asc" 2>/dev/null
        gpg --batch --no-tty --homedir "$work/gnupg" --status-fd 1 --verify "$work/$name.asc" "$work/$name" \
            2>/dev/null | grep -q "^\[GNUPG:\] VALIDSIG $FINGERPRINT " ||
            die "the download is not signed by the GF63 Mic Fix key; nothing was installed"
    else
        say "gpg not found: skipping the signature check (the download still came over HTTPS)."
    fi
    tar -xzf "$work/$name" -C "$work"
    from_dir=$work/gf63-mic-fix-$version
fi

[ -f "$from_dir/app/gf63_mic_fix/__init__.py" ] || die "$from_dir is not a GF63 Mic Fix release"

# --- install ------------------------------------------------------------------------------
share=$HOME/.local/share
bin=$HOME/.local/bin
units=$HOME/.config/systemd/user
mkdir -p "$share" "$bin" "$share/applications" "$share/icons/hicolor/scalable/apps" "$units"

# Program files: copied next to the old ones, then swapped in, so a failure never leaves a
# half-installed program behind.
rm -rf "$share/gf63-mic-fix.new" "$share/gf63-mic-fix.old"
cp -R "$from_dir/app" "$share/gf63-mic-fix.new"
echo universal >"$share/gf63-mic-fix.new/install-type"
[ -d "$share/gf63-mic-fix" ] && mv "$share/gf63-mic-fix" "$share/gf63-mic-fix.old"
mv "$share/gf63-mic-fix.new" "$share/gf63-mic-fix"
rm -rf "$share/gf63-mic-fix.old"

put() { # mode src dst [sed-expression]: write through a temporary file, then rename
    sed "${4:-}" "$2" >"$3.tmp" && chmod "$1" "$3.tmp" && mv "$3.tmp" "$3"
}
data=$from_dir/data
put 755 "$from_dir/bin/gf63-mic-fix" "$bin/gf63-mic-fix"
for f in "$ID.desktop" "$ID.Uninstall.desktop"; do
    put 644 "$data/$f" "$share/applications/$f" "s|^Exec=gf63-mic-fix|Exec=$bin/gf63-mic-fix|"
done
put 644 "$data/$ID.svg" "$share/icons/hicolor/scalable/apps/$ID.svg"
put 644 "$data/gf63-mic-fix.service" "$units/gf63-mic-fix.service"
put 644 "$data/gf63-mic-fix-update.service" "$units/gf63-mic-fix-update.service" \
    "s|^ExecStart=/usr/bin/gf63-mic-fix|ExecStart=$bin/gf63-mic-fix|"
put 644 "$data/gf63-mic-fix-update.timer" "$units/gf63-mic-fix-update.timer"

systemctl --user daemon-reload 2>/dev/null || true
systemctl --user enable --now gf63-mic-fix-update.timer >/dev/null 2>&1 || true

say "GF63 Mic Fix is installed. Open it from the app menu, or run: $bin/gf63-mic-fix"
