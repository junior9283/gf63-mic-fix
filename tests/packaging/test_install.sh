#!/bin/sh
# Installs the built packages in clean containers and runs the app once in each.
# Usage: [ONLY="arch-pkg ..."] tests/packaging/test_install.sh [DIST_DIR]   (default dist/; needs podman)
# Each check passes when the package installs and `gf63-mic-fix --status` ends with
# 2 (unsupported laptop) or 3 (no PipeWire running) without a Python traceback.
set -u
cd "$(dirname "$0")/../.."
dist=$(cd "${1:-dist}" && pwd)
logs=$(mktemp -d "${TMPDIR:-/tmp}/gf63-install-tests.XXXXXX")

smoke='
gf63-mic-fix --version || exit 10
gf63-mic-fix --status > /tmp/out 2>&1; code=$?
cat /tmp/out
grep -q Traceback /tmp/out && exit 11
[ $code -eq 2 ] || [ $code -eq 3 ] || exit 12'

# A user who had the fix on: removing the package must not leave a dangling enable link.
removal() { # remove-command
    echo "
link=/root/.config/systemd/user/pipewire.service.wants/gf63-mic-fix.service
mkdir -p \$(dirname \$link) && ln -s /usr/lib/systemd/user/gf63-mic-fix.service \$link
$1 >/dev/null 2>&1 || exit 14
test ! -L \$link || exit 15"
}

run() { # name image script; ONLY="name ..." runs just those
    case " ${ONLY:-$1} " in *" $1 "*) ;; *) return 0 ;; esac
    podman run --rm --pull=newer -v "$dist:/dist:ro,Z" "$2" sh -c "$3" >"$logs/$1.log" 2>&1
    echo "$?" >"$logs/$1.code"
}

run fedora-rpm fedora:latest "set -e
dnf install -y -q /dist/*.noarch.rpm
rpm -q --whatprovides /etc/yum.repos.d/gf63-mic-fix.repo
test \"\$(cat /usr/share/gf63-mic-fix/install-type)\" = rpm
set +e; $smoke
$(removal "dnf remove -y gf63-mic-fix")" &
run ubuntu-deb ubuntu:24.04 "set -e; export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq /dist/*.deb >/dev/null
test -f /etc/apt/sources.list.d/gf63-mic-fix.sources
test \"\$(cat /usr/share/gf63-mic-fix/install-type)\" = deb
set +e; $smoke
$(removal "apt-get remove -y gf63-mic-fix")" &
run debian-deb debian:13 "set -e; export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq /dist/*.deb >/dev/null
test \"\$(cat /usr/share/gf63-mic-fix/install-type)\" = deb
set +e; $smoke" &
run arch-pkg archlinux:latest "set -e
pacman -Syu --noconfirm --needed namcap >/dev/null
pacman -U --noconfirm /dist/*.pkg.tar.zst >/dev/null
test \"\$(cat /usr/share/gf63-mic-fix/install-type)\" = arch
echo '--- namcap PKGBUILD'; namcap /dist/PKGBUILD
echo '--- namcap package'; namcap /dist/*.pkg.tar.zst
namcap /dist/PKGBUILD /dist/*.pkg.tar.zst | grep ' E: ' && exit 13
set +e; $smoke
$(removal "pacman -R --noconfirm gf63-mic-fix")" &
run fedora-universal fedora:latest "set -e
dnf install -y -q python3-gobject gtk4 libadwaita pipewire pipewire-utils pulseaudio-utils
mkdir /tmp/x && tar -xzf /dist/gf63-mic-fix-*.tar.gz -C /tmp/x
sh /dist/install.sh --from-dir /tmp/x/gf63-mic-fix-*
test \"\$(cat ~/.local/share/gf63-mic-fix/install-type)\" = universal
export PATH=\$HOME/.local/bin:\$PATH
set +e; $smoke" &
wait

fail=0
for code in "$logs"/*.code; do
    name=$(basename "$code" .code)
    if [ "$(cat "$code")" = 0 ]; then echo "PASS $name"; else
        echo "FAIL $name (exit $(cat "$code")) - last lines:"; tail -15 "$logs/$name.log"; fail=1
    fi
done
echo "logs: $logs"
exit $fail
