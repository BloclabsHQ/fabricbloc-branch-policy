#!/usr/bin/env python3
import importlib.util
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


class TestAutoMerge(unittest.TestCase):
    def test_engine_skip_c35(self):
        load("common")
        mod = load("auto_merge")
        pr = {
            "draft": False,
            "labels": [],
            "head": {"ref": "agent/autonomous/fix/x"},
            "user": {"login": "fabricbloc-agent-ops[bot]"},
        }
        self.assertEqual(mod.skip_reason(pr, [], []), "engine-branch")

    def test_dependabot_major_blocked(self):
        mod = load("auto_merge")
        pr = {"user": {"login": "dependabot[bot]"}}
        self.assertFalse(mod.dependabot_allowed(pr, True, "version-update:semver-major"))
        self.assertTrue(mod.dependabot_allowed(pr, True, "version-update:semver-minor"))

    def test_never_allowlist(self):
        common = load("common")
        self.assertIn("BloclabsHQ/fabricbloc-branch-policy", common.FLOOR_NEVER_ALLOWLIST)


if __name__ == "__main__":
    unittest.main()
