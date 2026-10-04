#!/usr/bin/env python3
"""Contract tests for the F6 pinned gates. Run: python3 agent-gates/test.py

Extracts the embedded gate script from both workflow files (they must be
byte-identical), then runs it against a local fake GitHub API. No network.
Includes the F6 malicious case: an agent PR that rewrites the gate to exit 0.
"""
import json, os, subprocess, sys, threading, unittest, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml  # pyyaml, same pin as fabricbloc canon-check

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
GATES = ("agent-denied-paths", "agent-review-of-record")
REQUIRED_GATE_WORKFLOWS = GATES
# GitHub-hosted runner labels (no self-hosted). Required org gates pin to ubuntu-latest only.
GITHUB_HOSTED_RUNNER_LABELS = frozenset({
    "ubuntu-latest", "ubuntu-24.04", "ubuntu-22.04", "ubuntu-20.04",
    "windows-latest", "windows-2025", "windows-2022", "windows-11-arm",
    "macos-latest", "macos-15", "macos-14", "macos-13",
})
HEAD, BASE, OLD = "h" * 40, "b" * 40, "o" * 40


def assert_required_gate_hosted_only():
    """Required org workflows must use a fixed GitHub-hosted label (ubuntu-latest)."""
    for name in REQUIRED_GATE_WORKFLOWS:
        doc = yaml.safe_load((WF / f"{name}.yml").read_text())

        def bad_runner(value, where):
            if value is None:
                return
            if isinstance(value, str):
                low = value.lower()
                if "self-hosted" in low or "${{" in value:
                    raise AssertionError(f"{name} {where}: disallowed runs-on {value!r}")
                if value.strip() != "ubuntu-latest":
                    raise AssertionError(
                        f"{name} {where}: runs-on must be ubuntu-latest (got {value!r})")
                if value not in GITHUB_HOSTED_RUNNER_LABELS:
                    raise AssertionError(f"{name} {where}: not a known GitHub-hosted label")
                return
            if isinstance(value, list):
                for label in value:
                    if isinstance(label, str) and "self-hosted" in label.lower():
                        raise AssertionError(f"{name} {where}: self-hosted label {label!r}")
                raise AssertionError(f"{name} {where}: runs-on must be ubuntu-latest, not a label list")
            raise AssertionError(
                f"{name} {where}: runs-on must be the literal string ubuntu-latest (got {value!r})")

        for job_id, job in (doc.get("jobs") or {}).items():
            bad_runner(job.get("runs-on"), f"job {job_id}")
            strategy = job.get("strategy") or {}
            for dim, choices in (strategy.get("matrix") or {}).items():
                if dim == "runs-on" or "runner" in dim.lower():
                    raise AssertionError(f"{name} job {job_id}: matrix must not select runners ({dim})")


def embedded(name):
    doc = yaml.safe_load((WF / f"{name}.yml").read_text())
    run = doc["jobs"][name]["steps"][0]["run"]
    start = run.index("<<'PY'\n") + len("<<'PY'\n")
    return run[start:run.rindex("\nPY")]


MANIFEST = {"operators": {"members_expected": ["Madgeniusblink"]},
            "denied_paths": {"arch_0048_baseline": [".github/workflows/", "decisions/"],
                             "proposed_additions": [".cursor/"]}}


class Fake:
    routes = {}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        key = u.path
        if key.endswith("/contents/" + urllib.parse.quote("agents/runtime/engine/policy/cursor-env/manifest.json")) or "manifest.json" in key:
            key = "manifest"
        elif "config.yaml" in key:
            key = "config"
        val = Fake.routes.get(key)
        if isinstance(val, int):
            self.send_response(val); self.end_headers(); return
        if val is None:
            self.send_response(404); self.end_headers(); return
        if isinstance(val, list):
            page = int(q.get("page", ["1"])[0]); per = int(q.get("per_page", ["30"])[0])
            val = val[(page - 1) * per: page * per]
        body = val if isinstance(val, str) else json.dumps(val)
        self.send_response(200); self.end_headers(); self.wfile.write(body.encode())


SRV = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=SRV.serve_forever, daemon=True).start()
API = f"http://127.0.0.1:{SRV.server_port}"


def commit(login="Madgeniusblink", email="m@example.com", sha="c" * 40,
           author_login=None, committer_login=None, author_id=None, committer_id=None,
           author_email=None, committer_email=None):
    al = author_login if author_login is not None else login
    cl = committer_login if committer_login is not None else login
    ae = author_email if author_email is not None else email
    ce = committer_email if committer_email is not None else email
    author = None
    if al or author_id is not None:
        author = {}
        if al:
            author["login"] = al
        if author_id is not None:
            author["id"] = author_id
    committer = None
    if cl or committer_id is not None:
        committer = {}
        if cl:
            committer["login"] = cl
        if committer_id is not None:
            committer["id"] = committer_id
    return {"sha": sha, "author": author, "committer": committer,
            "commit": {"author": {"name": al or "x", "email": ae},
                       "committer": {"name": cl or "x", "email": ce}}}


