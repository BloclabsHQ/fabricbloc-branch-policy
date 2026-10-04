#!/usr/bin/env python3
"""Policy tests for CU-* rules encoded in cloud-sessions.yaml."""
import re
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
POLICY = ROOT / "domains" / "04-cursor" / "cloud-sessions.yaml"


class CloudSessionsPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = yaml.safe_load(POLICY.read_text())

    def test_validator_exits_zero(self):
        r = subprocess.run(
            [sys.executable, str(ROOT / "domains" / "04-cursor" / "validate_cloud_sessions.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_CU01_find_by_pr(self):
        wk = self.data["launch"]["work_key"]
        self.assertEqual(wk["strategy"], "find_by_pr_then_reply")
        self.assertTrue(wk["never_relaunch_if_agent_exists"])

    def test_CU03_caps(self):
        c = self.data["caps"]
        self.assertEqual(c["max_concurrent_running"], 4)
        self.assertEqual(c["max_concurrent_per_bot"], 2)
        self.assertEqual(c["max_concurrent_per_repo"], 2)
        self.assertEqual(c["max_launches_per_hour"], 6)

    def test_CU04_hotfix_slot(self):
        slots = self.data["caps"]["reserved_slots"]
        self.assertTrue(any(s["bot_id"] == "madengineer" and s["slots"] == 1 for s in slots))

    def test_CU05_registry_claim(self):
        reg = self.data["launch"]["registry"]
        self.assertTrue(reg["recheck_and_claim_before_launch"])
        self.assertTrue(reg["dedupe_after_launch"])

    def test_CU06_waits(self):
        self.assertLessEqual(self.data["waits"]["max_in_agent_wait_seconds"], 120)
        self.assertTrue(self.data["waits"]["ci_polling_in_agent_forbidden"])

    def test_CU07_archive(self):
        self.assertGreaterEqual(self.data["archive"]["idle_archive_hours"], 24)
        triggers = set(self.data["archive"]["triggers"])
        self.assertTrue({"pr_merged", "pr_closed"} <= triggers)

    def test_CU08_routing(self):
        r = self.data["routing"]
        self.assertIn("MadAgentPM", r["route"])
        self.assertIn("Loom", r["route"])
        labels = set(r.get("agent_harness_ticket_labels") or [])
        self.assertTrue(labels & {"agent-harness", "cursor-harness", "session-economy"})

    def test_CU09_loom_review(self):
        self.assertTrue(self.data["routing"]["loom_never_reviews_own_prs"])

    def test_CU10_grandfather(self):
        ph = self.data["phase_in"]
        self.assertEqual(ph["applies_to"], "new_sessions_only")
        self.assertIn("agent/autonomous/", ph["grandfather"]["branch_prefixes"])

    def test_branch_regex_matches_guard(self):
        rx = self.data["launch"]["branch_name"]["session_branch_regex"]
        guard_sample = "agent/session/docs/658-branch-identity-patterns"
        self.assertIsNotNone(re.match(rx, guard_sample))


if __name__ == "__main__":
    unittest.main()
