#!/usr/bin/env python3
import importlib.util
import os
import sys
import unittest
from pathlib import Path

HYGIENE = Path(__file__).resolve().parent

SAMPLE_TEMPLATE = """
| R1 | Assignee | ...
| D1 | Spec path | ...
| D2 | Tracking | ...
"""


def load(name):
    spec = importlib.util.spec_from_file_location(name, HYGIENE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestBacklogLint(unittest.TestCase):
    def test_row_ids_from_table_c64(self):
        load("common")
        mod = load("backlog_lint")
        rows = mod.row_ids_from_template(SAMPLE_TEMPLATE)
        self.assertIn("R1", rows)
        self.assertIn("D1", rows)
        self.assertIn("D2", rows)

    def test_template_gate_inert(self):
        mod = load("backlog_lint")
        os.environ.pop("TEMPLATE_GATE_READY", None)
        os.environ["HYGIENE_MODE"] = "live"
        self.assertTrue(mod.inert_run())
        os.environ["TEMPLATE_GATE_READY"] = "true"
        self.assertFalse(mod.inert_run())
        os.environ["HYGIENE_MODE"] = "dry-run"
        self.assertTrue(mod.inert_run())

    def test_lifecycle_w3(self):
        mod = load("backlog_lint")
        life = mod.lifecycle_labels([{"name": "in-progress"}, {"name": "spec:ready"}])
        self.assertEqual(len(life), 2)


if __name__ == "__main__":
    unittest.main()
