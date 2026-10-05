#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "scripts" / "branch-name-policy.py"


def load_policy():
    spec = importlib.util.spec_from_file_location("branch_name_policy", POLICY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bnp = load_policy()


class TestBranchNamePolicy(unittest.TestCase):
    def test_legacy_accepts_docs_ci(self):
        for branch in (
            "agent/session/docs/658-branch-identity-patterns",
            "agent/autonomous/ci/fleet-branch-guard",
        ):
            self.assertIsNotNone(bnp.LEGACY_AGENT_RE.match(branch), branch)

    def test_legacy_rejects_short_slug(self):
        self.assertIsNone(bnp.LEGACY_AGENT_RE.match("agent/session/docs/identity"))

    def test_bot_slug_requires_scope_slug(self):
        bots = ["warden"]
        rx = bnp.bot_agent_re(bots)
        self.assertIsNotNone(rx.match("agent/warden/feat/scope-my-slug"))
        self.assertIsNone(rx.match("agent/warden/feat/nohyphen"))

    def test_aether_docs_branch_matches_bot_grammar(self):
        bots = bnp.load_bot_slugs()
        rx = bnp.bot_agent_re(bots)
        branch = "agent/aether/docs/atlas-http-events-spec"
        self.assertIsNotNone(rx.fullmatch(branch), branch)

    def test_provider_prefixes_not_bot_grammar(self):
        bots = bnp.load_bot_slugs()
        rx = bnp.bot_agent_re(bots)
        for branch in (
            "codex/docs/my-feature-slug",
            "agent/codex/docs/my-feature-slug",
            "cursor/fix/my-feature-slug",
        ):
            self.assertIsNone(rx.fullmatch(branch), branch)

    def test_bots_json_has_no_reserved_slugs(self):
        bots = bnp.load_bot_slugs()
        for b in bots:
            self.assertNotIn(b, bnp.RESERVED_BOT_SLUGS)

    def test_cloud_sessions_yaml_matches_bots_json(self):
        import yaml

        policy_path = ROOT / "domains" / "04-cursor" / "cloud-sessions.yaml"
        data = yaml.safe_load(policy_path.read_text())
        branch_name = data["launch"]["branch_name"]
        bots = bnp.load_bot_slugs()
        self.assertEqual(branch_name["bot_branch_regex"], bnp.bot_branch_regex_from_bots(bots))
        self.assertEqual(branch_name["agent_re"], bnp.agent_re_combined(bots))


if __name__ == "__main__":
    unittest.main()
