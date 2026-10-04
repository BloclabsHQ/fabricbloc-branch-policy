#!/usr/bin/env python3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_policy_index.py"


class ValidatePolicyIndexTest(unittest.TestCase):
    def test_bad_row_too_few_columns_fails(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(
                "| ID | Domain | Rule | Enforcer | Test |\n"
                "| CU-99 | 04-cursor | broken row missing test column |\n"
            )
            path = f.name
        r = subprocess.run([sys.executable, str(SCRIPT), path], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CU-99", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
