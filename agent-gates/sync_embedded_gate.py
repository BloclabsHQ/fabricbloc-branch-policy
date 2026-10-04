#!/usr/bin/env python3
"""Rewrite both workflow heredocs from agent-gates/embedded_gate.py."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
GATES = ("agent-denied-paths", "agent-review-of-record")
GATE_PATH = Path(__file__).resolve().parent / "embedded_gate.py"
CANON_PATH = ROOT / "rulesets" / "canon.json"
INDENT = "          "


def bootstrap_refs_from_canon():
    canon = json.loads(CANON_PATH.read_text())
    for rs in canon.get("organization_rulesets") or []:
        if isinstance(rs, dict) and rs.get("name") == "canon-agent-gates":
            raw = rs.get("_bootstrap_ref_include") or []
            return sorted(
                e for e in raw if isinstance(e, str) and e.startswith("refs/heads/")
            )
    return []


def refresh_embedded_bootstrap_constant():
    refs = bootstrap_refs_from_canon()
    inner = ", ".join(repr(r) for r in refs)
    line = f"BOOTSTRAP_BASE_REFS = frozenset({{{inner}}})"
    text = GATE_PATH.read_text()
    new_text, n = re.subn(
        r"^BOOTSTRAP_BASE_REFS = frozenset\((?:\{.*\})?\)\s*$",
        line,
        text,
        count=1,
        flags=re.M,
    )
    if n != 1:
        raise SystemExit("embedded_gate.py: BOOTSTRAP_BASE_REFS line not found")
    GATE_PATH.write_text(new_text)


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
    refresh_embedded_bootstrap_constant()
    for g in GATES:
        patch(g)
    print("synced", ", ".join(GATES))


if __name__ == "__main__":
    main()
