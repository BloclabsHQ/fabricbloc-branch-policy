#!/usr/bin/env python3
"""Hygiene contract: embed sync, permissions lint, canon pin."""
import re
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
HYGIENE = Path(__file__).resolve().parent

HYGIENE_WORKFLOWS = (
    "hygiene-pr-ops-notify",
    "hygiene-stale",
    "hygiene-auto-merge",
    "hygiene-ci-red",
    "hygiene-branch-prune",
    "hygiene-backlog-lint",
)


def workflow_on(doc):
    # PyYAML 1.1 treats bare `on` as boolean True.
    return doc.get("on") or doc.get(True) or {}


def embedded(stem):
    path = WF / f"{stem}.yml"
    if not path.exists():
        return None
    doc = yaml.safe_load(path.read_text())
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            run = step.get("run") or ""
            if "<<'PY'" in run:
                start = run.index("<<'PY'\n") + len("<<'PY'\n")
                return run[start : run.rindex("\nPY")]
    return None


def expected_embed(script_name):
    proc = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, '{HYGIENE}'); from sync_embedded_hygiene import embed_body; print(embed_body('{script_name}'), end='')"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return proc.stdout


class TestHygieneContract(unittest.TestCase):
    def test_pr_ops_embed_synced(self):
        body = embedded("hygiene-pr-ops-notify")
        self.assertIsNotNone(body)
        self.assertEqual(body.rstrip("\n"), expected_embed("pr_ops_notify").rstrip("\n"))

    def test_branch_prune_embed_synced(self):
        body = embedded("hygiene-branch-prune")
        self.assertIsNotNone(body)
        self.assertEqual(body.rstrip("\n"), expected_embed("branch_prune").rstrip("\n"))

    def test_ci_red_embed_synced(self):
        body = embedded("hygiene-ci-red")
        self.assertIsNotNone(body)
        self.assertEqual(body.rstrip("\n"), expected_embed("ci_red").rstrip("\n"))

    def test_top_level_permissions_empty(self):
        for stem in HYGIENE_WORKFLOWS:
            path = WF / f"{stem}.yml"
            if not path.exists():
                continue
            doc = yaml.safe_load(path.read_text())
            with self.subTest(stem=stem):
                self.assertEqual(doc.get("permissions"), {})

    def test_workflow_call_present(self):
        doc = yaml.safe_load((WF / "hygiene-pr-ops-notify.yml").read_text())
        self.assertIn("workflow_call", workflow_on(doc))

    def test_c1_schedule_reaches_sweep_without_plan(self):
        doc = yaml.safe_load((WF / "hygiene-pr-ops-notify.yml").read_text())
        jobs = doc.get("jobs") or {}
        self.assertIn("sweep", jobs)
        sweep = jobs["sweep"]
        self.assertNotIn("needs", sweep)
        cond = sweep.get("if") or ""
        self.assertIn("github.event_name == 'schedule'", cond.replace("\n", " "))
        self.assertIn("inputs.sweep", cond)
        notify = jobs.get("notify") or {}
        needs = notify.get("needs")
        if isinstance(needs, str):
            needs = [needs]
        self.assertEqual(needs, ["plan"])

    # --- C6 backlog-lint ---


    def test_backlog_lint_embed_synced(self):
        body = embedded("hygiene-backlog-lint")
        self.assertIsNotNone(body)
        self.assertEqual(body.rstrip("\n"), expected_embed("backlog_lint").rstrip("\n"))

    def test_canon_hygiene_sha_when_present(self):
        import json

        canon = json.loads((ROOT / "rulesets/canon.json").read_text())
        pins = canon.get("pins") or {}
        if "hygiene_sha" in pins:
            sha = pins["hygiene_sha"]
            self.assertRegex(sha, r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
