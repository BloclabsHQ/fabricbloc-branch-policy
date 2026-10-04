#!/usr/bin/env python3
"""Ensure test_contract.py includes main's C1 schedule test and branch embed tests."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "hygiene" / "test_contract.py"

C1_TEST = '''
    def test_c1_schedule_reaches_sweep_without_plan(self):
        doc = yaml.safe_load((WF / "hygiene-pr-ops-notify.yml").read_text())
        jobs = doc.get("jobs") or {}
        self.assertIn("sweep", jobs)
        sweep = jobs["sweep"]
        self.assertNotIn("needs", sweep)
        cond = sweep.get("if") or ""
        self.assertIn("github.event_name == 'schedule'", cond.replace("\\n", " "))
        self.assertIn("inputs.sweep", cond)
        notify = jobs.get("notify") or {}
        needs = notify.get("needs")
        if isinstance(needs, str):
            needs = [needs]
        self.assertEqual(needs, ["plan"])
'''


def main() -> None:
    text = TARGET.read_text()
    if "test_c1_schedule_reaches_sweep_without_plan" not in text:
        anchor = "    def test_canon_hygiene_sha_when_present(self):"
        if anchor not in text:
            print("merge_contract_tests: missing anchor", file=sys.stderr)
            sys.exit(1)
        text = text.replace(anchor, C1_TEST + "\n" + anchor)
        TARGET.write_text(text)
    subprocess.run(["git", "add", str(TARGET)], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
