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
    gate_body = indent_block(GATE_PATH.read_text())
    marker_start = "<<'PY'\n"
    marker_end = "\n          PY"
    out, pos = [], 0
    while True:
        i = text.find(marker_start, pos)
        if i < 0:
            out.append(text[pos:])
            break
        out.append(text[pos : i + len(marker_start)])
        j = text.index(marker_end, i + len(marker_start))
        out.append(gate_body)
        pos = j
    path.write_text("".join(out))


def main():
    for g in GATES:
        patch(g)
    print("synced", ", ".join(GATES))


if __name__ == "__main__":
    main()
