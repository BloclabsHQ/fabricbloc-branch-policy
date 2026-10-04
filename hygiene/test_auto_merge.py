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
        self.assertEqual(mod.pr_blocked(pr, []), "engine-branch")

    def test_never_allowlist_c35(self):
        mod = load("auto_merge")
        os.environ.update(REPO="BloclabsHQ/fabricbloc-branch-policy")
        # main() early exit tested via import side effects avoided
        common = load("common")
        self.assertIn("BloclabsHQ/fabricbloc-branch-policy", common.FLOOR_NEVER_ALLOWLIST)


if __name__ == "__main__":
    unittest.main()
