#!/usr/bin/env python3
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows/branch-name-guard.yml"
SRC = Path(__file__).resolve().parent / "guard_logic.py"
BOTS_JSON = ROOT / "rulesets" / "bots.json"
INDENT = "          "


def indent_block(text):
    return "\n".join(INDENT + line if line else line for line in text.splitlines())


def sync_bot_slugs_into_guard():
    data = json.loads(BOTS_JSON.read_text())
    slugs = sorted({str(b).lower() for b in data.get("bots") or []})
    if not slugs:
        raise SystemExit("rulesets/bots.json has no bots")
    text = SRC.read_text()
    line = f"SYNCED_BOT_SLUGS = {slugs!r}  # auto-sync from rulesets/bots.json\n"
    if "SYNCED_BOT_SLUGS = " not in text:
        raise SystemExit(f"{SRC}: missing SYNCED_BOT_SLUGS marker")
    text = re.sub(r"^SYNCED_BOT_SLUGS = .*$", line.rstrip(), text, count=1, flags=re.M)
    SRC.write_text(text)


def main():
    sync_bot_slugs_into_guard()
    text = WF.read_text()
    mark, endmark = "<<'PY'\n", "\n          PY"
    if endmark not in text:
        text = text.rstrip() + endmark + "\n"
    start = text.index(mark) + len(mark)
    end = text.rindex(endmark)
    WF.write_text(text[:start] + indent_block(SRC.read_text()) + text[end:])
    print("synced branch-name-guard.yml")


if __name__ == "__main__":
    main()
