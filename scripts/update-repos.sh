#!/bin/sh
# Adds the packages in DIST_DIR to the apt and dnf repositories kept in SITE_DIR (the gh-pages
# checkout) and re-signs their indexes. Old packages stay, so pinned installs keep working.
# Usage: scripts/update-repos.sh DIST_DIR SITE_DIR   (needs createrepo_c, apt-ftparchive, gpg)
set -eu
dist=$(cd "${1:?usage: update-repos.sh DIST_DIR SITE_DIR}" && pwd)
site=$(cd "${2:?usage: update-repos.sh DIST_DIR SITE_DIR}" && pwd)
root=$(cd "$(dirname "$0")/.." && pwd)
fpr=${SIGNING_FPR:-$(sed -n 's/^SIGNING_FINGERPRINT = "\([0-9A-F]*\)".*/\1/p' \
    "$root/src/gf63_mic_fix/updater.py")}
sign() { gpg --batch --yes --local-user "$fpr" "$@"; }

mkdir -p "$site/rpm" "$site/deb"
cp "$dist"/*.rpm "$site/rpm/"
createrepo_c --update --quiet "$site/rpm"
sign --armor --detach-sign -o "$site/rpm/repodata/repomd.xml.asc" "$site/rpm/repodata/repomd.xml"

cp "$dist"/*.deb "$site/deb/"
(
    cd "$site/deb"
    apt-ftparchive packages . >Packages
    gzip -9 -k -f Packages
    apt-ftparchive -o APT::FTPArchive::Release::Origin=gf63-mic-fix \
        -o APT::FTPArchive::Release::Label="GF63 Mic Fix" release . >Release
    sign --clearsign -o InRelease Release
    sign --armor --detach-sign -o Release.gpg Release
)

cp "$root/data/signing-key.asc" "$site/signing-key.asc"
touch "$site/.nojekyll"
cat >"$site/index.html" <<'HTML'
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>GF63 Mic Fix packages</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="font-family: sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem">
<h1>GF63 Mic Fix packages</h1>
<p>Package repositories used by the app for updates (<a href="rpm/">rpm</a>,
<a href="deb/">deb</a>, <a href="signing-key.asc">signing key</a>).</p>
<p>Install instructions: <a href="https://github.com/junior9283/gf63-mic-fix">github.com/junior9283/gf63-mic-fix</a></p>
</body></html>
HTML
echo "repositories updated in $site"
