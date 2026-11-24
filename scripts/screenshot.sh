#!/bin/sh
# Renders README screenshots off-screen with GTK's broadway backend (no window, no browser).
# Usage: scripts/screenshot.sh [STATUS]   (default FIXED) -> docs/assets/screenshot-*.png
set -eu
cd "$(dirname "$0")/.."
status=${1:-FIXED}
mo=src/locale/pt_BR/LC_MESSAGES  # where i18n looks when running from source
mkdir -p "$mo" docs/assets
msgfmt -o "$mo/gf63-mic-fix.mo" po/pt_BR.po
runtime=$(mktemp -d)
chmod 700 "$runtime"
# Broadway has no viewer, so its frame clock does not advance: turn animations off or
# switches are captured halfway through their color transition.
mkdir -p "$runtime/config/gtk-4.0"
printf '[Settings]\ngtk-enable-animations=false\n' > "$runtime/config/gtk-4.0/settings.ini"
XDG_RUNTIME_DIR=$runtime gtk4-broadwayd :19 >/dev/null 2>&1 &
broadway=$!
# Show the footer of a packaged install (the most common case), not "development copy".
echo rpm >src/install-type
trap 'kill $broadway 2>/dev/null; rm -rf "$runtime" src/install-type' EXIT
sleep 0.5
shot() { # lang scheme output
    XDG_RUNTIME_DIR=$runtime XDG_CONFIG_HOME=$runtime/config GDK_BACKEND=broadway BROADWAY_DISPLAY=:19 GSK_RENDERER=cairo \
        LANGUAGE=$1 ADW_DEBUG_COLOR_SCHEME=prefer-$2 GF63_MIC_FIX_APPDIR=$PWD/src \
        bin/gf63-mic-fix --screenshot "$3" --fake-status "$status" 2>/dev/null
    echo "$3"
}
shot en light docs/assets/screenshot-en.png
shot en dark docs/assets/screenshot-en-dark.png
shot pt_BR light docs/assets/screenshot-pt-BR.png
shot pt_BR dark docs/assets/screenshot-pt-BR-dark.png
