#!/usr/bin/env python3
"""Tests for MR-11 env_drift (ROLLOUT-ADDENDUM R4)."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import unittest
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "environments"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


ed = load_module("env_drift", ROOT / "env_drift.py")
MANIFEST = json.loads((ROOT / "manifest.json").read_text())
POLICY = ed.policy_from_manifest(MANIFEST)


def fx(name: str):
    return json.loads((FIX / name).read_text())


def run_pure(envs: str, bp: str | None = "branch-policies.main.json"):
    return ed.evaluate(fx(envs), {"agent-ops": fx(bp)} if bp else {}, POLICY)


def drift(findings):
    return [f for f in findings if f["severity"] == "drift"]


def text(findings) -> str:
    return "\n".join(f["detail"] for f in findings)


class PureTests(unittest.TestCase):
    def test_manifest_policy_matches_default(self) -> None:
        self.assertEqual(
            {k: v for k, v in MANIFEST["environments"].items() if not k.startswith("_")},
            ed.DEFAULT_POLICY,
        )

    def test_clean_target_state(self) -> None:
        self.assertEqual(run_pure("environments.clean.json"), [])

    def test_current_state_agent_ops_bypass_true(self) -> None:
        out = run_pure("environments.agent-ops-bypass-true.json")
        self.assertEqual(len(drift(out)), 1)
        self.assertIn("agent-ops: can_admins_bypass = true, expected false", text(out))

    def test_any_environment_with_bypass_is_flagged(self) -> None:
        out = run_pure("environments.other-env-bypass-true.json")
        self.assertIn("dev: can_admins_bypass = true", text(out))

    def test_bypass_not_reported_is_unverified_not_drift(self) -> None:
        out = run_pure("environments.bypass-absent.json")
        self.assertEqual(drift(out), [])
        self.assertIn("did not report can_admins_bypass", text(out))

    def test_legacy_policy_without_type_counts_as_branch(self) -> None:
        self.assertEqual(run_pure("environments.clean.json", "branch-policies.main-legacy-no-type.json"), [])

    def test_extra_branch_rule(self) -> None:
        out = run_pure("environments.clean.json", "branch-policies.main-and-dev.json")
        self.assertIn('extra [{"name": "dev", "type": "branch"}]', text(out))

    def test_wildcard_rule(self) -> None:
        out = run_pure("environments.clean.json", "branch-policies.wildcard.json")
        self.assertIn("main*", text(out))

    def test_tag_rule_named_main(self) -> None:
        out = run_pure("environments.clean.json", "branch-policies.tag-main.json")
        self.assertIn('"type": "tag"', text(out))

    def test_no_rules_under_custom(self) -> None:
        out = run_pure("environments.clean.json", "branch-policies.empty.json")
        self.assertIn("must be exactly", text(out))

    def test_protected_branches_mode(self) -> None:
        out = run_pure("environments.agent-ops-protected-branches.json", None)
        self.assertIn('"protected_branches": true', text(out))

    def test_null_policy_means_any_ref(self) -> None:
        out = run_pure("environments.agent-ops-any-branch.json", None)
        self.assertIn("deployment_branch_policy is null", text(out))

    def test_missing_agent_ops(self) -> None:
        out = run_pure("environments.no-agent-ops.json", None)
        self.assertIn("agent-ops: environment not found", text(out))

    def test_branch_policies_not_fetched_is_unverified(self) -> None:
        out = run_pure("environments.clean.json", None)
        self.assertEqual(drift(out), [])
        self.assertIn("not fetched", text(out))

    def test_reviewers_without_prevent_self_review(self) -> None:
        out = run_pure("environments.agent-ops-reviewers-self-review.json")
        self.assertIn("without prevent_self_review", text(out))

    def test_malformed_payload(self) -> None:
        self.assertEqual(len(drift(ed.evaluate([], {}, POLICY))), 1)

    def test_environments_total_count_mismatch_is_unverified(self) -> None:
        payload = {"total_count": 99, "environments": fx("environments.clean.json")["environments"]}
        out = ed.evaluate(payload, {"agent-ops": fx("branch-policies.main.json")}, POLICY)
        self.assertEqual(drift(out), [])
        self.assertIn("total_count 99", text(out))

    def test_report_fingerprint_present_on_drift(self) -> None:
        out = run_pure("environments.agent-ops-bypass-true.json")
        code, rep = ed.report(out, strict=False)
        self.assertEqual(code, 1)
        assert rep is not None
        self.assertEqual(len(rep["fingerprint"]), 16)


class FakeAPI:
    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str]):
        self.calls.append(url)
        for prefix, value in sorted(self.routes.items(), key=lambda kv: -len(kv[0])):
            if url.startswith(prefix):
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected URL {url}")


GH = ed.GITHUB_API
ENVS = f"{GH}/repos/BloclabsHQ/fabricbloc/environments?"
BPS = f"{GH}/repos/BloclabsHQ/fabricbloc/environments/agent-ops/deployment-branch-policies?"


class LiveAndCliTests(unittest.TestCase):
    def test_live_clean(self) -> None:
        api = FakeAPI({ENVS: fx("environments.clean.json"), BPS: fx("branch-policies.main.json")})
        self.assertEqual(ed.live_findings(api, "t", POLICY), [])
        self.assertTrue(all("per_page=100" in c for c in api.calls))

    def test_live_current_state(self) -> None:
        api = FakeAPI({ENVS: fx("environments.agent-ops-bypass-true.json"), BPS: fx("branch-policies.main.json")})
        self.assertIn("can_admins_bypass = true", text(ed.live_findings(api, "t", POLICY)))

    def test_live_no_token_and_403_are_unverified(self) -> None:
        self.assertEqual(drift(ed.live_findings(FakeAPI({}), None, POLICY)), [])
        err = urllib.error.HTTPError(ENVS, 403, "Forbidden", {}, None)
        self.assertEqual(drift(ed.live_findings(FakeAPI({ENVS: err}), "t", POLICY)), [])

    def test_cli_offline_exit_codes(self) -> None:
        bp = f"agent-ops={FIX / 'branch-policies.main.json'}"
        code, rep = ed.run(["--environments-json", str(FIX / "environments.clean.json"), "--branch-policies", bp])
        self.assertEqual((code, rep), (0, None))
        code, rep = ed.run(
            ["--environments-json", str(FIX / "environments.agent-ops-bypass-true.json"), "--branch-policies", bp]
        )
        self.assertEqual(code, 1)
        self.assertEqual(rep["policy"], "environments")
        code, _ = ed.run(["--environments-json", str(FIX / "environments.clean.json")])
        self.assertEqual(code, 0)
        code, _ = ed.run(["--environments-json", str(FIX / "environments.clean.json"), "--strict-live"])
        self.assertEqual(code, 1)
        with contextlib.redirect_stderr(io.StringIO()):
            code, _ = ed.run(["--environments-json", str(FIX / "does-not-exist.json")])
        self.assertEqual(code, 2)

    def test_token_never_in_report(self) -> None:
        api = FakeAPI({ENVS: fx("environments.agent-ops-bypass-true.json"), BPS: fx("branch-policies.wildcard.json")})
        code, rep = ed.run(["--live"], fetch=api, env={"GH_AUDIT_TOKEN": "SECRET-SENTINEL-9"})
        self.assertEqual(code, 1)
        self.assertNotIn("SECRET-SENTINEL-9", json.dumps(rep))


if __name__ == "__main__":
    unittest.main(verbosity=1)
