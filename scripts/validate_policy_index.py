#!/usr/bin/env python3
"""Ensure POLICY_INDEX.md rows point at existing enforcer tests."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "POLICY_INDEX.md"
ROW = re.compile(r"^\| (CU-\d+|AG-\d+|MR-\d+|SE-\d+) \|")


def main() -> int:
    index = Path(sys.argv[1]) if len(sys.argv) > 1 else INDEX
    text = index.read_text()
    bad = []
    n_rules = 0
    for line in text.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        n_rules += 1
        rid = m.group(1)
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 5:
            bad.append(f"{rid}: row has {len(parts)} columns, expected at least 5 (ID..Test)")
            continue
        test_col = parts[4]
        if rid.startswith("CU-"):
            t = ROOT / "domains" / "04-cursor" / "tests" / "test_cloud_sessions.py"
            if test_col != str(t.relative_to(ROOT)) or not t.is_file():
                bad.append(f"{rid}: test column must be {t.relative_to(ROOT)}")
        elif rid.startswith("AG-"):
            t = ROOT / "agent-gates" / "test.py"
            if test_col != str(t.relative_to(ROOT)) or not t.is_file():
                bad.append(f"{rid}: test column must be {t.relative_to(ROOT)}")
        elif rid.startswith("MR-"):
            t = ROOT / "domains" / "02-merge-rulesets" / "env-drift" / "tests" / "test_env_drift.py"
            if test_col != str(t.relative_to(ROOT)) or not t.is_file():
                bad.append(f"{rid}: test column must be {t.relative_to(ROOT)}")
        elif rid.startswith("SE-"):
            t = ROOT / "domains" / "05-secrets" / "tests" / "test_secrets_registry.py"
            if test_col != str(t.relative_to(ROOT)) or not t.is_file():
                bad.append(f"{rid}: test column must be {t.relative_to(ROOT)}")
    if bad:
        for b in bad:
            print(b)
        return 1
    print(f"OK {INDEX.name} ({n_rules} rules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
