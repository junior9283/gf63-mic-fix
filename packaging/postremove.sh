#!/bin/sh
# After the package is removed (not upgraded): delete the per-user links that systemd left
# pointing at the removed units, so `systemctl --user` stops warning about them.
# Arguments: rpm "0" = erase, "1" = upgrade; deb "remove"/"purge" vs "upgrade"/...; Arch: none.
case ${1:-} in
1 | 2 | upgrade | failed-upgrade | abort-*) exit 0 ;;
esac
root=${GF63_ROOT:-}
for link in "$root"/home/*/.config/systemd/user/*.wants/gf63-mic-fix*.service \
    "$root"/home/*/.config/systemd/user/*.wants/gf63-mic-fix*.timer \
    "$root"/root/.config/systemd/user/*.wants/gf63-mic-fix*; do
    # Only links whose target no longer exists; never follow or touch anything else.
    if [ -L "$link" ] && [ ! -e "$link" ]; then
        rm -f -- "$link"
    fi
done
exit 0
