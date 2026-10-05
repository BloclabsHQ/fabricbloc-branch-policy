#!/usr/bin/env python3
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import gate_issue_link as gil  # noqa: E402


class TestParseIssueRefs(unittest.TestCase):
    def test_closes_hash(self):
        refs = gil.parse_issue_refs("Fixes #42\n", "BloclabsHQ/fabric-wallet")
        self.assertEqual(refs, [("BloclabsHQ/fabric-wallet", 42)])

    def test_cross_repo(self):
        body = "Resolves BloclabsHQ/other#7 and closes #3"
        refs = gil.parse_issue_refs(body, "BloclabsHQ/fabric-wallet")
        self.assertIn(("BloclabsHQ/other", 7), refs)
        self.assertIn(("BloclabsHQ/fabric-wallet", 3), refs)


class TestEnforceMode(unittest.TestCase):
    def test_warn_before_deadline(self):
        future = "2099-01-01T00:00:00Z"
        with patch.dict(os.environ, {"ISSUE_LINK_ENFORCE_AFTER": future}):
            self.assertEqual(gil.enforce_mode(), "warn")

    def test_closed_after_deadline(self):
        past = "2000-01-01T00:00:00Z"
        with patch.dict(os.environ, {"ISSUE_LINK_ENFORCE_AFTER": past}):
            self.assertEqual(gil.enforce_mode(), "closed")


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


class TestIssueValidation(unittest.TestCase):
    def test_rejects_pr_number(self):
        def fake_call(path, accept="application/vnd.github+json", allow_404=False):
            return {"state": "open", "pull_request": {"url": "x"}}

        with patch.object(gil, "call", side_effect=fake_call):
            ok, reason = gil.issue_is_valid_open_issue("BloclabsHQ/fabric-wallet", 1)
        self.assertFalse(ok)
        self.assertIn("pull request", reason)


if __name__ == "__main__":
    unittest.main()
