#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from embedded_gate import (  # noqa: E402
    VERDICT_RE,
    agent_denied_paths_successful,
    body_without_code_fences,
    classify_review_routes,
    issue_comment_edited,
    is_trusted_verdict_author,
    parse_verdict_from_comments,
    try_reviewer_automation,
)

HEAD = "a" * 40
OLD = "b" * 40
CFG = json.loads((ROOT.parent / "rulesets" / "reviewers.json").read_text())
CURSOR_ID = 199161495
CRIS_ID = 42707764


def comment(body, login="cursoragent", user_id=CURSOR_ID, edited=False):
    created = "2026-10-04T10:00:00Z"
    updated = "2026-10-04T10:05:00Z" if edited else created
    return {
        "body": body,
        "created_at": created,
        "updated_at": updated,
        "user": {"login": login, "id": user_id, "type": "User"},
    }


class TestReviewerRouting(unittest.TestCase):
    def test_verdict_regex(self):
        body = "<!-- fb-verdict: PASS reviewer=sentinel sha=" + HEAD + " -->"
        m = VERDICT_RE.search(body)
        self.assertIsNotNone(m)
        self.assertEqual(m.group("reviewer"), "sentinel")

    def test_classify_fabricbloc_src_auth_sentinel(self):
        rev, cris, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc",
            {"src/auth/login.go"},
            CFG,
        )
        self.assertTrue(matched)
        self.assertEqual(rev, "sentinel")
        self.assertFalse(cris)
        self.assertTrue(sens)

    def test_classify_cris_beats_sentinel_on_secrets(self):
        rev, cris, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc",
            {"secrets/registry.yaml"},
            CFG,
        )
        self.assertTrue(matched)
        self.assertTrue(cris)
        self.assertEqual(rev, "madagentpm")

    def test_classify_iac_aether(self):
        rev, cris, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc",
            {"iac/modules/vpc/main.tf"},
            CFG,
        )
        self.assertEqual(rev, "aether")
        self.assertTrue(sens)

    def test_classify_warden_workflows(self):
        rev, _, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc",
            {".github/workflows/ci.yml"},
            CFG,
        )
        self.assertEqual(rev, "warden")
        self.assertTrue(matched)
        self.assertTrue(sens)

    def test_classify_default_docs_only(self):
        rev, cris, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc",
            {"docs/readme.md"},
            CFG,
        )
        self.assertFalse(matched)
        self.assertEqual(rev, "madagentpm")
        self.assertFalse(cris)
        self.assertFalse(sens)

    def test_classify_wallet_sentinel(self):
        rev, cris, _, matched = classify_review_routes(
            "BloclabsHQ/fabric-wallet",
            {"pkg/crypto/seal.go"},
            CFG,
        )
        self.assertTrue(matched)
        self.assertEqual(rev, "sentinel")
        self.assertFalse(cris)

    def test_trusted_identity_requires_login_and_id(self):
        cfg = dict(CFG, verdict_approval_enabled=True)
        self.assertTrue(
            is_trusted_verdict_author({"login": "cursoragent", "id": CURSOR_ID}, cfg)
        )
        self.assertFalse(
            is_trusted_verdict_author({"login": "cursoragent", "id": 1}, cfg)
        )
        self.assertFalse(
            is_trusted_verdict_author({"login": "evil", "id": CURSOR_ID}, cfg)
        )

    def test_self_pass_verdict_rejected(self):
        cfg = dict(CFG, verdict_approval_enabled=True)
        marker = f"<!-- fb-verdict: PASS reviewer=madagentpm sha={HEAD} -->"
        comments = [comment(marker, login="cursoragent", user_id=CURSOR_ID)]
        v, author = parse_verdict_from_comments(
            comments, HEAD, "madagentpm", {"cursoragent"}, cfg)
        self.assertIsNone(v)
        self.assertIsNone(author)

    def test_verdict_disabled_by_canon_flag(self):
        cfg = dict(CFG, verdict_approval_enabled=False)
        marker = f"<!-- fb-verdict: PASS reviewer=madagentpm sha={HEAD} -->"
        comments = [comment(marker, login="otherhuman", user_id=999)]
        v, _ = parse_verdict_from_comments(comments, HEAD, "madagentpm", set(), cfg)
        self.assertIsNone(v)

    def test_fenced_marker_ignored(self):
        cfg = dict(CFG, verdict_approval_enabled=True)
        inner = f"<!-- fb-verdict: PASS reviewer=madagentpm sha={HEAD} -->"
        body = f"```html\n{inner}\n```"
        comments = [comment(body, login="madgeniusblink", user_id=CRIS_ID)]
        v, _ = parse_verdict_from_comments(comments, HEAD, "madagentpm", set(), cfg)
        self.assertIsNone(v)

    def test_edited_comment_ignored(self):
        cfg = dict(CFG, verdict_approval_enabled=True)
        marker = f"<!-- fb-verdict: PASS reviewer=madagentpm sha={HEAD} -->"
        comments = [comment(marker, login="madgeniusblink", user_id=CRIS_ID, edited=True)]
        v, _ = parse_verdict_from_comments(comments, HEAD, "madagentpm", set(), cfg)
        self.assertIsNone(v)

    def test_wrong_reviewer_slug_rejected(self):
        cfg = dict(CFG, verdict_approval_enabled=True)
        marker = f"<!-- fb-verdict: PASS reviewer=sentinel sha={HEAD} -->"
        comments = [comment(marker, login="madgeniusblink", user_id=CRIS_ID)]
        v, _ = parse_verdict_from_comments(
            comments, HEAD, "madagentpm", set(), cfg)
        self.assertIsNone(v)

    def test_stale_sha_rejected(self):
        cfg = dict(CFG, verdict_approval_enabled=True)
        marker = f"<!-- fb-verdict: PASS reviewer=madagentpm sha={OLD} -->"
        comments = [comment(marker, login="madgeniusblink", user_id=CRIS_ID)]
        v, _ = parse_verdict_from_comments(comments, HEAD, "madagentpm", set(), cfg)
        self.assertIsNone(v)

    def test_valid_verdict_when_enabled(self):
        cfg = dict(CFG, verdict_approval_enabled=True)
        marker = f"<!-- fb-verdict: PASS reviewer=madagentpm sha={HEAD} -->"
        comments = [comment(marker, login="madgeniusblink", user_id=CRIS_ID)]
        v, author = parse_verdict_from_comments(
            comments, HEAD, "madagentpm", set(), cfg)
        self.assertEqual(v, "madagentpm")
        self.assertEqual(author, "madgeniusblink")

    def test_body_without_code_fences(self):
        inner = "<!-- fb-verdict: PASS reviewer=x sha=" + HEAD + " -->"
        self.assertNotIn("fb-verdict", body_without_code_fences(f"```\n{inner}\n```"))

    def test_issue_comment_edited(self):
        self.assertFalse(issue_comment_edited({"created_at": "a", "updated_at": "a"}))
        self.assertTrue(issue_comment_edited({"created_at": "a", "updated_at": "b"}))

    def test_missing_app_token_skips_without_exception(self):
        posts = []

        def fake_post(number, body, token=None):
            posts.append(body)

        import embedded_gate as eg

        orig = eg.post_issue_comment
        orig_denied = eg.agent_denied_paths_successful
        orig_find = eg.find_trusted_verdict
        eg.post_issue_comment = fake_post
        eg.agent_denied_paths_successful = lambda _head: False
        eg.find_trusted_verdict = lambda *a, **k: (None, None)
        try:
            ok = try_reviewer_automation(
                7, HEAD, {"docs/x.md"}, CFG, {"cursoragent"})
        finally:
            eg.post_issue_comment = orig
            eg.agent_denied_paths_successful = orig_denied
            eg.find_trusted_verdict = orig_find
        self.assertFalse(ok)
        self.assertTrue(any("needs-review" in p for p in posts))


