#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from embedded_gate import (  # noqa: E402
    FLOOR_DENIED,
    GITHUB_ACTIONS_APP_ID,
    REPO,
    VERDICT_RE,
    agent_denied_paths_successful,
    all_paths_eligible_for_auto,
    body_without_code_fences,
    changed_paths_from_files,
    check_run_from_github_actions,
    classify_agent_path_tier,
    classify_review_routes,
    deterministic_auto_approve_eligible,
    issue_comment_edited,
    is_verdict_app_author,
    parse_verdict_markers_from_comments,
    path_eligible_for_auto_approve,
    path_is_safe_for_auto_approve,
    required_verdict_reviewers,
    try_reviewer_automation,
    verdict_approval_satisfied,
)

HEAD = "a" * 40
OLD = "b" * 40
CFG = json.loads((ROOT.parent / "rulesets" / "reviewers.json").read_text())
DENIED = list(FLOOR_DENIED)
MANIFEST_ARCH_DENIED = list(FLOOR_DENIED) + ["architecture/decisions/"]
CURSOR_ID = 199161495
CRIS_ID = 42707764
VERDICT_BOT = "fabricbloc-verdict[bot]"
VERDICT_BOT_ID = 337980250
CFG_VERDICT = CFG


def verdict_marker(reviewer, head, verdict="PASS"):
    return (
        f"<!-- fabricbloc-verdict v1 reviewer={reviewer} "
        f"verdict={verdict} head={head} -->"
    )


def comment(body, login="cursoragent", user_id=CURSOR_ID, edited=False):
    created = "2026-10-04T10:00:00Z"
    updated = "2026-10-04T10:05:00Z" if edited else created
    return {
        "body": body,
        "created_at": created,
        "updated_at": updated,
        "user": {"login": login, "id": user_id, "type": "User"},
    }


def eligible(paths):
    return all_paths_eligible_for_auto(paths, CFG, REPO, DENIED)


class TestTwoTierDeniedPaths(unittest.TestCase):
    def test_workflows_cris_only(self):
        self.assertEqual(
            classify_agent_path_tier(".github/workflows/ci.yml", DENIED), "cris_only")

    def test_approval_relay_cris_only(self):
        self.assertEqual(
            classify_agent_path_tier("agents/runtime/engine/approval_relay/handler.py", DENIED),
            "cris_only",
        )

    def test_gov_adr_cris_only(self):
        self.assertEqual(
            classify_agent_path_tier("architecture/decisions/GOV-0033-d1.md", DENIED),
            "cris_only",
        )

    def test_non_gov_adr_verdict_eligible(self):
        self.assertEqual(
            classify_agent_path_tier("architecture/decisions/ARCH-0045.md", DENIED),
            "verdict_eligible",
        )

    def test_non_gov_adr_verdict_eligible_manifest_arch_decisions_denied(self):
        self.assertEqual(
            classify_agent_path_tier("architecture/decisions/ARCH-0048.md", MANIFEST_ARCH_DENIED),
            "verdict_eligible",
        )

    def test_gov_adr_cris_only_manifest_arch_decisions_denied(self):
        self.assertEqual(
            classify_agent_path_tier("architecture/decisions/GOV-0033-d1.md", MANIFEST_ARCH_DENIED),
            "cris_only",
        )

    def test_nested_gov_adr_cris_only_manifest_arch_decisions_denied(self):
        self.assertEqual(
            classify_agent_path_tier(
                "architecture/decisions/subdir/GOV-0001.md", MANIFEST_ARCH_DENIED),
            "cris_only",
        )

    def test_engine_non_test_py_cris_only(self):
        self.assertEqual(
            classify_agent_path_tier("agents/runtime/engine/runner.py", DENIED),
            "cris_only",
        )

    def test_engine_test_py_verdict_eligible(self):
        self.assertEqual(
            classify_agent_path_tier("agents/runtime/engine/tests/test_runner.py", DENIED),
            "verdict_eligible",
        )

    def test_engine_readme_verdict_eligible(self):
        self.assertEqual(
            classify_agent_path_tier("agents/runtime/engine/README.md", DENIED),
            "verdict_eligible",
        )

    def test_engine_manifest_cris_only(self):
        self.assertEqual(
            classify_agent_path_tier(
                "agents/runtime/engine/policy/cursor-env/manifest.json", DENIED),
            "cris_only",
        )

    def test_rename_out_of_cris_only_stays_cris(self):
        self.assertEqual(
            classify_agent_path_tier(".github/workflows/old.yml", DENIED), "cris_only")


