#!/usr/bin/env python3
"""Ensure POLICY_INDEX.md rows point at existing enforcer tests."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "POLICY_INDEX.md"
ROW = re.compile(r"^\| (CU-\d+|AG-\d+) \|")


def main() -> int:
    text = INDEX.read_text()
    bad = []
    for line in text.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        rid = m.group(1)
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 6:
            continue
        test_col = parts[5]
        if rid.startswith("CU-"):
            t = ROOT / "domains" / "04-cursor" / "tests" / "test_cloud_sessions.py"
            if test_col != str(t.relative_to(ROOT)) or not t.is_file():
                bad.append(f"{rid}: test column must be {t.relative_to(ROOT)}")
        elif rid.startswith("AG-"):
            t = ROOT / "agent-gates" / "test.py"
            if test_col != str(t.relative_to(ROOT)) or not t.is_file():
                bad.append(f"{rid}: test column must be {t.relative_to(ROOT)}")
    if bad:
        for b in bad:
            print(b)
        return 1
    print(f"OK {INDEX.name} ({len([l for l in text.splitlines() if ROW.match(l)])} rules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
