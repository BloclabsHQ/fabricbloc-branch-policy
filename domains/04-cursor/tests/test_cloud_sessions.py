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
GUARD_WF = ROOT / ".github/workflows/branch-name-guard.yml"


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
        me = [s for s in slots if s["bot_id"] == "madengineer"]
        self.assertEqual(len(me), 1)
        self.assertEqual(me[0]["slots"], 1)
        self.assertEqual(me[0]["purpose"], "product_hotfix")

    def test_CU05_registry_claim(self):
        reg = self.data["launch"]["registry"]
        self.assertTrue(reg["recheck_and_claim_before_launch"])
        self.assertTrue(reg["dedupe_after_launch"])

    def test_CU06_waits(self):
        self.assertLessEqual(self.data["waits"]["max_in_agent_wait_seconds"], 120)
        self.assertTrue(self.data["waits"]["ci_polling_in_agent_forbidden"])

    def test_CU07_archive(self):
        self.assertEqual(self.data["archive"]["idle_archive_hours"], 24)
        triggers = set(self.data["archive"]["triggers"])
        self.assertTrue({"pr_merged", "pr_closed"} <= triggers)

    def test_CU08_routing(self):
        r = self.data["routing"]
        self.assertEqual(r["route"], "MadAgentPM -> Loom")
        labels = set(r.get("agent_harness_ticket_labels") or [])
        self.assertTrue(labels & {"agent-harness", "cursor-harness", "session-economy"})

    def test_CU09_loom_review(self):
        self.assertTrue(self.data["routing"]["loom_never_reviews_own_prs"])

    def test_CU10_grandfather(self):
        ph = self.data["phase_in"]
        self.assertEqual(ph["applies_to"], "new_sessions_only")
        self.assertTrue(ph["grandfather"]["madengineer_in_flight_sessions"])
        self.assertEqual(ph["grandfather"]["branch_prefixes"], ["agent/autonomous/"])

    def test_branch_regex_matches_guard(self):
        import sys

        sys.path.insert(0, str(ROOT / "branch-name-guard"))
        import guard_logic as gl  # noqa: WPS433

        policy_re = self.data["launch"]["branch_name"]["session_branch_regex"]
        guard_legacy = gl.LEGACY_AGENT_RE.pattern
        self.assertEqual(policy_re, guard_legacy)
        guard_rx = gl.LEGACY_AGENT_RE
        policy_rx = re.compile(policy_re)
        samples = (
            "agent/session/docs/658-branch-identity-patterns",
            "agent/autonomous/ci/fleet-branch-guard",
        )
        for sample in samples:
            self.assertIsNotNone(guard_rx.match(sample), sample)
            self.assertIsNotNone(policy_rx.match(sample), sample)
        bot_re = re.compile(self.data["launch"]["branch_name"]["bot_branch_regex"])
        self.assertIsNotNone(bot_re.match("agent/warden/feat/scope-my-slug"))


if __name__ == "__main__":
    unittest.main()
