#!/usr/bin/env python3
"""Contract tests for SE-* secrets registry (B0)."""
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "domains" / "05-secrets" / "registry.yaml"
VALIDATE = ROOT / "domains" / "05-secrets" / "validate_registry.py"
LINT = ROOT / "domains" / "05-secrets" / "lint_registry.py"


class SecretsRegistryB0(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = yaml.safe_load(REGISTRY.read_text())
        cls.by_name = {e["name"]: e for e in cls.data["entries"]}

    def test_validate_exits_zero(self):
        r = subprocess.run([sys.executable, str(VALIDATE)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_lint_report_only_exits_zero(self):
        r = subprocess.run([sys.executable, str(LINT)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("SE-06", r.stdout)
        self.assertIn("SE-11", r.stdout)
        self.assertIn("report-only", r.stdout)

    def test_SE01_unique_names(self):
        names = [e["name"] for e in self.data["entries"]]
        self.assertEqual(len(names), len(set(names)))

    def test_live_org_github_token_visibility_all(self):
        e = self.by_name["ORG_GITHUB_TOKEN"]
        self.assertEqual(e["status"], "live")
        org = next(loc for loc in e["github_locations"] if loc["scope"] == "org")
        self.assertEqual(org["visibility"], "all")

    def test_fabricbloc_action_automation_org_and_repo_override(self):
        e = self.by_name["FABRICBLOC_ACTION_AUTOMATION"]
        scopes = {loc["scope"] for loc in e["github_locations"]}
        self.assertEqual(scopes, {"org", "repo"})
        org = next(loc for loc in e["github_locations"] if loc["scope"] == "org")
        self.assertEqual(org["visibility"], "private")
        repo = next(loc for loc in e["github_locations"] if loc["scope"] == "repo")
        self.assertEqual(repo["repo"], "BloclabsHQ/fabricbloc")
        self.assertTrue(repo.get("overrides_org"))

    def test_cursor_api_key_repo_not_environment(self):
        e = self.by_name["CURSOR_API_KEY"]
        loc = e["github_locations"][0]
        self.assertEqual(loc["scope"], "repo")
        self.assertEqual(loc.get("kind", "actions_secret"), "actions_secret")

    def test_n5_duplicates_slack_and_claude(self):
        for name in ("SLACK_BOT_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
            e = self.by_name[name]
            self.assertTrue(e.get("intentional_duplicate"))
            self.assertEqual(e.get("duplicate_policy"), "N5")

    def test_fabric_iac_aws_deprecated(self):
        for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
            e = self.by_name[name]
            self.assertEqual(e["status"], "deprecated")
            repo = e["github_locations"][0]["repo"]
            self.assertEqual(repo, "BloclabsHQ/fabric-iac")

    def test_policy_audit_planned(self):
        for name in ("POLICY_AUDIT_APP_ID", "POLICY_AUDIT_APP_PRIVATE_KEY"):
            e = self.by_name[name]
            self.assertEqual(e["status"], "planned")
            self.assertIsNone(e["onepassword_item"])
            self.assertIn("TODO(Cris)", e["notes"])

    def test_SE12_vendored_policy_audit_private_key(self):
        self.assertIn("POLICY_AUDIT_APP_PRIVATE_KEY", self.by_name)

    def test_live_infra_token_names(self):
        for name in ("GHCR_READ_TOKEN", "MIMIR_PUSH_TOKEN", "DEV_OP_SERVICE_ACCOUNT_TOKEN"):
            self.assertEqual(self.by_name[name]["status"], "live")


if __name__ == "__main__":
    unittest.main()
