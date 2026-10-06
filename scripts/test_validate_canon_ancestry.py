"""Exercise pin ancestry with the detached checkout layout used by Actions."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_canon", ROOT / "agent-gates" / "validate_canon.py"
)
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class PinAncestryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, GIT_AUTHOR_NAME="Fixture",
                        GIT_AUTHOR_EMAIL="fixture@example.invalid",
                        GIT_COMMITTER_NAME="Fixture",
                        GIT_COMMITTER_EMAIL="fixture@example.invalid")
        self.git("init", "--quiet")
        tree = self.git("write-tree")
        self.pin = self.git("commit-tree", tree, input="published pin\n")
        main = self.git("commit-tree", tree, "-p", self.pin, input="main\n")
        self.topic = self.git("commit-tree", tree, "-p", main, input="PR only\n")
        self.git("update-ref", "refs/remotes/origin/main", main)
        self.git("update-ref", "--no-deref", "HEAD", self.topic)

    def git(self, *args, input=None):
        return subprocess.run(
            ["git", *args], cwd=self.root, env=self.env, input=input,
            text=True, capture_output=True, check=True,
        ).stdout.strip()

    def errors(self, pin):
        return VALIDATOR.agent_gates_pin_ancestor_errors(
            {"pins": {"agent_gates_sha": pin}}, self.root
        )

    def test_detached_checkout_accepts_published_pin_without_local_main(self):
        self.assertEqual(self.errors(self.pin), [])

    def test_pr_only_pin_is_rejected_even_when_it_is_head(self):
        self.assertTrue(self.errors(self.topic))

    def test_missing_history_reports_unverifiable_instead_of_nonancestor(self):
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        self.assertIn("cannot verify", " ".join(self.errors(self.pin)))

    def test_contract_checkout_fetches_history_for_ancestry(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/agent-gates-contract.yml").read_text()
        )
        checkout = workflow["jobs"]["contract"]["steps"][0]
        self.assertEqual(checkout["with"].get("fetch-depth"), 0)


if __name__ == "__main__":
    unittest.main()
