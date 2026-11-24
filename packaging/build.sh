#!/bin/sh
# Builds every release artifact: rpm, deb, Arch package, universal tarball and PKGBUILD.
# Usage: packaging/build.sh VERSION OUTDIR      (needs nfpm and msgfmt)
set -eu
version=${1:?usage: build.sh VERSION OUTDIR}
out=${2:?usage: build.sh VERSION OUTDIR}
cd "$(dirname "$0")/.."

code_version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' src/gf63_mic_fix/__init__.py)
if [ "$version" != "$code_version" ]; then
    echo "version $version does not match __version__ = $code_version" >&2
    exit 1
fi

rm -rf build
app=build/root/usr/share/gf63-mic-fix
mkdir -p "$app" "$out"
cp -R src/gf63_mic_fix "$app/"
find "$app" -name __pycache__ -prune -exec rm -rf {} +
for po in po/*.po; do
    lang=$(basename "$po" .po)
    mkdir -p "$app/locale/$lang/LC_MESSAGES"
    msgfmt -c -o "$app/locale/$lang/LC_MESSAGES/gf63-mic-fix.mo" "$po"
done
cp data/signing-key.asc "$app/"
for kind in rpm deb arch; do echo "$kind" >"build/install-type.$kind"; done

for packager in rpm deb archlinux; do
    VERSION=$version nfpm package -f packaging/nfpm.yaml -p "$packager" -t "$out/" >/dev/null
done

# nfpm's archlinux packager stores files as uid/gid 0 without the "root" names, which namcap
# rejects. Repack with the names set, keeping member order, modes and times.
pkg=$(ls "$out"/gf63-mic-fix-"$version"-*.pkg.tar.zst)
mkdir build/pkg
tar --zstd -tf "$pkg" >build/pkg.list
tar --zstd -xpf "$pkg" -C build/pkg
tar --zstd -C build/pkg --owner=root:0 --group=root:0 --no-recursion -T build/pkg.list -cf "$pkg"

# Universal tarball: gf63-mic-fix-VERSION/{app,bin,data,install.sh}. The updater relies on
# this exact top directory name (it binds the signed archive to its version).
top=gf63-mic-fix-$version
mkdir -p "build/$top"
cp -R "$app" "build/$top/app"  # install.sh writes install-type
cp -R bin data "build/$top/"
cp packaging/install.sh "build/$top/install.sh"
tar --sort=name --owner=0 --group=0 --numeric-owner --mtime="@${SOURCE_DATE_EPOCH:-0}" \
    -C build -czf "$out/$top.tar.gz" "$top"
cp packaging/install.sh "$out/install.sh"

sum=$(sha256sum "$out/$top.tar.gz" | cut -d' ' -f1)
sed -e "s/@VERSION@/$version/" -e "s/@SHA256@/$sum/" packaging/arch/PKGBUILD.in >"$out/PKGBUILD"

ls -1 "$out"
