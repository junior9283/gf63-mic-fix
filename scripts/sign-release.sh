#!/bin/sh
# Signs release artifacts with the project key (already imported in $GNUPGHOME or the default
# keyring): the rpm itself, a detached .asc for every file and a signed SHA256SUMS.
# Usage: scripts/sign-release.sh DIST_DIR
set -eu
dist=${1:?usage: sign-release.sh DIST_DIR}
fpr=${SIGNING_FPR:-$(sed -n 's/^SIGNING_FINGERPRINT = "\([0-9A-F]*\)".*/\1/p' \
    "$(dirname "$0")/../src/gf63_mic_fix/updater.py")}
[ -n "$fpr" ] || { echo "no signing fingerprint" >&2; exit 1; }

for rpm in "$dist"/*.rpm; do
    rpmsign --addsign --define "_gpg_name $fpr" --define "__gpg $(command -v gpg)" "$rpm" >/dev/null
done
cd "$dist"
rm -f -- *.asc SHA256SUMS
sha256sum -- * >SHA256SUMS
for f in *; do
    gpg --batch --yes --local-user "$fpr" --armor --detach-sign -- "$f"
done
ls -1
