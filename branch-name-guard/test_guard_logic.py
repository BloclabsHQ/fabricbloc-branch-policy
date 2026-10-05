#!/usr/bin/env python3
import json
import os
import sys
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

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
            gl.parse_timestamp(gl.CANON_LEGACY_BRANCH_PR_CREATED_BEFORE, "canon"),
            "2026-10-01T00:00:00Z",
        )
        self.assertEqual(rc, 0)

    def test_aether_docs_branch_passes(self):
        """fabricbloc#1581-style agent/<bot>/… must pass (not legacy session-only pin)."""
        bots = list(gl.SYNCED_BOT_SLUGS)
        rc = gl.validate(
            "agent/aether/docs/atlas-http-events-spec",
            ["main"],
            bots,
            gl.parse_timestamp(gl.CANON_LEGACY_BRANCH_PR_CREATED_BEFORE, "canon"),
            "2026-10-01T00:00:00Z",
        )
        self.assertEqual(rc, 0)
        self.assertEqual(
            gl.attributed_bot("agent/aether/docs/atlas-http-events-spec", bots),
            "aether",
        )

    def test_unknown_bot_rejected(self):
        with self.assertRaises(SystemExit):
            gl.validate(
                "agent/atlas/feat/scope-my-slug",
                ["main"],
                BOTS,
                gl.parse_timestamp(gl.CANON_LEGACY_BRANCH_PR_CREATED_BEFORE, "canon"),
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


class TestCanonParity(unittest.TestCase):
    def test_embedded_legacy_cutoff_matches_canon_json(self):
        root = Path(__file__).resolve().parents[1]
        canon = json.loads((root / "rulesets/canon.json").read_text())
        self.assertEqual(
            gl.CANON_LEGACY_BRANCH_PR_CREATED_BEFORE,
            canon["pins"]["legacy_branch_pr_created_before"],
        )

    def test_embedded_bots_pin_matches_canon_json(self):
        root = Path(__file__).resolve().parents[1]
        canon = json.loads((root / "rulesets/canon.json").read_text())
        self.assertEqual(
            gl.CANON_BOTS_JSON_SHA,
            canon["pins"]["branch_name_guard_sha"],
        )


class TestLegacyCutoffPolicy(unittest.TestCase):
    def test_unset_var_uses_canon(self):
        env = os.environ.copy()
        env.pop("LEGACY_BRANCH_PR_CREATED_BEFORE", None)
        with patch.dict(os.environ, env, clear=True):
            cutoff = gl.effective_legacy_cutoff()
        canon = gl.parse_timestamp(gl.CANON_LEGACY_BRANCH_PR_CREATED_BEFORE, "canon")
        self.assertEqual(cutoff, canon)

    def test_far_future_var_clamped_to_canon(self):
        future = "2099-01-01T00:00:00Z"
        canon = gl.parse_timestamp(gl.CANON_LEGACY_BRANCH_PR_CREATED_BEFORE, "canon")
        with patch.dict(os.environ, {"LEGACY_BRANCH_PR_CREATED_BEFORE": future}):
            self.assertEqual(gl.effective_legacy_cutoff(), canon)

    def test_earlier_var_moves_cutoff(self):
        earlier = "2026-10-10T00:00:00Z"
        with patch.dict(os.environ, {"LEGACY_BRANCH_PR_CREATED_BEFORE": earlier}):
            self.assertEqual(
                gl.effective_legacy_cutoff(),
                gl.parse_timestamp(earlier, "var"),
            )

    def test_tz_less_deadline_as_utc(self):
        dt = gl.parse_timestamp("2026-10-19T00:00:00", "test")
        self.assertEqual(dt, datetime(2026, 10, 19, 0, 0, tzinfo=timezone.utc))

    def test_legacy_denied_after_cutoff_for_new_pr(self):
        cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
        self.assertFalse(gl.legacy_allowed_for_pr(cutoff, "2021-01-01T00:00:00Z"))


class TestBotsJsonPin(unittest.TestCase):
    def test_fetch_tries_pin_and_main_never_pr_head(self):
        calls = []

        def fake_fetch(repo, token, ref):
            calls.append(ref)
            raise urllib.error.HTTPError("url", 404, "missing", {}, None)

        with patch.object(gl, "ref_is_on_main_history", return_value=True):
            with patch.object(gl, "fetch_bots_json_at_ref", side_effect=fake_fetch):
                with patch.dict(
                    os.environ,
                    {"GH_TOKEN": "x", "POLICY_BOTS_JSON_SHA": "deadbeef" * 5},
                    clear=False,
                ):
                    os.environ.pop("BOTS_JSON_REF", None)
                    data = gl.fetch_bots_json_from_api()
        self.assertIsNone(data)
        self.assertEqual(calls, ["deadbeef" * 5, "main"])
        self.assertNotIn("refs/pull", " ".join(calls))

    def test_untrusted_pin_fails_closed(self):
        with patch.object(gl, "ref_is_on_main_history", return_value=False):
            with patch.dict(
                os.environ,
                {"GH_TOKEN": "x", "POLICY_BOTS_JSON_SHA": "badc0ffee" * 5},
                clear=False,
            ):
                with self.assertRaises(SystemExit):
                    gl.fetch_bots_json_from_api()

    def test_legacy_branch_not_bot_grammar(self):
        """Legacy session path must not match bot/<bot>/ regex (fullmatch)."""
        branch = "agent/session/feat/warden-my-slug"
        self.assertIsNone(gl.bot_agent_re(gl.SYNCED_BOT_SLUGS).fullmatch(branch))
        self.assertIsNotNone(gl.LEGACY_AGENT_RE.fullmatch(branch))

    def test_synced_slugs_match_bots_json(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root / "rulesets/bots.json").read_text())
        expected = sorted({str(b).lower() for b in data["bots"]})
        self.assertEqual(sorted(gl.SYNCED_BOT_SLUGS), expected)


if __name__ == "__main__":
    unittest.main()
