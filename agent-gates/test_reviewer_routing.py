#!/usr/bin/env python3
import sys
import unittest

ROOT = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from embedded_gate import VERDICT_RE, classify_review_routes  # noqa: E402


class TestReviewerRouting(unittest.TestCase):
    def test_verdict_regex(self):
        body = "<!-- fb-verdict: PASS reviewer=sentinel sha=" + "a" * 40 + " -->"
        m = VERDICT_RE.search(body)
        self.assertIsNotNone(m)
        self.assertEqual(m.group("reviewer"), "sentinel")

    def test_classify_wallet_to_sentinel(self):
        cfg = {
            "default_reviewer": "madagentpm",
            "routes": [
                {
                    "repos": ["fabric-wallet"],
                    "path_globs": ["**/crypto/**"],
                    "reviewer": "sentinel",
                }
            ],
        }
        rev, cris, _ = classify_review_routes(
            "BloclabsHQ/fabric-wallet",
            {"pkg/crypto/foo.go"},
            cfg,
        )
        self.assertEqual(rev, "sentinel")
        self.assertFalse(cris)

    def test_cris_required(self):
        cfg = {
            "default_reviewer": "madagentpm",
            "routes": [
                {
                    "path_globs": ["**/iam/**"],
                    "reviewer": "madagentpm",
                    "cris_required": True,
                }
            ],
        }
        _rev, cris, _ = classify_review_routes(
            "BloclabsHQ/fabricbloc",
            {"infra/iam/role.json"},
            cfg,
        )
        self.assertTrue(cris)


if __name__ == "__main__":
    unittest.main()
