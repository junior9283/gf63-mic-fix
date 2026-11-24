#!/bin/sh
# Re-extracts translatable strings and merges them into every .po file.
set -eu
cd "$(dirname "$0")/.."
version=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/gf63_mic_fix/__init__.py)
find src -name '*.py' | sort | xargs xgettext -L Python --keyword=_ --from-code=UTF-8 \
    --package-name=gf63-mic-fix --package-version="$version" \
    --msgid-bugs-address=https://github.com/junior9283/gf63-mic-fix/issues -o po/gf63-mic-fix.pot
for po in po/*.po; do msgmerge -q --update --backup=none "$po" po/gf63-mic-fix.pot; done
