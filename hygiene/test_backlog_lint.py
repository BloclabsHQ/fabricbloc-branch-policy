#!/usr/bin/env python3
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


SAMPLE_TEMPLATE = """
- [PASS] R1
- [PASS] R2
- [PASS] W3
- [PASS] D1 docs/specs/2026-10-04-sample.md
- [PASS] D2
"""


class TestBacklogLint(unittest.TestCase):
    def test_row_ids_from_template_c64(self):
        load("common")
        mod = load("backlog_lint")
        rows = mod.row_ids_from_template(SAMPLE_TEMPLATE)
        self.assertIn("R1", rows)
        self.assertIn("D1", rows)

    def test_lifecycle_w3(self):
        mod = load("backlog_lint")
        life = mod.lifecycle_labels([{"name": "in-progress"}, {"name": "spec:ready"}])
        self.assertEqual(len(life), 2)
        life2 = mod.lifecycle_labels([{"name": "in-progress"}, {"name": "blocked"}])
        self.assertEqual(len(life2), 1)


if __name__ == "__main__":
    unittest.main()
