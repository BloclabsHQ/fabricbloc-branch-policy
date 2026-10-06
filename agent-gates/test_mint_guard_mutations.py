#!/usr/bin/env python3
"""Mutation-gap tests for mint guards (MadAgentPM follow-up). Each test fails if its guard is removed."""
import copy
import json
import os
import sys
import unittest
import urllib.parse

import yaml

from pathlib import Path

AG_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AG_DIR))

import mint_guard_contract as mgc  # noqa: E402
from test import (  # noqa: E402
    AGENT,
    Fake,
    HEAD,
    REVIEWER_BOT,
    REVIEWER_BOT_ID,
    VERDICT_BOT,
    VERDICT_BOT_ID,
    approve,
    reviewer_body,
    run_gate_with_patch,
    setup,
)

HEAD_OTHER = "o" * 40


class TestMintGuardMutations(unittest.TestCase):
    def _doc(self):
        return mgc.load_ror_workflow_doc(yaml)

    def test_a1_concurrency_per_pr(self):
        mgc.assert_concurrency_per_pr(self._doc())
        bad = copy.deepcopy(self._doc())
        bad["jobs"]["reviewer-app-auto-approve"]["concurrency"]["group"] = "ror-mint-global"
        with self.assertRaises(AssertionError):
            mgc.assert_concurrency_per_pr(bad)

    def test_a2_dedupe_requires_head_and_app_id(self):
        import embedded_gate as eg

        text = mgc.embedded_text()
        mgc.assert_dedupe_checks_id_and_head(text)
        posted = []

        def fake_call(path, method="GET", body=None, token=None):
            if method == "POST" and path.endswith("/reviews"):
                posted.append(body)
            return {}

        reviews = [
            approve(REVIEWER_BOT, sha=HEAD, body=reviewer_body(), user_id=REVIEWER_BOT_ID + 1),
        ]
        orig = (eg.call, eg.paginate, eg.REPO)
        eg.call = fake_call
        eg.paginate = lambda path, *a, **k: reviews if path.endswith("/reviews") else []
        eg.REPO = "BloclabsHQ/fabricbloc"
        try:
            self.assertFalse(eg.reviewer_app_already_approved_at_head("7", HEAD))
            eg.submit_reviewer_app_approve_if_needed("7", HEAD, "tok", "madagentpm")
            self.assertEqual(len(posted), 1)
        finally:
            eg.call, eg.paginate, eg.REPO = orig

        def patch(body):
            return body.replace(
                "if login == bot_login and uid == bot_id:",
                "if login == bot_login:",
                1,
            )

        patched = patch(mgc.embedded_text())
        fn = patched.split("def reviewer_app_already_approved_at_head", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("and uid == bot_id", fn)
        with self.assertRaises(AssertionError):
            mgc.assert_dedupe_checks_id_and_head(patched)

    def test_a3_approve_only_via_if_needed(self):
        text = mgc.embedded_text()
        mgc.assert_approve_only_via_if_needed(text)

        def patch(body):
            return body.replace(
                "        if submit_reviewer_app_approve_if_needed(",
                "        submit_reviewer_app_approve(",
                1,
            )

        with self.assertRaises(AssertionError):
            mgc.assert_approve_only_via_if_needed(patch(text))

    def test_a4_main_enforces_mint_eligible(self):
        text = mgc.embedded_text()
        mgc.assert_main_calls_enforce_mint_pr_eligible(text)

        def patch(body):
            return body.replace("        enforce_mint_pr_eligible(pr)\n", "", 1)

        setup(files=("docs/x.md",), **AGENT)
        Fake.routes["/repos/BloclabsHQ/fabricbloc/pulls/7"]["state"] = "closed"
        code_guard, out_guard = run_gate_with_patch(
            "agent-review-of-record",
            lambda b: b,
            extra_env={"ROR_JOB": "mint", "REVIEWER_APP_TOKEN": "tok"},
        )
        self.assertEqual(code_guard, 1, out_guard)
        self.assertIn("must be open", out_guard)

        setup(files=("docs/x.md",), **AGENT)
        Fake.routes["/repos/BloclabsHQ/fabricbloc/pulls/7"]["state"] = "closed"
        code_mut, out_mut = run_gate_with_patch(
            "agent-review-of-record",
            patch,
            extra_env={"ROR_JOB": "mint", "REVIEWER_APP_TOKEN": "tok"},
        )
        self.assertNotIn("must be open", out_mut)

        with self.assertRaises(AssertionError):
            mgc.assert_main_calls_enforce_mint_pr_eligible(patch(text))

    def test_a5_head_rechecked_before_approve(self):
        text = mgc.embedded_text()
        mgc.assert_head_guard_before_approve(text)
        import embedded_gate as eg

        posted = []
        def fake_call(path, method="GET", body=None, token=None):
            if method == "POST" and path.endswith("/reviews"):
                posted.append(body)
            if path.endswith("/pulls/7"):
                return {"head": {"sha": HEAD_OTHER}, "base": {"ref": "main"}, "state": "open"}
            return {}

        orig = eg.call
        eg.call = fake_call
        eg.REPO = "BloclabsHQ/fabricbloc"
        try:
            with self.assertRaises(SystemExit):
                eg.submit_reviewer_app_approve_if_needed(
                    "7", HEAD, "tok", "madagentpm", guard_head=True
                )
            self.assertEqual(posted, [])
        finally:
            eg.call = orig

        def patch(body):
            return body.replace(
                "    if guard_head:\n        mint_live_head_or_fail(number, head)\n",
                "",
                1,
            )

        with self.assertRaises(AssertionError):
            mgc.assert_head_guard_before_approve(patch(text))

    def test_a6_fail_marker_blocks_approve_with_app_token(self):
        import embedded_gate as eg

        posted = []

        def fake_denied(head, *, wait_denied_paths=False, pr_number=None):
            return True

        def fake_page(path, *a, **k):
            if "/comments" in path:
                return [{
                    "body": (
                        f"<!-- fabricbloc-verdict v1 reviewer=madagentpm "
                        f"verdict=FAIL head={HEAD} -->"
                    ),
                    "user": {"login": VERDICT_BOT, "id": VERDICT_BOT_ID},
                }]
            return []

        def fake_call(path, method="GET", body=None, token=None):
            if method == "POST" and path.endswith("/reviews"):
                posted.append(body)
            if path.endswith("/pulls/7"):
                return {"head": {"sha": HEAD}, "base": {"ref": "main"}, "state": "open"}
            return {}

        orig = (
            eg.agent_denied_paths_successful,
            eg.paginate,
            eg.call,
            eg.all_paths_eligible_for_auto,
        )
        eg.agent_denied_paths_successful = fake_denied
        eg.paginate = fake_page
        eg.call = fake_call
        eg.all_paths_eligible_for_auto = lambda *a, **k: False
        eg.REPO = "BloclabsHQ/fabricbloc"
        cfg = {
            "verdict_approval_enabled": True,
            "verdict_app": {"login": VERDICT_BOT, "user_id": VERDICT_BOT_ID},
        }
        os.environ["REVIEWER_APP_TOKEN"] = "tok"
        try:
            ok = eg.try_reviewer_automation(
                "7",
                HEAD,
                ("docs/x.md",),
                cfg,
                set(),
                list(eg.FLOOR_DENIED),
                "agent/warden/feat/x-y",
                wait_denied_paths=True,
            )
        finally:
            os.environ.pop("REVIEWER_APP_TOKEN", None)
            (
                eg.agent_denied_paths_successful,
                eg.paginate,
                eg.call,
                eg.all_paths_eligible_for_auto,
            ) = orig
        self.assertFalse(ok)
        self.assertEqual(posted, [])

    def test_a7_mint_timeout_upper_bound(self):
        mgc.assert_mint_timeout_upper_bound(self._doc())
        bad = copy.deepcopy(self._doc())
        bad["jobs"]["reviewer-app-auto-approve"]["timeout-minutes"] = 60
        with self.assertRaises(AssertionError):
            mgc.assert_mint_timeout_upper_bound(bad)

    def test_a8_default_wait_budget_240(self):
        mgc.assert_mint_env_budget_default(self._doc())
        bad = copy.deepcopy(self._doc())
        step = next(
            s
            for s in bad["jobs"]["reviewer-app-auto-approve"]["steps"]
            if (s.get("env") or {}).get("ROR_JOB") == "mint"
        )
        step["env"]["ROR_MINT_WAIT_BUDGET_SEC"] = "300"
        with self.assertRaises(AssertionError):
            mgc.assert_mint_env_budget_default(bad)

    def test_a9_mint_permissions_pinned(self):
        mgc.assert_mint_permissions_pinned(self._doc())
        bad = copy.deepcopy(self._doc())
        bad["jobs"]["reviewer-app-auto-approve"]["permissions"]["pull-requests"] = "write"
        with self.assertRaises(AssertionError):
            mgc.assert_mint_permissions_pinned(bad)

    def test_a10_empty_live_head_fails_during_poll(self):
        text = mgc.embedded_text()
        mgc.assert_empty_live_head_fails_during_poll(text)
        import embedded_gate as eg

        class FakeResp:
            def read(self):
                return json.dumps({"head": {"sha": ""}}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout=30):
            path = urllib.parse.urlparse(
                req.full_url if hasattr(req, "full_url") else req.get_full_url()
            ).path
            if path.endswith("/pulls/7"):
                return FakeResp()
            return FakeResp()

        orig = (eg.urllib.request.urlopen, eg.REPO, eg.TOKEN)
        eg.urllib.request.urlopen = fake_urlopen
        eg.REPO = "BloclabsHQ/fabricbloc"
        eg.TOKEN = "test"
        eg._reset_ror_mint_wait_deadline()
        os.environ["ROR_MINT_WAIT_BUDGET_SEC"] = "1"
        os.environ["DENIED_PATHS_POLL_INTERVAL_SEC"] = "0"
        try:
            with self.assertRaises(SystemExit):
                eg.agent_denied_paths_successful(HEAD, wait_denied_paths=True, pr_number="7")
        finally:
            eg.urllib.request.urlopen, eg.REPO, eg.TOKEN = orig
            eg._reset_ror_mint_wait_deadline()

        def patch(body):
            return body.replace(
                'fail("live PR head SHA empty during mint wait; failing closed")',
                "return False",
                1,
            )

        with self.assertRaises(AssertionError):
            mgc.assert_empty_live_head_fails_during_poll(patch(text))

    def test_b1_no_combined_ror_job(self):
        text = mgc.embedded_text()
        mgc.assert_no_ror_combined(text)

        def patch(body):
            return body.replace(
                'if ror_job not in ("gate", "mint"):',
                'if ror_job not in ("gate", "mint", "combined"):',
                1,
            ).replace(
                'fail(f"ROR_JOB must be gate or mint for agent-review-of-record, got {ror_job!r}")',
                'ror_job = (os.environ.get("ROR_JOB") or "combined").strip().lower()',
                1,
            )

        with self.assertRaises(AssertionError):
            mgc.assert_no_ror_combined(patch(text))

    def test_b2_newest_check_run_by_id(self):
        text = mgc.embedded_text()
        mgc.assert_newest_check_run_by_id(text)
        import embedded_gate as eg

        runs = [
            {
                "name": "agent-denied-paths",
                "status": "completed",
                "conclusion": "failure",
                "app": {"id": 15368},
                "started_at": "2026-10-05T12:00:00Z",
                "id": 1,
            },
            {
                "name": "agent-denied-paths",
                "status": "completed",
                "conclusion": "success",
                "app": {"id": 15368},
                "started_at": "2026-10-05T11:00:00Z",
                "id": 99,
            },
        ]

        class FakeResp:
            def read(self):
                return json.dumps({"check_runs": runs}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        orig = (eg.urllib.request.urlopen, eg.REPO, eg.TOKEN)
        eg.urllib.request.urlopen = lambda *a, **k: FakeResp()
        eg.REPO = "BloclabsHQ/fabricbloc"
        eg.TOKEN = "test"
        try:
            self.assertTrue(eg.agent_denied_paths_successful(HEAD))
        finally:
            eg.urllib.request.urlopen, eg.REPO, eg.TOKEN = orig

        def patch(body):
            return body.replace(
                "ga_runs.sort(key=lambda r: r.get(\"id\") or 0)",
                'ga_runs.sort(key=lambda r: (r.get("started_at") or "", r.get("id") or 0))',
                1,
            )

        with self.assertRaises(AssertionError):
            mgc.assert_newest_check_run_by_id(patch(text))


if __name__ == "__main__":
    unittest.main(verbosity=1)