class TestReviewerRouting(unittest.TestCase):
    def test_verdict_regex(self):
        body = verdict_marker("sentinel", HEAD)
        m = VERDICT_RE.search(body)
        self.assertIsNotNone(m)
        self.assertEqual(m.group("reviewer"), "sentinel")
        self.assertEqual(m.group("verdict"), "PASS")

    def test_classify_fabricbloc_src_auth_sentinel(self):
        rev, cris, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc",
            {"src/auth/login.go"},
            CFG,
        )
        self.assertTrue(matched)
        self.assertEqual(rev, "sentinel")
        self.assertFalse(cris)
        self.assertTrue(sens)

    def test_classify_cris_beats_sentinel_on_secrets(self):
        rev, cris, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc",
            {"secrets/registry.yaml"},
            CFG,
        )
        self.assertTrue(matched)
        self.assertTrue(cris)
        self.assertEqual(rev, "madagentpm")

    def test_classify_iac_aether(self):
        rev, cris, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc",
            {"iac/modules/vpc/main.tf"},
            CFG,
        )
        self.assertEqual(rev, "aether")
        self.assertTrue(sens)

    def test_classify_warden_workflows(self):
        rev, _, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc",
            {".github/workflows/ci.yml"},
            CFG,
        )
        self.assertEqual(rev, "warden")
        self.assertTrue(matched)
        self.assertTrue(sens)

    def test_classify_default_docs_only(self):
        rev, cris, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc",
            {"docs/readme.md"},
            CFG,
        )
        self.assertFalse(matched)
        self.assertEqual(rev, "madagentpm")
        self.assertFalse(cris)
        self.assertFalse(sens)

    def test_classify_branch_policy_decisions_sentinel(self):
        rev, cris, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc-branch-policy",
            {"DECISIONS.md"},
            CFG,
        )
        self.assertTrue(matched)
        self.assertEqual(rev, "sentinel")
        self.assertTrue(sens)
        self.assertFalse(cris)

    def test_classify_branch_policy_risk_on_diff_sentinel(self):
        rev, _, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc-branch-policy",
            {"docs/risk-on-diff-not-repo.md"},
            CFG,
        )
        self.assertTrue(matched)
        self.assertEqual(rev, "sentinel")
        self.assertTrue(sens)

    def test_classify_decisions_plus_workflow_routes_warden(self):
        """policy-workflows (230) beats merge-authority-prose (225) when both match."""
        rev, _, sens, matched = classify_review_routes(
            "BloclabsHQ/fabricbloc-branch-policy",
            {"DECISIONS.md", ".github/workflows/agent-denied-paths.yml"},
            CFG,
        )
        self.assertTrue(matched)
        self.assertEqual(rev, "warden")
        self.assertTrue(sens)

    def test_classify_wallet_sentinel(self):
        rev, cris, _, matched = classify_review_routes(
            "BloclabsHQ/fabric-wallet",
            {"pkg/crypto/seal.go"},
            CFG,
        )
        self.assertTrue(matched)
        self.assertEqual(rev, "sentinel")
        self.assertFalse(cris)

    def test_verdict_app_identity_requires_login_and_id(self):
        self.assertTrue(
            is_verdict_app_author(
                {"login": VERDICT_BOT, "id": VERDICT_BOT_ID}, CFG_VERDICT)
        )
        self.assertFalse(
            is_verdict_app_author({"login": VERDICT_BOT, "id": 1}, CFG_VERDICT)
        )
        self.assertFalse(
            is_verdict_app_author({"login": "evil[bot]", "id": VERDICT_BOT_ID}, CFG_VERDICT)
        )
        self.assertFalse(
            is_verdict_app_author({"login": VERDICT_BOT, "id": 337980251}, CFG_VERDICT)
        )

    def test_pinned_verdict_app_id_satisfies_docs_only(self):
        paths = {"docs/readme.md"}
        comments = [
            comment(verdict_marker("madagentpm", HEAD), login=VERDICT_BOT, user_id=VERDICT_BOT_ID),
        ]
        import embedded_gate as eg

        orig = eg.agent_denied_paths_successful
        eg.agent_denied_paths_successful = lambda _h: True
        try:
            ok, reason = verdict_approval_satisfied(
                comments, HEAD, paths, CFG, set(), DENIED, "agent/session/feat/x-y")
        finally:
            eg.agent_denied_paths_successful = orig
        self.assertTrue(ok, reason)

    def test_user_id_zero_fail_closed(self):
        cfg = {**CFG_VERDICT, "verdict_app": {"login": VERDICT_BOT, "user_id": 0}}
        paths = {"architecture/decisions/ARCH-0045.md"}
        comments = [comment(verdict_marker("madagentpm", HEAD), login=VERDICT_BOT, user_id=0)]
        ok, reason = verdict_approval_satisfied(
            comments, HEAD, paths, cfg, set(), DENIED, "agent/session/feat/x-y")
        self.assertFalse(ok)
        self.assertIn("user_id", reason)

    def test_verdict_disabled_by_canon_flag(self):
        cfg = {**CFG_VERDICT, "verdict_approval_enabled": False}
        comments = [comment(verdict_marker("madagentpm", HEAD), login=VERDICT_BOT, user_id=VERDICT_BOT_ID)]
        markers = parse_verdict_markers_from_comments(comments, HEAD, set(), cfg)
        self.assertEqual(markers, {})

    def test_fenced_marker_ignored(self):
        inner = verdict_marker("madagentpm", HEAD)
        body = f"```html\n{inner}\n```"
        comments = [comment(body, login=VERDICT_BOT, user_id=VERDICT_BOT_ID)]
        markers = parse_verdict_markers_from_comments(comments, HEAD, set(), CFG_VERDICT)
        self.assertEqual(markers, {})

    def test_edited_comment_ignored(self):
        comments = [
            comment(
                verdict_marker("madagentpm", HEAD),
                login=VERDICT_BOT,
                user_id=VERDICT_BOT_ID,
                edited=True,
            )
        ]
        markers = parse_verdict_markers_from_comments(comments, HEAD, set(), CFG_VERDICT)
        self.assertEqual(markers, {})

    def test_wrong_app_id_rejected(self):
        comments = [comment(verdict_marker("madagentpm", HEAD), login=VERDICT_BOT, user_id=1)]
        markers = parse_verdict_markers_from_comments(comments, HEAD, set(), CFG_VERDICT)
        self.assertEqual(markers, {})

    def test_stale_head_rejected(self):
        comments = [comment(verdict_marker("madagentpm", OLD), login=VERDICT_BOT, user_id=VERDICT_BOT_ID)]
        markers = parse_verdict_markers_from_comments(comments, HEAD, set(), CFG_VERDICT)
        self.assertEqual(markers, {})

    def test_fail_verdict_blocks_approval(self):
        paths = {"architecture/decisions/ARCH-0045.md"}
        comments = [
            comment(verdict_marker("madagentpm", HEAD), login=VERDICT_BOT, user_id=VERDICT_BOT_ID),
            comment(verdict_marker("aether", HEAD, "FAIL"), login=VERDICT_BOT, user_id=VERDICT_BOT_ID),
        ]
        import embedded_gate as eg

        orig = eg.agent_denied_paths_successful
        eg.agent_denied_paths_successful = lambda _h: True
        try:
            ok, reason = verdict_approval_satisfied(
                comments, HEAD, paths, CFG_VERDICT, set(), DENIED, "agent/session/feat/x-y")
        finally:
            eg.agent_denied_paths_successful = orig
        self.assertFalse(ok)
        self.assertIn("aether", reason)

    def test_valid_verdict_all_required(self):
        paths = {"architecture/decisions/ARCH-0045.md"}
        comments = [
            comment(verdict_marker("madagentpm", HEAD), login=VERDICT_BOT, user_id=VERDICT_BOT_ID),
            comment(verdict_marker("aether", HEAD), login=VERDICT_BOT, user_id=VERDICT_BOT_ID),
        ]
        import embedded_gate as eg

        orig = eg.agent_denied_paths_successful
        eg.agent_denied_paths_successful = lambda _h: True
        try:
            ok, reason = verdict_approval_satisfied(
                comments, HEAD, paths, CFG_VERDICT, set(), DENIED, "agent/session/feat/x-y")
        finally:
            eg.agent_denied_paths_successful = orig
        self.assertTrue(ok, reason)

    def test_missing_madagentpm_blocks(self):
        paths = {"architecture/decisions/ARCH-0045.md"}
        comments = [comment(verdict_marker("aether", HEAD), login=VERDICT_BOT, user_id=VERDICT_BOT_ID)]
        import embedded_gate as eg

        orig = eg.agent_denied_paths_successful
        eg.agent_denied_paths_successful = lambda _h: True
        try:
            ok, _ = verdict_approval_satisfied(
                comments, HEAD, paths, CFG_VERDICT, set(), DENIED, "agent/session/feat/x-y")
        finally:
            eg.agent_denied_paths_successful = orig
        self.assertFalse(ok)

    def test_non_required_fail_blocks_docs_only_probe_r22(self):
        """R22: madagentpm PASS + warden FAIL on docs-only must not satisfy verdict approval."""
        paths = {"docs/readme.md"}
        comments = [
            comment(verdict_marker("madagentpm", HEAD), login=VERDICT_BOT, user_id=VERDICT_BOT_ID),
            comment(verdict_marker("warden", HEAD, "FAIL"), login=VERDICT_BOT, user_id=VERDICT_BOT_ID),
        ]
        import embedded_gate as eg

        orig = eg.agent_denied_paths_successful
        eg.agent_denied_paths_successful = lambda _h: True
        try:
            ok, reason = verdict_approval_satisfied(
                comments, HEAD, paths, CFG_VERDICT, set(), DENIED, "agent/session/feat/x-y")
        finally:
            eg.agent_denied_paths_successful = orig
        self.assertFalse(ok)
        self.assertIn("warden", reason)
        self.assertIn("FAIL", reason)

    def test_same_slug_newer_pass_overrides_older_fail(self):
        paths = {"docs/readme.md"}
        comments = [
            comment(verdict_marker("madagentpm", HEAD, "FAIL"), login=VERDICT_BOT, user_id=VERDICT_BOT_ID),
            comment(verdict_marker("madagentpm", HEAD), login=VERDICT_BOT, user_id=VERDICT_BOT_ID),
        ]
        import embedded_gate as eg

        orig = eg.agent_denied_paths_successful
        eg.agent_denied_paths_successful = lambda _h: True
        try:
            ok, reason = verdict_approval_satisfied(
                comments, HEAD, paths, CFG_VERDICT, set(), DENIED, "agent/session/feat/x-y")
        finally:
            eg.agent_denied_paths_successful = orig
        self.assertTrue(ok, reason)

    def test_body_without_code_fences(self):
        inner = verdict_marker("x", HEAD)
        self.assertNotIn("fabricbloc-verdict", body_without_code_fences(f"```\n{inner}\n```"))

    def test_issue_comment_edited(self):
        self.assertFalse(issue_comment_edited({"created_at": "a", "updated_at": "a"}))
        self.assertTrue(issue_comment_edited({"created_at": "a", "updated_at": "b"}))

    def test_missing_app_token_skips_without_exception(self):
        posts = []

        def fake_post(number, body, token=None):
            posts.append(body)

        import embedded_gate as eg

        orig = eg.post_issue_comment
        orig_denied = eg.agent_denied_paths_successful
        orig_page = eg.paginate
        eg.post_issue_comment = fake_post
        eg.agent_denied_paths_successful = lambda _head: False
        eg.paginate = lambda *a, **k: []
        try:
            ok = try_reviewer_automation(
                7, HEAD, {"docs/x.md"}, CFG, {"cursoragent"}, DENIED, "agent/session/feat/x-y")
        finally:
            eg.post_issue_comment = orig
            eg.agent_denied_paths_successful = orig_denied
            eg.paginate = orig_page
        self.assertFalse(ok)
        self.assertTrue(any("needs-review" in p for p in posts))


