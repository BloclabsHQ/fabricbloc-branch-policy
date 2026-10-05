#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows/branch-name-guard.yml"
SRC = Path(__file__).resolve().parent / "guard_logic.py"
INDENT = "          "


def indent_block(text):
    return "\n".join(INDENT + line if line else line for line in text.splitlines())


def main():
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
