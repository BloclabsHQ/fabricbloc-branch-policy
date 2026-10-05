#!/usr/bin/env python3
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = __import__("pathlib").Path(__file__).resolve().parent
POLICY_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

import gate_issue_link as gil  # noqa: E402


class TestParseIssueRefs(unittest.TestCase):
    def test_closes_hash(self):
        refs = gil.parse_issue_refs("Fixes #42\n", "BloclabsHQ/fabric-wallet")
        self.assertEqual(refs, [("BloclabsHQ/fabric-wallet", 42)])

    def test_closes_colon_syntax(self):
        refs = gil.parse_issue_refs("Closes: #9", "BloclabsHQ/fabric-wallet")
        self.assertEqual(refs, [("BloclabsHQ/fabric-wallet", 9)])

    def test_cross_repo_with_keyword(self):
        body = "Resolves BloclabsHQ/other#7 and closes #3"
        refs = gil.parse_issue_refs(body, "BloclabsHQ/fabric-wallet")
        self.assertIn(("BloclabsHQ/other", 7), refs)
        self.assertIn(("BloclabsHQ/fabric-wallet", 3), refs)

    def test_cpython_ref_without_keyword_ignored(self):
        body = "ref python/cpython#100000"
        refs = gil.parse_issue_refs(body, "BloclabsHQ/fabric-wallet")
        self.assertEqual(refs, [])

    def test_cpython_with_keyword_still_blocked(self):
        body = "Closes python/cpython#100000"
        refs = gil.parse_issue_refs(body, "BloclabsHQ/fabric-wallet")
        self.assertEqual(refs, [])

    def test_keyword_less_owner_repo_hash_ignored(self):
        body = "see BloclabsHQ/other#5 for context"
        refs = gil.parse_issue_refs(body, "BloclabsHQ/fabric-wallet")
        self.assertEqual(refs, [])

    def test_issue_url_with_keyword(self):
        body = "Fixes https://github.com/BloclabsHQ/fabricbloc/issues/1526"
        refs = gil.parse_issue_refs(body, "BloclabsHQ/fabric-wallet")
        self.assertEqual(refs, [("BloclabsHQ/fabricbloc", 1526)])


class TestCanonParity(unittest.TestCase):
    def test_embedded_enforce_deadline_matches_canon_json(self):
        canon_path = POLICY_ROOT / "rulesets" / "canon.json"
        canon = json.loads(canon_path.read_text())
        self.assertEqual(
            gil.CANON_ISSUE_LINK_ENFORCE_AFTER,
            canon["pins"]["issue_link_enforce_after"],
        )


class TestWorkflowContract(unittest.TestCase):
    def test_app_token_action_pinned_and_client_id(self):
        wf = (POLICY_ROOT / ".github/workflows/gate-issue-link.yml").read_text()
        self.assertIn(
            "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0",
            wf,
        )
        self.assertIn("client-id: ${{ vars.HYGIENE_APP_CLIENT_ID }}", wf)
        self.assertNotIn("create-github-app-token@v1", wf)
        self.assertIn("permission-issues: read", wf)
        self.assertIn("HYGIENE_APP_PRIVATE_KEY missing", wf)


class TestEnforceMode(unittest.TestCase):
    def test_warn_before_canon_deadline_unset_var(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ISSUE_LINK_ENFORCE_AFTER", None)
            with patch.object(
                gil,
                "effective_enforce_deadline",
                return_value=datetime(2099, 1, 1, tzinfo=timezone.utc),
            ):
                self.assertEqual(gil.enforce_mode(), "warn")

    def test_far_future_var_clamped_to_canon_deadline(self):
        future = "2099-01-01T00:00:00Z"
        canon = gil.parse_timestamp(gil.CANON_ISSUE_LINK_ENFORCE_AFTER, "canon")
        with patch.dict(os.environ, {"ISSUE_LINK_ENFORCE_AFTER": future}):
            self.assertEqual(gil.effective_enforce_deadline(), canon)

    def test_unset_var_uses_canon_deadline(self):
        env = os.environ.copy()
        env.pop("ISSUE_LINK_ENFORCE_AFTER", None)
        with patch.dict(os.environ, env, clear=True):
            canon = gil.parse_timestamp(gil.CANON_ISSUE_LINK_ENFORCE_AFTER, "canon")
            self.assertEqual(gil.effective_enforce_deadline(), canon)

    def test_closed_after_deadline(self):
        past = "2000-01-01T00:00:00Z"
        with patch.dict(os.environ, {"ISSUE_LINK_ENFORCE_AFTER": past}):
            self.assertEqual(gil.enforce_mode(), "closed")

    def test_tz_less_deadline_parsed_as_utc(self):
        dt = gil.parse_timestamp("2026-10-07T03:00:00", "test")
        self.assertEqual(dt, datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc))

    def test_invalid_timestamp_fails_clean(self):
        with self.assertRaises(SystemExit):
            gil.parse_timestamp("not-a-date", "ISSUE_LINK_ENFORCE_AFTER")


