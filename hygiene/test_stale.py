#!/usr/bin/env python3
"""C2 exemption fixture tests (C2-4 subset)."""
import importlib.util
import sys
import unittest
from pathlib import Path

HYGIENE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HYGIENE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestStaleExemptions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load("common")
        cls.mod = load("stale")

    def test_head_glob(self):
        self.assertTrue(self.mod.head_matches("agent/session/feat/x", "agent/**"))
        self.assertFalse(self.mod.head_matches("madgeniusblink/feat/x", "agent/**"))

    def test_exempt_labels(self):
        self.assertEqual(self.mod.pr_exempt_labels([{"name": "HOLD"}]), "hold")
        self.assertEqual(self.mod.pr_exempt_labels([{"name": "spec:gate"}]), "spec-label")

    def test_close_before_date(self):
        import os
        os.environ["CLOSE_AFTER"] = "2099-01-01T00:00:00-07:00"
        self.assertFalse(self.mod.close_allowed())


if __name__ == "__main__":
    unittest.main()
