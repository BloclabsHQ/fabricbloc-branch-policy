#!/usr/bin/env python3
"""Rewrite both workflow heredocs from agent-gates/embedded_gate.py."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
GATES = ("agent-denied-paths", "agent-review-of-record")
GATE_PATH = Path(__file__).resolve().parent / "embedded_gate.py"
INDENT = "          "


def indent_block(text):
    return "\n".join(INDENT + line if line else line for line in text.splitlines())


def patch(name):
    path = WF / f"{name}.yml"
    text = path.read_text()
    start = text.index("<<'PY'\n") + len("<<'PY'\n")
    end = text.rindex("\n          PY")
    new = text[:start] + indent_block(GATE_PATH.read_text()) + text[end:]
    path.write_text(new)


def main():
    for g in GATES:
        patch(g)
    print("synced", ", ".join(GATES))


if __name__ == "__main__":
    main()