class TestDeterministicAutoApproveAllowlist(unittest.TestCase):
    def test_changed_paths_includes_previous_filename(self):
        files = [{"filename": "docs/x.md", "previous_filename": "src/auth/y.go"}]
        self.assertEqual(
            changed_paths_from_files(files),
            {"docs/x.md", "src/auth/y.go"},
        )

    def test_rename_out_of_sensitive_dir_blocks_auto(self):
        paths = {"docs/relocated.md", "src/auth/legacy.go"}
        self.assertFalse(eligible(paths))

    def test_case_variant_sensitive_path_denied(self):
        self.assertFalse(eligible({"Src/Auth/handler.go"}))

    def test_unlisted_path_makefile_denied(self):
        self.assertFalse(eligible({"Makefile"}))

    def test_allowlisted_docs_only_passes(self):
        self.assertTrue(eligible({"docs/guide.md"}))

    def test_svg_extension_denied_for_auto_approve(self):
        self.assertFalse(eligible({"docs/diagram.svg"}))

    def test_html_extension_denied_for_auto_approve(self):
        self.assertFalse(eligible({"docs/page.html"}))

    def test_htm_extension_denied_for_auto_approve(self):
        self.assertFalse(eligible({"docs/page.htm"}))

    def test_reviewers_json_has_no_dead_allowlist_globs(self):
        self.assertNotIn("deterministic_auto_approve_allowlist", CFG)

    def test_review_route_blocks_even_if_under_docs(self):
        self.assertFalse(eligible({"docs/a.md", "iac/module/main.tf"}))

    def test_denied_path_floor_blocks_engine(self):
        self.assertFalse(eligible({"agents/runtime/engine/config.yaml"}))

    def test_test_code_not_allowlisted(self):
        self.assertFalse(eligible({"agent-gates/test_reviewer_routing.py"}))

    def test_fixture_data_allowlisted(self):
        self.assertTrue(eligible({"pkg/foo/testdata/input.json"}))

    def test_runnable_under_docs_denied(self):
        self.assertFalse(eligible({"docs/conf.py"}))
        self.assertFalse(eligible({"docs/setup/script.sh"}))

    def test_runnable_package_json_under_fixtures_denied(self):
        self.assertFalse(eligible({"pkg/fixtures/package.json"}))

    def test_exclusion_docs_gov_single_file(self):
        self.assertFalse(path_eligible_for_auto_approve(
            "docs/GOV-0033.md", CFG, REPO, DENIED))

    def test_exclusion_docs_decisions(self):
        self.assertFalse(path_eligible_for_auto_approve(
            "docs/decisions/0001-record.md", CFG, REPO, DENIED))

    def test_unsafe_path_dotdot_denied(self):
        self.assertFalse(path_is_safe_for_auto_approve("docs/../secrets/x.md"))

    def test_unsafe_path_leading_slash_denied(self):
        self.assertFalse(path_is_safe_for_auto_approve("/docs/x.md"))

    def test_unsafe_path_leading_dot_slash_denied(self):
        self.assertFalse(path_is_safe_for_auto_approve("./docs/x.md"))

    def test_unsafe_path_backslash_denied(self):
        self.assertFalse(path_is_safe_for_auto_approve("docs\\x.md"))

    def test_unsafe_path_nul_denied(self):
        self.assertFalse(path_is_safe_for_auto_approve("docs/x\0.md"))

    def test_sensitive_class_secrets(self):
        self.assertFalse(eligible({"secrets/registry.yaml"}))

    def test_sensitive_class_pem_key(self):
        self.assertFalse(eligible({"certs/server.pem"}))

    def test_sensitive_class_dot_env(self):
        self.assertFalse(eligible({".env.production"}))

    def test_sensitive_class_terraform_tf(self):
        self.assertFalse(eligible({"terraform/main.tf"}))

    def test_sensitive_class_k8s(self):
        self.assertFalse(eligible({"k8s/deployment.yaml"}))

    def test_sensitive_class_helm(self):
        self.assertFalse(eligible({"helm/chart/values.yaml"}))

    def test_sensitive_class_charts(self):
        self.assertFalse(eligible({"charts/app/Chart.yaml"}))

    def test_sensitive_class_dockerfile(self):
        self.assertFalse(eligible({"Dockerfile.prod"}))

    def test_sensitive_class_docker_compose(self):
        self.assertFalse(eligible({"docker-compose.yml"}))

    def test_sensitive_class_migrations(self):
        self.assertFalse(eligible({"db/migrations/001.sql"}))

    def test_sensitive_class_auth_path_segment(self):
        self.assertFalse(eligible({"pkg/wallet/auth/util.go"}))

    def test_exclusion_github(self):
        self.assertFalse(path_eligible_for_auto_approve(
            ".github/workflows/ci.yml", CFG, REPO, DENIED))

    def test_exclusion_cursor(self):
        self.assertFalse(path_eligible_for_auto_approve(
            ".cursor/rules.json", CFG, REPO, DENIED))

    def test_exclusion_claude(self):
        self.assertFalse(path_eligible_for_auto_approve(
            ".claude/settings.json", CFG, REPO, DENIED))

    def test_exclusion_codex(self):
        self.assertFalse(path_eligible_for_auto_approve(
            ".codex/config.toml", CFG, REPO, DENIED))

    def test_exclusion_agents_md(self):
        self.assertFalse(path_eligible_for_auto_approve(
            "docs/AGENTS.md", CFG, REPO, DENIED))

    def test_exclusion_claude_md(self):
        self.assertFalse(path_eligible_for_auto_approve(
            "CLAUDE.md", CFG, REPO, DENIED))

    def test_exclusion_cursorrules(self):
        self.assertFalse(path_eligible_for_auto_approve(
            "apps/.cursorrules", CFG, REPO, DENIED))

    def test_exclusion_skill_md(self):
        self.assertFalse(path_eligible_for_auto_approve(
            ".cursor/skills/foo/SKILL.md", CFG, REPO, DENIED))

    def test_exclusion_codeowners(self):
        self.assertFalse(path_eligible_for_auto_approve(
            "CODEOWNERS", CFG, REPO, DENIED))

    def test_exclusion_canon(self):
        self.assertFalse(path_eligible_for_auto_approve(
            "canon/policies.yaml", CFG, REPO, DENIED))

    def test_exclusion_rulesets(self):
        self.assertFalse(path_eligible_for_auto_approve(
            "rulesets/reviewers.json", CFG, REPO, DENIED))

    def test_exclusion_docs_adr(self):
        self.assertFalse(path_eligible_for_auto_approve(
            "docs/adr/0001-record.md", CFG, REPO, DENIED))

    def test_exclusion_docs_gov(self):
        self.assertFalse(path_eligible_for_auto_approve(
            "docs/gov-0033/policy.md", CFG, REPO, DENIED))

    def test_exclusion_security_md(self):
        self.assertFalse(path_eligible_for_auto_approve(
            "SECURITY.md", CFG, REPO, DENIED))

    def test_deterministic_eligible_requires_allowlist_and_denied_paths(self):
        import embedded_gate as eg

        paths = {"docs/only.md"}
        orig = eg.agent_denied_paths_successful
        eg.agent_denied_paths_successful = lambda _h: True
        try:
            self.assertTrue(
                deterministic_auto_approve_eligible(paths, CFG, HEAD, DENIED))
            eg.agent_denied_paths_successful = lambda _h: False
            self.assertFalse(
                deterministic_auto_approve_eligible(paths, CFG, HEAD, DENIED))
        finally:
            eg.agent_denied_paths_successful = orig