def setup(ref="madgeniusblink/feat/x", author="Madgeniusblink", atype="User", author_id=None,
          files=(".github/workflows/a.yml",), commits=None, reviews=(), manifest=MANIFEST, head=HEAD,
          changed=None, ncommits=None, renames=(), engine_config=None):
    commits = [commit()] if commits is None else commits
    fl = [{"filename": f} for f in files] + [{"filename": n, "previous_filename": o} for o, n in renames]
    Fake.routes = {
        "/repos/BloclabsHQ/fabricbloc/pulls/7": {"head": {"sha": head, "ref": ref}, "base": {"sha": BASE, "ref": "main"},
                                                "user": {"login": author, "type": atype, **({"id": author_id} if author_id is not None else {})},
                                                "changed_files": len(fl) if changed is None else changed,
                                                "commits": len(commits) if ncommits is None else ncommits},
        "/repos/BloclabsHQ/fabricbloc/pulls/7/files": fl,
        "/repos/BloclabsHQ/fabricbloc/pulls/7/commits": commits,
        "/repos/BloclabsHQ/fabricbloc/pulls/7/reviews": list(reviews),
        "manifest": json.dumps(manifest) if manifest is not None else None,
        **({"config": engine_config} if engine_config is not None else {}),
    }


def run(mode, repo="BloclabsHQ/fabricbloc", event_head=HEAD, gh_token="test"):
    env = dict(os.environ, MODE=mode, API=API, GH_TOKEN=gh_token, REPO=repo, PR="7", EVENT_HEAD_SHA=event_head)
    p = subprocess.run([sys.executable, "-c", embedded(mode)], env=env, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout + p.stderr


def approve(login="Madgeniusblink", sha=HEAD, state="APPROVED"):
    return {"user": {"login": login}, "state": state, "commit_id": sha}


AGENT = dict(ref="agent/autonomous/fix/x-i1-y", author="fabricbloc-agent-ops[bot]", atype="Bot",
             commits=[commit("cursoragent", "cursoragent@cursor.com")])


class T(unittest.TestCase):
    def test_required_gates_github_hosted_only(self):
        assert_required_gate_hosted_only()

    def test_copies_identical(self):
        self.assertEqual(embedded(GATES[0]), embedded(GATES[1]))

    def test_no_checkout_anywhere(self):
        for g in GATES:
            text = (WF / f"{g}.yml").read_text()
            self.assertNotIn("actions/checkout", text.replace("NO actions/checkout", ""))
            self.assertNotIn("${{ github.event.pull_request.head.ref", text)

    def test_F6_malicious_exit0_edit_still_fails(self):
        # Agent PR rewrites fabricbloc's own copy of the gate to `exit 0`.
        setup(files=(".github/workflows/agent-denied-paths.yml",), **AGENT)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out); self.assertIn("denied path", out)

    def test_human_pr_not_gated(self):
        setup()
        self.assertEqual(run("agent-denied-paths")[0], 0)
        self.assertEqual(run("agent-review-of-record")[0], 0)

    def test_human_named_branch_with_cursor_commits_is_gated(self):
        setup(commits=[commit("cursoragent", "cursoragent@cursor.com")])
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_unlinked_cursor_email_is_gated(self):
        setup(commits=[commit(None, "cursoragent@cursor.com")])
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_K7c_noreply_email_only_no_login(self):
        setup(commits=[commit(None, "199161495+cursoragent@users.noreply.github.com")])
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_K7d_cursor_user_id_other_login(self):
        setup(commits=[commit("notcursoragent", "other@example.com", author_id=199161495)])
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_agent_email_case_insensitive(self):
        setup(commits=[commit(None, "CursorAgent@Cursor.COM")])
        self.assertEqual(run("agent-denied-paths")[0], 1)
        setup(commits=[commit(None, "199161495+CursorAgent@users.noreply.github.com")])
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_agent_login_case_insensitive(self):
        setup(commits=[commit("CursorAgent", "other@example.com")])
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_agent_email_strip_and_case(self):
        setup(commits=[commit(None, " CURSORAGENT@CURSOR.COM ")])
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_empty_gh_token_fails(self):
        setup(files=("docs/x.md",), **AGENT)
        code, out = run("agent-denied-paths", gh_token="")
        self.assertEqual(code, 1, out)
        self.assertIn("GH_TOKEN is empty", out)

    def test_ai_reviewer_approval_counts(self):
        cfg = "human: ['Madgeniusblink']\nai_reviewers: ['fabricbloc-ai-reviewer']\n"
        setup(files=("docs/x.md",), reviews=[approve("fabricbloc-ai-reviewer")],
              engine_config=cfg, **AGENT)
        self.assertEqual(run("agent-review-of-record")[0], 0)

    def test_ai_reviewer_self_approve_linked_commit_fails(self):
        cfg = "human: ['Madgeniusblink']\nai_reviewers: ['fabricbloc-ai-reviewer']\n"
        a = dict(AGENT, commits=[commit("fabricbloc-ai-reviewer", "ai@example.com")])
        setup(files=("docs/x.md",), reviews=[approve("fabricbloc-ai-reviewer")],
              engine_config=cfg, **a)
        self.assertEqual(run("agent-review-of-record")[0], 1)

    def test_ai_reviewer_self_approve_unlinked_email_fails(self):
        cfg = "human: ['Madgeniusblink']\nai_reviewers: ['fabricbloc-ai-reviewer']\n"
        a = dict(AGENT, commits=[commit(None, "fabricbloc-ai-reviewer@users.noreply.github.com",
                                      author_email="fabricbloc-ai-reviewer@users.noreply.github.com")])
        setup(files=("docs/x.md",), reviews=[approve("fabricbloc-ai-reviewer")],
              engine_config=cfg, **a)
        self.assertEqual(run("agent-review-of-record")[0], 1)

    def test_ai_reviewer_on_handle_branch_not_human_skip(self):
        cfg = "human: ['Madgeniusblink']\nai_reviewers: ['fabricbloc-ai-reviewer']\n"
        setup(ref="madgeniusblink/feat/x", author="fabricbloc-ai-reviewer", atype="User",
              files=("docs/x.md",), engine_config=cfg)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertIn("gated because", out)

    def test_handle_must_match_author(self):
        setup(ref="someoneelse/feat/x")
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_session_branch_gated(self):
        setup(ref="agent/session/ci/cursor-env-policy")
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_bot_author_on_human_ref_gated(self):
        setup(ref="madgeniusblink/feat/x", author="fabricbloc-agent-ops[bot]", atype="Bot")
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_agent_docs_only_passes_denied_paths(self):
        setup(files=("docs/x.md",), **AGENT)
        self.assertEqual(run("agent-denied-paths")[0], 0)

    def test_rename_out_of_denied_path(self):
        setup(files=(), renames=((".github/workflows/a.yml", "tmp/a.yml"),), **AGENT)
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_floor_applies_without_base_manifest(self):
        setup(files=(".github/actions/x/action.yml",), manifest=None, **AGENT)
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_proposed_not_applied_by_default(self):
        setup(files=(".cursor/environment.json",), **AGENT)
        self.assertEqual(run("agent-denied-paths")[0], 0)

    def test_empty_diff_fails(self):
        setup(files=(), **AGENT)
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_file_count_mismatch_fails(self):
        setup(files=("docs/x.md",), changed=5, **AGENT)
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_too_many_commits_fails(self):
        setup(ncommits=250, **{k: v for k, v in AGENT.items()})
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_stale_event_head_fails(self):
        setup(files=("docs/x.md",), **AGENT)
        self.assertEqual(run("agent-denied-paths", event_head=OLD)[0], 1)

    def test_api_error_fails_closed(self):
        setup(files=("docs/x.md",), **AGENT)
        Fake.routes["/repos/BloclabsHQ/fabricbloc/pulls/7/files"] = 500
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_self_repo_skips(self):
        self.assertEqual(run("agent-denied-paths", repo="BloclabsHQ/fabricbloc-branch-policy")[0], 0)

    def test_unknown_repo_fails(self):
        self.assertEqual(run("agent-denied-paths", repo="BloclabsHQ/other")[0], 1)

    def test_review_none_fails(self):
        setup(files=("docs/x.md",), **AGENT)
        self.assertEqual(run("agent-review-of-record")[0], 1)

    def test_review_at_head_passes(self):
        setup(files=("docs/x.md",), reviews=[approve()], **AGENT)
        self.assertEqual(run("agent-review-of-record")[0], 0)

    def test_review_at_old_head_fails(self):
        setup(files=("docs/x.md",), reviews=[approve(sha=OLD)], **AGENT)
        self.assertEqual(run("agent-review-of-record")[0], 1)

    def test_changes_requested_blocks(self):
        setup(files=("docs/x.md",), reviews=[approve(), approve("other", state="CHANGES_REQUESTED")], **AGENT)
        self.assertEqual(run("agent-review-of-record")[0], 1)

    def test_self_approval_by_committer_fails(self):
        a = dict(AGENT, commits=[commit("cursoragent", "cursoragent@cursor.com"), commit("Madgeniusblink", sha="d" * 40)])
        setup(files=("docs/x.md",), reviews=[approve()], **a)
        self.assertEqual(run("agent-review-of-record")[0], 1)

    def test_non_allowlisted_approver_fails(self):
        setup(files=("docs/x.md",), reviews=[approve("randomuser")], **AGENT)
        self.assertEqual(run("agent-review-of-record")[0], 1)

    def test_hostile_branch_name_is_inert(self):
        setup(ref='agent/x";$(touch /tmp/pwned);"', files=("docs/x.md",), atype="Bot", author="fabricbloc-agent-ops[bot]")
        run("agent-denied-paths")
        self.assertFalse(Path("/tmp/pwned").exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
