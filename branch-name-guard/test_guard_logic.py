#!/usr/bin/env python3
import sys
import unittest
from datetime import datetime, timezone

ROOT = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import guard_logic as gl  # noqa: E402

BOTS = ["warden", "madengineer", "sentinel"]


class TestBranchGrammar(unittest.TestCase):
    def test_new_bot_grammar_scope_slug(self):
        rc = gl.validate(
            "agent/warden/feat/scope-my-slug",
            ["main"],
            BOTS,
            None,
            "2026-10-01T00:00:00Z",
        )
        self.assertEqual(rc, 0)

    def test_unknown_bot_rejected(self):
        with self.assertRaises(SystemExit):
            gl.validate(
                "agent/atlas/feat/scope-my-slug",
                ["main"],
                BOTS,
                None,
                "2026-10-01T00:00:00Z",
            )

    def test_legacy_dual_accept_before_cutoff(self):
        future = datetime(2099, 1, 1, tzinfo=timezone.utc)
        rc = gl.validate(
            "agent/session/feat/warden-my-slug",
            ["main"],
            BOTS,
            future,
            "2026-10-01T00:00:00Z",
        )
        self.assertEqual(rc, 0)

    def test_legacy_after_cutoff_old_pr_ok(self):
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        rc = gl.validate(
            "agent/session/feat/warden-my-slug",
            ["main"],
            BOTS,
            past,
            "2019-06-01T00:00:00Z",
        )
        self.assertEqual(rc, 0)

    def test_legacy_after_cutoff_new_pr_fail(self):
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        with self.assertRaises(SystemExit):
            gl.validate(
                "agent/session/feat/warden-my-slug",
                ["main"],
                BOTS,
                past,
                "2021-06-01T00:00:00Z",
            )

    def test_attributed_bot_new(self):
        self.assertEqual(
            gl.attributed_bot("agent/warden/chore/scope-foo-bar", BOTS),
            "warden",
        )


if __name__ == "__main__":
    unittest.main()