class TestAgentDeniedPathsCheck(unittest.TestCase):
    def _run_check_runs(self, eg, check_runs):
        class FakeResp:
            def read(self):
                return json.dumps({"check_runs": check_runs}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout=30):
            return FakeResp()

        orig_repo, orig_token = eg.REPO, eg.TOKEN
        eg.REPO = "BloclabsHQ/fabricbloc"
        eg.TOKEN = "test"
        orig_open = eg.urllib.request.urlopen
        eg.urllib.request.urlopen = fake_urlopen
        try:
            return agent_denied_paths_successful(HEAD)
        finally:
            eg.urllib.request.urlopen = orig_open
            eg.REPO, eg.TOKEN = orig_repo, orig_token

    def test_check_run_from_github_actions(self):
        ga = {"id": GITHUB_ACTIONS_APP_ID, "slug": "github-actions"}
        self.assertTrue(check_run_from_github_actions({"app": ga}))
        self.assertFalse(check_run_from_github_actions({"app": {"id": 1, "slug": "evil"}}))
        self.assertFalse(check_run_from_github_actions({
            "app": {"id": 999, "slug": "github-actions"},
        }))

    def test_agent_denied_paths_successful_reads_conclusion(self):
        import embedded_gate as eg

        ok = self._run_check_runs(eg, [{
            "name": "agent-denied-paths",
            "status": "completed",
            "conclusion": "success",
            "app": {"id": GITHUB_ACTIONS_APP_ID, "slug": "github-actions"},
            "started_at": "2026-10-05T12:00:00Z",
            "id": 1,
        }])
        self.assertTrue(ok)

    def test_github_actions_slug_without_app_id_15368_ignored(self):
        import embedded_gate as eg

        ok = self._run_check_runs(eg, [{
            "name": "agent-denied-paths",
            "status": "completed",
            "conclusion": "success",
            "app": {"id": 1, "slug": "github-actions"},
            "started_at": "2026-10-05T12:00:00Z",
            "id": 1,
        }])
        self.assertFalse(ok)

    def test_fake_app_success_ignored(self):
        import embedded_gate as eg

        ok = self._run_check_runs(eg, [{
            "name": "agent-denied-paths",
            "status": "completed",
            "conclusion": "success",
            "app": {"id": 999, "slug": "fake-bot"},
            "started_at": "2026-10-05T12:00:00Z",
            "id": 1,
        }])
        self.assertFalse(ok)

    def test_stale_fake_success_newer_github_actions_failure(self):
        import embedded_gate as eg

        ok = self._run_check_runs(eg, [
            {
                "name": "agent-denied-paths",
                "status": "completed",
                "conclusion": "success",
                "app": {"id": 999, "slug": "fake-bot"},
                "started_at": "2026-10-05T11:00:00Z",
                "id": 1,
            },
            {
                "name": "agent-denied-paths",
                "status": "completed",
                "conclusion": "failure",
                "app": {"id": GITHUB_ACTIONS_APP_ID, "slug": "github-actions"},
                "started_at": "2026-10-05T12:00:00Z",
                "id": 2,
            },
        ])
        self.assertFalse(ok)

    def test_mode_empty_string_fails_closed(self):
        import os
        import subprocess

        env = {k: v for k, v in os.environ.items() if k != "MODE"}
        env.update({
            "MODE": "",
            "GH_TOKEN": "test",
            "REPO": "BloclabsHQ/fabricbloc",
            "PR": "7",
            "EVENT_HEAD_SHA": HEAD,
            "REPO_DEFAULT_BRANCH": "main",
            "API": "http://127.0.0.1:9",
        })
        p = subprocess.run(
            [sys.executable, str(ROOT / "embedded_gate.py")],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(p.returncode, 1)
        self.assertIn("MODE is unset", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
