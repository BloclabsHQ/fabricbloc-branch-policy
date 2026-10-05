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

    def test_bots_json_has_no_reserved_slugs(self):
        bots = bnp.load_bot_slugs()
        for b in bots:
            self.assertNotIn(b, bnp.RESERVED_BOT_SLUGS)


if __name__ == "__main__":
    unittest.main()
