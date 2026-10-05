#!/usr/bin/env python3
"""Embed agent-gates/gate_issue_link.py into gate-issue-link.yml."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows" / "gate-issue-link.yml"
SRC = Path(__file__).resolve().parent / "gate_issue_link.py"
INDENT = "          "


def indent_block(text):
    return "\n".join(INDENT + line if line else line for line in text.splitlines())


def main():
    text = WF.read_text()
    mark, endmark = "<<'PY'\n", "\n          PY"
    if mark not in text:
        raise SystemExit(f"{WF}: missing PY heredoc")
    start = text.index(mark) + len(mark)
    end = text.rindex(endmark)
    body = indent_block(SRC.read_text())
    WF.write_text(text[:start] + body + text[end:])
    print("synced gate-issue-link.yml")


if __name__ == "__main__":
    main()
