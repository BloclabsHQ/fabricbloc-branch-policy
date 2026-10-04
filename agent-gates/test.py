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
HEAD, BASE, OLD = "h" * 40, "b" * 40, "o" * 40


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


def commit(login="Madgeniusblink", email="m@example.com", sha="c" * 40):
    return {"sha": sha, "author": {"login": login} if login else None, "committer": {"login": login} if login else None,
            "commit": {"author": {"name": login or "x", "email": email}, "committer": {"name": login or "x", "email": email}}}


def setup(ref="madgeniusblink/feat/x", author="Madgeniusblink", atype="User", files=(".github/workflows/a.yml",),
          commits=None, reviews=(), manifest=MANIFEST, head=HEAD, changed=None, ncommits=None, renames=()):
    commits = [commit()] if commits is None else commits
    fl = [{"filename": f} for f in files] + [{"filename": n, "previous_filename": o} for o, n in renames]
    Fake.routes = {
        "/repos/BloclabsHQ/fabricbloc/pulls/7": {"head": {"sha": head, "ref": ref}, "base": {"sha": BASE, "ref": "main"},
                                                "user": {"login": author, "type": atype},
                                                "changed_files": len(fl) if changed is None else changed,
                                                "commits": len(commits) if ncommits is None else ncommits},
        "/repos/BloclabsHQ/fabricbloc/pulls/7/files": fl,
        "/repos/BloclabsHQ/fabricbloc/pulls/7/commits": commits,
        "/repos/BloclabsHQ/fabricbloc/pulls/7/reviews": list(reviews),
        "manifest": json.dumps(manifest) if manifest is not None else None,
    }


def run(mode, repo="BloclabsHQ/fabricbloc", event_head=HEAD):
    env = dict(os.environ, MODE=mode, API=API, GH_TOKEN="test", REPO=repo, PR="7", EVENT_HEAD_SHA=event_head)
    p = subprocess.run([sys.executable, "-c", embedded(mode)], env=env, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout + p.stderr


def approve(login="Madgeniusblink", sha=HEAD, state="APPROVED"):
    return {"user": {"login": login}, "state": state, "commit_id": sha}


AGENT = dict(ref="agent/autonomous/fix/x-i1-y", author="fabricbloc-agent-ops[bot]", atype="Bot",
             commits=[commit("cursoragent", "cursoragent@cursor.com")])


class T(unittest.TestCase):
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
