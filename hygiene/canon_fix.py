#!/usr/bin/env python3
"""Merge canon.json: main base + branch hygiene_sha (MadAgentPM post-C1 policy)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

AGENT_GATES_SHA = "ea32ff2b6f05b1a3635a764f7823ae4c4da129f0"
C1_SQUASH = "a9b4aa189ec38ba972dee43ac0d13f4f92a1b356"
C1_BRANCH_HEADS = {
    "fbd513a7b72360b2499c718ddf3d2388c58a82b0",
}


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: canon_fix.py <main-canon.json> <branch-canon.json>", file=sys.stderr)
        sys.exit(2)
    main_doc = json.loads(Path(sys.argv[1]).read_text())
    branch_doc = json.loads(Path(sys.argv[2]).read_text())
    hygiene_sha = (branch_doc.get("pins") or {}).get("hygiene_sha", "")
    if hygiene_sha in C1_BRANCH_HEADS:
        hygiene_sha = C1_SQUASH
    main_doc.setdefault("pins", {})["hygiene_sha"] = hygiene_sha
    main_doc["pins"]["agent_gates_sha"] = AGENT_GATES_SHA
    out = Path("rulesets/canon.json")
    out.write_text(json.dumps(main_doc, indent=2) + "\n")


if __name__ == "__main__":
    main()
