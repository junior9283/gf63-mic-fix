"""Fills empty msgstr entries of a .po file from a JSON {msgid: msgstr} map. Dev helper."""

import json
import sys
from pathlib import Path


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def main(po_path: str, map_path: str) -> int:
    tr = json.loads(Path(map_path).read_text())
    out, missing = [], []
    for block in Path(po_path).read_text().split("\n\n"):
        lines = block.splitlines()
        fields, key, start = {}, None, None
        for i, line in enumerate(lines):
            if line.startswith(("msgid ", "msgstr ")):
                key, _, rest = line.partition(" ")
                fields[key] = rest[1:-1]
                if key == "msgstr":
                    start = i
            elif line.startswith('"') and key:
                fields[key] += line[1:-1]
        msgid = fields.get("msgid", "").replace('\\"', '"')
        if msgid and not fields.get("msgstr"):
            if msgid in tr:
                lines = lines[:start] + [f'msgstr "{esc(tr[msgid])}"']
            else:
                missing.append(msgid)
        out.append("\n".join(lines))
    Path(po_path).write_text("\n\n".join(out))
    for m in missing:
        print("MISSING:", m)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
