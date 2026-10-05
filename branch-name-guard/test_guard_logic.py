#!/usr/bin/env python3
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import guard_logic as gl  # noqa: E402

BOTS = ["warden", "madengineer", "sentinel"]


class TestBranchGrammar(unittest.TestCase):
    def test_new_bot_grammar(self):
        rc = gl.validate(
            "agent/warden/feat/my-slug",
            ["main"],
            BOTS,
            None,
            "",
            "",
        )
        self.assertEqual(rc, 0)

    def test_unknown_bot_rejected(self):
        with self.assertRaises(SystemExit):
            gl.validate(
                "agent/atlas/feat/my-slug",
                ["main"],
                BOTS,
                None,
                "",
                "",
            )

    def test_legacy_dual_accept(self):
        future = datetime(2099, 1, 1, tzinfo=timezone.utc)
        rc = gl.validate(
            "agent/session/feat/warden-my-slug",
            ["main"],
            BOTS,
            future,
            "",
            "",
        )
        self.assertEqual(rc, 0)

    def test_attributed_bot_new(self):
        self.assertEqual(
            gl.attributed_bot("agent/warden/chore/foo-bar", BOTS),
            "warden",
        )


if __name__ == "__main__":
    unittest.main()
