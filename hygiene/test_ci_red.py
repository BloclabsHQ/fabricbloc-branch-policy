#!/usr/bin/env python3
import importlib.util
import json
import os
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


class TestCiRed(unittest.TestCase):
    def test_cancelled_not_failure_c45(self):
        mod = load("ci_red")
        self.assertIsNone(mod.run_is_failure({"conclusion": "cancelled"}))
        self.assertTrue(mod.run_is_failure({"conclusion": "failure"}))
        self.assertFalse(mod.run_is_failure({"conclusion": "success"}))

    def test_consecutive_one_no_issue_c41(self):
        mod = load("ci_red")
        outcomes = [mod.run_is_failure({"conclusion": "failure"})]
        self.assertEqual(len([o for o in outcomes if o]), 1)


if __name__ == "__main__":
    unittest.main()
