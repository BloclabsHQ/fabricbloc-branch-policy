#!/usr/bin/env python3
"""Lightweight contract tests for FC-01 funds/custody human gate."""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
INDEX = ROOT / "POLICY_INDEX.md"
RULES = ROOT / "domains" / "06-funds-custody" / "rules.yaml"
DOC = ROOT / "docs" / "FC-01-funds-custody-human-gate.md"

REQUIRED_DOC_PHRASES = (
    "testnet",
    "fork",
    "Cris",
    "DEPLOYER_KEY",
    "OPERATOR_KEY",
    "treasury",
    "prod deploy",
)


class FundsCustodyGate(unittest.TestCase):
    def test_policy_index_contains_fc01(self):
        text = INDEX.read_text()
        self.assertIn("FC-01", text)
        self.assertIn("06-funds-custody", text)
        self.assertIn("domains/06-funds-custody/tests/test_funds_custody_gate.py", text)

    def test_rules_yaml_has_fc01(self):
        data = yaml.safe_load(RULES.read_text())
        self.assertIn("FC-01", data["rules"])
        fc = data["rules"]["FC-01"]
        self.assertEqual(fc["named_human"], "Cris")
        self.assertIn("testnet", fc["default_environment"])

    def test_consumer_doc_exists_with_required_phrases(self):
        self.assertTrue(DOC.is_file(), f"missing {DOC.relative_to(ROOT)}")
        body = DOC.read_text()
        for phrase in REQUIRED_DOC_PHRASES:
            self.assertIn(phrase, body, f"missing phrase: {phrase!r}")


if __name__ == "__main__":
    unittest.main()
