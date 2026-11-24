#!/bin/sh
# End-to-end check of the signed package repositories, all in local containers:
# sign + build the apt/dnf repos (Ubuntu, like CI), serve them over HTTP, then install from them
# on Fedora (gpgcheck + repo_gpgcheck) and Ubuntu (apt update must not warn about signatures).
# Usage: tests/packaging/test_repos.sh DIST_DIR GNUPGHOME_WITH_THE_PRIVATE_KEY [PORT]
set -eu
cd "$(dirname "$0")/../.."
src_dist=$(cd "$1" && pwd)
keys=$(cd "$2" && pwd)
port=${3:-8765}
work=$(mktemp -d "${TMPDIR:-/tmp}/gf63-repo-tests.XXXXXX")
mkdir "$work/dist" "$work/site"
cp "$src_dist"/*.rpm "$src_dist"/*.deb "$work/dist/"

echo "== sign and build the repositories (ubuntu:24.04)"
podman run --rm --pull=newer -v "$PWD:/src:ro,Z" -v "$keys:/keys:ro,Z" -v "$work:/work:Z" ubuntu:24.04 sh -ec '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq && apt-get install -y -qq rpm createrepo-c apt-utils gnupg >/dev/null
    export GNUPGHOME=$(mktemp -d) && cp /keys/private.asc "$GNUPGHOME/"
    gpg --batch --import "$GNUPGHOME/private.asc" 2>/dev/null
    /src/scripts/sign-release.sh /work/dist >/dev/null
    /src/scripts/update-repos.sh /work/dist /work/site'

python3 -m http.server "$port" -d "$work/site" >/dev/null 2>&1 &
server=$!
trap 'kill $server 2>/dev/null' EXIT
sleep 1
url=http://127.0.0.1:$port

echo "== dnf from the repository (fedora)"
podman run --rm --pull=newer --network=host fedora:latest sh -ec "
    cat > /etc/yum.repos.d/gf63.repo <<REPO
[gf63-mic-fix]
name=GF63 Mic Fix (test)
baseurl=$url/rpm/
gpgcheck=1
repo_gpgcheck=1
gpgkey=$url/signing-key.asc
REPO
    dnf install -y -q gf63-mic-fix 2>&1 | tee /tmp/out
    ! grep -qi 'skipped OpenPGP' /tmp/out
    rpm -q gf63-mic-fix && gf63-mic-fix --version"

echo "== apt from the repository (ubuntu:24.04)"
podman run --rm --network=host ubuntu:24.04 sh -ec "
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq && apt-get install -y -qq ca-certificates curl >/dev/null
    curl -fsS $url/signing-key.asc -o /usr/share/keyrings/gf63-test.asc
    printf 'Types: deb\nURIs: $url/deb/\nSuites: ./\nSigned-By: /usr/share/keyrings/gf63-test.asc\n' \
        > /etc/apt/sources.list.d/gf63-test.sources
    apt-get update 2>&1 | tee /tmp/out
    ! grep -E '^(W|E):' /tmp/out
    apt-get install -y -qq gf63-mic-fix >/dev/null && gf63-mic-fix --version"
echo "repos OK (site kept in $work/site)"