class TestNoIssueLabel(unittest.TestCase):
    def test_labeled_event_rejects_wrong_actor(self):
        payload = {
            "action": "labeled",
            "label": {"name": "no-issue"},
            "sender": {"login": "evil"},
        }
        with self.assertRaises(SystemExit):
            gil.check_labeled_event(payload)

    def test_labeled_event_allows_madgeniusblink(self):
        payload = {
            "action": "labeled",
            "label": {"name": "no-issue"},
            "sender": {"login": "Madgeniusblink"},
        }
        gil.check_labeled_event(payload)

    def test_newest_label_event_after_readd_by_non_cris(self):
        events = [{"event": "labeled", "label": {"name": "no-issue"}, "actor": {"login": "madgeniusblink"}}]
        events.extend(
            {"event": "commented", "actor": {"login": "x"}}
            for _ in range(149)
        )
        events.append(
            {"event": "labeled", "label": {"name": "no-issue"}, "actor": {"login": "notcris"}}
        )

        def fake_call(path, token=None, accept="application/vnd.github+json", allow_404=False):
            if "/events" in path:
                if "page=2" in path:
                    return []
                return events
            return []

        with patch.object(gil, "call", side_effect=fake_call):
            self.assertFalse(gil.label_applied_by_madgeniusblink("BloclabsHQ/x", 1))

    def test_newest_unlabeled_revokes_exempt(self):
        events = [
            {"event": "labeled", "label": {"name": "no-issue"}, "actor": {"login": "madgeniusblink"}},
            {"event": "unlabeled", "label": {"name": "no-issue"}, "actor": {"login": "madgeniusblink"}},
        ]

        def fake_call(path, token=None, **kw):
            if "/events" in path:
                return events if "page=1" in path or "page=" not in path else []
            return []

        with patch.object(gil, "call", side_effect=fake_call):
            self.assertFalse(gil.label_applied_by_madgeniusblink("BloclabsHQ/x", 1))


class TestEvaluateRefs(unittest.TestCase):
    def test_one_valid_open_closing_ref_enough(self):
        def fake_check(owner_repo, number):
            if number == 42:
                return "ok", None
            return "bad", f"issue {owner_repo}#{number} is not open"

        body = "Closes #42\n\nSee also #99 (closed last week)."
        refs = gil.parse_issue_refs(body, "BloclabsHQ/fabric-wallet")
        with patch.object(gil, "issue_check_result", side_effect=fake_check):
            violations = gil.evaluate_refs(refs, "closed")
        self.assertEqual(violations, [])

    def test_incidental_closed_not_in_refs(self):
        refs = gil.parse_issue_refs("Closes #1\n\n#99 was closed.", "BloclabsHQ/r")
        self.assertEqual(refs, [("BloclabsHQ/r", 1)])

    def test_unverifiable_cross_repo_warn_mode(self):
        with patch.object(
            gil,
            "issue_check_result",
            return_value=("unverifiable", "cannot verify private cross-repo"),
        ):
            with patch.object(gil, "warn") as mock_warn:
                violations = gil.evaluate_refs([("BloclabsHQ/secret", 1)], "warn")
        self.assertEqual(violations, [])
        mock_warn.assert_called()

    def test_unverifiable_cross_repo_closed_mode(self):
        with patch.object(
            gil,
            "issue_check_result",
            return_value=("unverifiable", "cannot verify private cross-repo"),
        ):
            violations = gil.evaluate_refs([("BloclabsHQ/secret", 1)], "closed")
        self.assertTrue(violations)
        self.assertIn("cannot verify", violations[0])


class TestIssueValidation(unittest.TestCase):
    def test_rejects_pr_number(self):
        def fake_call(path, token=None, accept="application/vnd.github+json", allow_404=False):
            return {"state": "open", "pull_request": {"url": "x"}}

        with patch.object(gil, "call", side_effect=fake_call):
            status, reason = gil.issue_check_result("BloclabsHQ/fabric-wallet", 1)
        self.assertEqual(status, "bad")
        self.assertIn("pull request", reason)


if __name__ == "__main__":
    unittest.main()
