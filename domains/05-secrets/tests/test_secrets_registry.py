#!/usr/bin/env python3
"""Contract tests for §5 registry schema and report-only SE lint."""
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
DOMAIN = ROOT / "domains" / "05-secrets"
REGISTRY = DOMAIN / "registry.yaml"
SECRETS_MD = DOMAIN / "SECRETS.md"
VALIDATE = DOMAIN / "validate_registry.py"
LINT = DOMAIN / "lint_registry.py"

SECTION5_KEYS = frozenset(
    {
        "name",
        "type",
        "kind",
        "stored_as",
        "github",
        "onepassword_item",
        "runtime_env",
        "permissions",
        "owner_role",
        "custodian",
        "rotation_days",
        "last_rotated",
        "status",
        "replaces",
    }
)


class SecretsRegistryB0(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = yaml.safe_load(REGISTRY.read_text())
        cls.by_name = {e["name"]: e for e in cls.data["entries"]}

    def test_validate_schema_only_exits_zero(self):
        r = subprocess.run([sys.executable, str(VALIDATE)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_lint_report_only_exits_zero(self):
        r = subprocess.run([sys.executable, str(LINT)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("report-only", r.stdout)
        for rule in [f"SE-{i:02d}" for i in range(1, 14)]:
            self.assertIn(rule, r.stdout, msg=f"missing {rule} in lint output")

    def test_section5_fields_on_every_entry(self):
        for e in self.data["entries"]:
            self.assertTrue(SECTION5_KEYS <= set(e.keys()), e.get("name"))

    def test_SE12_secrets_md_matches_registry(self):
        reg = {e["name"] for e in self.data["entries"]}
        md = {
            line.strip()
            for line in SECRETS_MD.read_text().splitlines()
            if line.strip()
            and not line.strip().startswith("#")
            and line.strip().replace("_", "").isalnum()
        }
        self.assertEqual(reg, md)

    def test_agent_ops_app_private_key_not_stored(self):
        self.assertNotIn("AGENT_OPS_APP_PRIVATE_KEY", self.by_name)

    def test_gh_read_token_fabric_nft_and_se02_in_lint(self):
        e = self.by_name["GH_READ_TOKEN"]
        repos = e["github"][0]["repos"]
        self.assertIn("BloclabsHQ/fabric-nft", repos)
        r = subprocess.run([sys.executable, str(LINT)], cwd=ROOT, capture_output=True, text=True)
        self.assertIn("GH_READ_TOKEN", r.stdout)
        self.assertIn("SE-02", r.stdout)

    def test_org_github_token_active_org_visibility_all(self):
        e = self.by_name["ORG_GITHUB_TOKEN"]
        self.assertEqual(e["status"], "active")
        org = next(g for g in e["github"] if g["scope"] == "org")
        self.assertEqual(org["visibility"], "all")

    def test_fabricbloc_automation_org_and_repo_list(self):
        e = self.by_name["FABRICBLOC_ACTION_AUTOMATION"]
        scopes = {g["scope"] for g in e["github"]}
        self.assertEqual(scopes, {"org", "repo"})

    def test_cursor_api_key_repo_secret_not_runtime_env(self):
        e = self.by_name["CURSOR_API_KEY"]
        self.assertEqual(e["stored_as"], "secret")
        self.assertIsNone(e["runtime_env"])
        self.assertEqual(e["github"][0]["scope"], "repo")

    def test_n5_duplicate_github_lists(self):
        for name in ("SLACK_BOT_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
            self.assertEqual(len(self.by_name[name]["github"]), 2)

    def test_fabric_iac_aws_deprecated_until(self):
        for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
            e = self.by_name[name]
            self.assertEqual(e["status"], "deprecated(until)")
            self.assertEqual(e["github"][0]["repos"], ["BloclabsHQ/fabric-iac"])

    def test_policy_audit_planned_stored_as(self):
        self.assertEqual(self.by_name["POLICY_AUDIT_APP_ID"]["stored_as"], "variable")
        self.assertEqual(self.by_name["POLICY_AUDIT_APP_PRIVATE_KEY"]["stored_as"], "secret")
        self.assertEqual(self.by_name["POLICY_AUDIT_APP_ID"]["status"], "planned")


if __name__ == "__main__":
    unittest.main()