class TestAgentDeniedPathsCheck(unittest.TestCase):
    def test_agent_denied_paths_successful_reads_conclusion(self):
        import embedded_gate as eg

        class FakeResp:
            def __init__(self, payload):
                self._payload = payload

            def read(self):
                return json.dumps(self._payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        payloads = [{
            "check_runs": [
                {"name": "agent-denied-paths", "status": "completed", "conclusion": "success"},
            ],
        }]

        def fake_urlopen(req, timeout=30):
            return FakeResp(payloads[0])

        orig_api, orig_repo, orig_token = eg.API, eg.REPO, eg.TOKEN
        eg.REPO = "BloclabsHQ/fabricbloc"
        eg.TOKEN = "test"
        orig_open = eg.urllib.request.urlopen
        eg.urllib.request.urlopen = fake_urlopen
        try:
            self.assertTrue(agent_denied_paths_successful(HEAD))
        finally:
            eg.urllib.request.urlopen = orig_open
            eg.REPO, eg.TOKEN, eg.API = orig_repo, orig_token, orig_api


    def test_mode_empty_string_fails_closed(self):
        import os
        import subprocess

        env = {
            k: v
            for k, v in os.environ.items()
            if k != "MODE"
        }
        env.update({
            "MODE": "",
            "GH_TOKEN": "test",
            "REPO": "BloclabsHQ/fabricbloc",
            "PR": "7",
            "EVENT_HEAD_SHA": HEAD,
            "REPO_DEFAULT_BRANCH": "main",
            "API": "http://127.0.0.1:9",
        })
        p = subprocess.run(
            [sys.executable, str(ROOT / "embedded_gate.py")],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(p.returncode, 1)
        self.assertIn("MODE is unset", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
