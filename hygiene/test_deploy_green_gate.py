#!/usr/bin/env python3
import json
import os
import sys
import unittest
from unittest.mock import patch

HYGIENE = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(HYGIENE))

import deploy_green_gate as dgg  # noqa: E402


class Fake:
    routes = {}

    @classmethod
    def reset(cls):
        cls.routes = {}

    @classmethod
    def install(cls):
        def fake_call(path, *, token=None, accept="application/vnd.github+json", allow_404=False, method="GET", body=None):
            key = path.split("?")[0]
            if key in cls.routes:
                return cls.routes[key]
            if allow_404:
                return None
            raise AssertionError(f"unexpected API path {path}")

        return patch.object(dgg, "call", side_effect=fake_call)


class TestDeployGreenGate(unittest.TestCase):
    def setUp(self):
        Fake.reset()

    def test_success_on_pr_head_checks(self):
        sha = "a" * 40
        head = "b" * 40
        repo = "BloclabsHQ/fabric-wallet"
        Fake.routes[f"/repos/{repo}/commits/{sha}/pulls"] = [
            {"number": 99, "merged_at": "2026-10-04T12:00:00Z", "head": {"sha": head}}
        ]
        Fake.routes[f"/repos/{repo}/commits/{head}/check-runs"] = {
            "check_runs": [
                {"id": 3, "name": "Lint", "conclusion": "success"},
                {"id": 2, "name": "Security Scan", "conclusion": "skipped"},
                {"id": 1, "name": "Test", "conclusion": "success"},
            ]
        }
        with Fake.install():
            out = dgg.verify_pr_head_checks("tok", repo, sha, ["Lint", "Security Scan", "Test"])
        self.assertEqual(out["pr_number"], 99)
        self.assertEqual(out["head_sha"], head)

    def test_fail_missing_check(self):
        sha = "c" * 40
        head = "d" * 40
        repo = "BloclabsHQ/fabric-wallet"
        Fake.routes[f"/repos/{repo}/commits/{sha}/pulls"] = [
            {"number": 1, "merged_at": "2026-10-04T12:00:00Z", "head": {"sha": head}}
        ]
        Fake.routes[f"/repos/{repo}/commits/{head}/check-runs"] = {
            "check_runs": [{"id": 1, "name": "Lint", "conclusion": "success"}]
        }
        with Fake.install():
            with self.assertRaises(SystemExit):
                with patch.object(dgg, "fail", side_effect=lambda *a, **k: sys.exit(1)):
                    dgg.verify_pr_head_checks("tok", repo, sha, ["Lint", "Test"])

    def test_fail_no_merged_pr(self):
        sha = "e" * 40
        repo = "BloclabsHQ/fabric-wallet"
        Fake.routes[f"/repos/{repo}/commits/{sha}/pulls"] = []
        with Fake.install():
            with self.assertRaises(SystemExit):
                with patch.object(dgg, "fail", side_effect=lambda *a, **k: sys.exit(1)):
                    dgg.verify_pr_head_checks("tok", repo, sha, ["Test"])


if __name__ == "__main__":
    unittest.main()
