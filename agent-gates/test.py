#!/usr/bin/env python3
"""Contract tests for the F6 pinned gates. Run: python3 agent-gates/test.py

Extracts the embedded gate script from both workflow files (they must be
byte-identical), then runs it against a local fake GitHub API. No network.
Includes the F6 malicious case: an agent PR that rewrites the gate to exit 0.
"""
import copy, json, os, re, subprocess, sys, tempfile, threading, unittest, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml  # pyyaml, same pin as fabricbloc canon-check

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
GATES = ("agent-denied-paths", "agent-review-of-record")
REQUIRED_GATE_WORKFLOWS = GATES + ("branch-name-guard",)
# GitHub-hosted runner labels (no self-hosted). Required org gates pin to ubuntu-latest only.
GITHUB_HOSTED_RUNNER_LABELS = frozenset({
    "ubuntu-latest", "ubuntu-24.04", "ubuntu-22.04", "ubuntu-20.04",
    "windows-latest", "windows-2025", "windows-2022", "windows-11-arm",
    "macos-latest", "macos-15", "macos-14", "macos-13",
})
HEAD, BASE, OLD = "h" * 40, "b" * 40, "o" * 40


def validate_required_gate_hosted_only(name, doc):
    """Required org workflows must use literal runs-on: ubuntu-latest on every job."""
    jobs = doc.get("jobs") or {}
    if not jobs:
        raise AssertionError(f"{name}: jobs must not be empty")
    for job_id, job in jobs.items():
        if "uses" in job:
            raise AssertionError(
                f"{name} job {job_id}: reusable workflow jobs (uses:) are not allowed")
        value = job.get("runs-on")
        where = f"job {job_id}"
        if value is None:
            raise AssertionError(f"{name} {where}: missing runs-on")
        if isinstance(value, str):
            low = value.lower()
            if "self-hosted" in low or "${{" in value:
                raise AssertionError(f"{name} {where}: disallowed runs-on {value!r}")
            if value.strip() != "ubuntu-latest":
                raise AssertionError(
                    f"{name} {where}: runs-on must be ubuntu-latest (got {value!r})")
            if value not in GITHUB_HOSTED_RUNNER_LABELS:
                raise AssertionError(f"{name} {where}: not a known GitHub-hosted label")
        elif isinstance(value, list):
            for label in value:
                if isinstance(label, str) and "self-hosted" in label.lower():
                    raise AssertionError(f"{name} {where}: self-hosted label {label!r}")
            raise AssertionError(f"{name} {where}: runs-on must be ubuntu-latest, not a label list")
        else:
            raise AssertionError(
                f"{name} {where}: runs-on must be the literal string ubuntu-latest (got {value!r})")
        strategy = job.get("strategy") or {}
        for dim in (strategy.get("matrix") or {}):
            if dim == "runs-on" or "runner" in dim.lower():
                raise AssertionError(f"{name} job {job_id}: matrix must not select runners ({dim})")


def assert_required_gate_hosted_only():
    for name in REQUIRED_GATE_WORKFLOWS:
        validate_required_gate_hosted_only(name, yaml.safe_load((WF / f"{name}.yml").read_text()))


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
           author_email=None, committer_email=None, message=""):
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
            "commit": {"message": message,
                       "author": {"name": al or "x", "email": ae},
                       "committer": {"name": cl or "x", "email": ce}}}


def setup(ref="madgeniusblink/feat/x", author="Madgeniusblink", atype="User", author_id=None,
          files=(".github/workflows/a.yml",), commits=None, reviews=(), manifest=MANIFEST, head=HEAD,
          changed=None, ncommits=None, renames=(), engine_config=None, base_ref="main",
          commit_pulls=None, repo="BloclabsHQ/fabricbloc"):
    commits = [commit()] if commits is None else commits
    fl = [{"filename": f} for f in files] + [{"filename": n, "previous_filename": o} for o, n in renames]
    pr_base = f"/repos/{repo}/pulls/7"
    routes = {
        f"{pr_base}": {"head": {"sha": head, "ref": ref},
                       "base": {"sha": BASE, "ref": base_ref},
                       "user": {"login": author, "type": atype, **({"id": author_id} if author_id is not None else {})},
                       "changed_files": len(fl) if changed is None else changed,
                       "commits": len(commits) if ncommits is None else ncommits},
        f"{pr_base}/files": fl,
        f"{pr_base}/commits": commits,
        f"{pr_base}/reviews": list(reviews),
        "manifest": json.dumps(manifest) if manifest is not None else None,
        **({"config": engine_config} if engine_config is not None else {}),
    }
    commit_pulls = commit_pulls or {}
    for c in commits:
        sha = c.get("sha")
        if not sha:
            continue
        key = f"/repos/{repo}/commits/{sha}/pulls"
        if sha in commit_pulls:
            routes[key] = commit_pulls[sha]
        elif base_ref == "main":
            routes[key] = []
    Fake.routes = routes


def run(mode, repo="BloclabsHQ/fabricbloc", event_head=HEAD, gh_token="test", extra_env=None):
    env = dict(os.environ, MODE=mode, API=API, GH_TOKEN=gh_token, REPO=repo, PR="7", EVENT_HEAD_SHA=event_head)
    if extra_env:
        env.update(extra_env)
    p = subprocess.run([sys.executable, "-c", embedded(mode)], env=env, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout + p.stderr


def approve(login="Madgeniusblink", sha=HEAD, state="APPROVED", body=None, user_id=None):
    user = {"login": login}
    if user_id is not None:
        user["id"] = user_id
    r = {"user": user, "state": state, "commit_id": sha}
    if body is not None:
        r["body"] = body
    return r


def reviewer_body(sha=HEAD, ref="cli:probe-token-abcdef"):
    return f"approve head {sha}\napproval-ref: {ref}"


def load_canon():
    return json.loads((ROOT / "rulesets" / "canon.json").read_text())


def creation_restricted(canon):
    return next(r for r in canon["repository_rulesets"] if r["name"] == "canon-branch-creation-restricted")


def deploy_human_only(canon):
    return next(r for r in canon["repository_rulesets"] if r["name"] == "canon-deploy-branches-human-only")


CREATION_RESTRICTED_FORBIDDEN_EXCLUDES = frozenset({
    "refs/heads/**",
    "refs/heads/*",
    "refs/heads/**/*",
    "~ALL",
})


def exclude_would_cover_all_branches(pattern):
    p = (pattern or "").strip()
    return p in CREATION_RESTRICTED_FORBIDDEN_EXCLUDES


def assert_creation_restricted_shape(canon):
    rs = creation_restricted(canon)
    assert rs.get("bypass_actors") == [], "creation-restricted bypass must be empty"
    assert rs.get("enforcement") == "active"
    inc = rs["conditions"]["ref_name"]["include"]
    assert "refs/heads/**" in inc
    exc = rs["conditions"]["ref_name"]["exclude"]
    assert "refs/heads/main" in exc and "refs/heads/agent/**" in exc
    assert "refs/heads/dependabot/**" not in exc
    for path in exc:
        assert "refs/heads/*/" not in path, f"wildcard handle exclude forbidden: {path}"
        assert not exclude_would_cover_all_branches(path), (
            f"creation-restricted exclude must not cover all branches: {path}")
    ns = load_gate_constants()
    for handle in ns["GOV_HUMAN_HANDLES"]:
        for typ in ns["HUMAN_BRANCH_TYPES"]:
            assert f"refs/heads/{handle}/{typ}/**" in exc


def assert_deploy_human_only_shape(canon):
    rs = deploy_human_only(canon)
    assert rs.get("bypass_actors") == []
    rules = {r["type"] for r in rs["rules"]}
    assert "creation" in rules and "update" in rules


def load_gate_constants():
    src = (ROOT / "agent-gates" / "embedded_gate.py").read_text()
    ns = {}
    exec(src.replace("\nmain()\n", "\n"), ns)  # noqa: S102
    return ns


def run_gate_with_patch(mode, patch_src, extra_env=None):
    body = patch_src(embedded(mode))
    env = dict(os.environ, MODE=mode, API=API, GH_TOKEN="test", REPO="BloclabsHQ/fabricbloc",
               PR="7", EVENT_HEAD_SHA=HEAD)
    if extra_env:
        env.update(extra_env)
    p = subprocess.run([sys.executable, "-c", body], env=env, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout + p.stderr


def run_with_reviewer_bots(mode, bots, **kwargs):
    pairs = ", ".join(repr((str(b[0]), int(b[1]))) for b in bots)
    body = embedded(mode)
    body = re.sub(
        r"^REVIEWER_APP_BOTS = set\(\)",
        f"REVIEWER_APP_BOTS = {{{pairs}}}",
        body,
        count=1,
        flags=re.M,
    )
    env = dict(os.environ, MODE=mode, API=API, GH_TOKEN="test", REPO="BloclabsHQ/fabricbloc",
               PR="7", EVENT_HEAD_SHA=HEAD)
    env.update(kwargs.get("env", {}))
    p = subprocess.run([sys.executable, "-c", body], env=env, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout + p.stderr


def run_with_bootstrap_refs(mode, refs, **kwargs):
    inner = ", ".join(repr(r) for r in sorted(refs))
    line = f"BOOTSTRAP_BASE_REFS = frozenset({{{inner}}})"
    body = embedded(mode)
    body = re.sub(
        r"^BOOTSTRAP_BASE_REFS = frozenset\(\{.*\}\)\s*$",
        line,
        body,
        count=1,
        flags=re.M,
    )
    env = dict(os.environ, MODE=mode, API=API, GH_TOKEN="test", REPO="BloclabsHQ/fabricbloc",
               PR="7", EVENT_HEAD_SHA=HEAD)
    env.update(kwargs.get("env", {}))
    p = subprocess.run([sys.executable, "-c", body], env=env, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout + p.stderr


def gate_ns_with_bootstrap(refs):
    ns = load_gate_constants()
    ns["BOOTSTRAP_BASE_REFS"] = frozenset(refs)
    return ns


AGENT = dict(ref="agent/autonomous/fix/x-i1-y", author="fabricbloc-agent-ops[bot]", atype="Bot",
             commits=[commit("cursoragent", "cursoragent@cursor.com")])

# Bot logins and numeric user ids from unauthenticated GET /users/<login>%5Bbot%5D (2026-10-04).
PINNED_AGENT_BOT_IDENTITIES = (
    ("fabricbloc-agent-ops[bot]", 337168458),
    ("fabricbloc-approval-relay[bot]", 337608266),
    ("cursor[bot]", 206951365),
    ("cursoragent", 199161495),
    ("chatgpt-codex-connector[bot]", 199175422),
    ("claude[bot]", 209825114),
    ("github-actions[bot]", 41898282),
    ("Copilot", 175728472),  # GET /users/copilot-pull-request-reviewer%5Bbot%5D
)


class T(unittest.TestCase):
    def test_required_gates_github_hosted_only(self):
        assert_required_gate_hosted_only()

    def test_required_gate_hosted_only_rejects_bad_workflows(self):
        good = {"jobs": {"gate": {"runs-on": "ubuntu-latest", "steps": [{"run": "true"}]}}}
        validate_required_gate_hosted_only("good", good)
        cases = (
            ("missing runs-on", {"jobs": {"gate": {"steps": [{"run": "true"}]}}}),
            ("uses reusable workflow", {"jobs": {"gate": {"uses": "org/repo/.github/workflows/w.yml@main"}}}),
            ("expression runs-on", {"jobs": {"gate": {"runs-on": "${{ vars.X }}", "steps": [{"run": "true"}]}}}),
            ("label list", {"jobs": {"gate": {"runs-on": ["ubuntu-latest"], "steps": [{"run": "true"}]}}}),
            ("matrix runs-on", {"jobs": {"gate": {"runs-on": "ubuntu-latest", "strategy": {"matrix": {"runs-on": ["ubuntu-latest"]}}, "steps": [{"run": "true"}]}}}),
            ("self-hosted label", {"jobs": {"gate": {"runs-on": '["self-hosted","linux","x64"]', "steps": [{"run": "true"}]}}}),
            ("empty jobs", {"jobs": {}}),
        )
        for label, doc in cases:
            with self.subTest(label):
                with self.assertRaises(AssertionError):
                    validate_required_gate_hosted_only("bad", doc)

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

    def test_target_repos_includes_fabricbloc_context_keyflo(self):
        repos = load_gate_constants()["TARGET_REPOS"]
        self.assertEqual(
            repos,
            {
                "BloclabsHQ/fabricbloc",
                "BloclabsHQ/context",
                "BloclabsHQ/keyflo-session-issuer",
            },
        )

    def test_onboarded_repo_context_human_pr_passes_denied_paths(self):
        setup(files=("docs/x.md",), repo="BloclabsHQ/context")
        self.assertEqual(run("agent-denied-paths", repo="BloclabsHQ/context")[0], 0)

    def test_onboarded_repo_keyflo_human_pr_passes_denied_paths(self):
        setup(files=("docs/x.md",), repo="BloclabsHQ/keyflo-session-issuer")
        self.assertEqual(run("agent-denied-paths", repo="BloclabsHQ/keyflo-session-issuer")[0], 0)

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

    def test_parse_flow_list_three_unquoted(self):
        ns = load_gate_constants()
        cfg = "ai_reviewers: [alpha, beta, gamma]\n"
        self.assertEqual(ns["parse_flow_list_line"](cfg, "ai_reviewers"),
                         {"alpha", "beta", "gamma"})

    def test_parse_flow_list_three_quoted(self):
        ns = load_gate_constants()
        cfg = "ai_reviewers: ['one', 'two', 'three']\n"
        self.assertEqual(ns["parse_flow_list_line"](cfg, "ai_reviewers"),
                         {"one", "two", "three"})

    def test_parse_flow_list_mixed(self):
        ns = load_gate_constants()
        cfg = "ai_reviewers: [Madgeniusblink, 'fabricbloc-reviewer[bot]', bot2]\n"
        self.assertEqual(ns["parse_flow_list_line"](cfg, "ai_reviewers"),
                         {"Madgeniusblink", "fabricbloc-reviewer[bot]", "bot2"})

    def test_parse_flow_list_ai_reviewers_fabricbloc_reviewer_bot(self):
        ns = load_gate_constants()
        cfg = "ai_reviewers: ['fabricbloc-reviewer[bot]']\n"
        self.assertEqual(ns["parse_flow_list_line"](cfg, "ai_reviewers"),
                         {"fabricbloc-reviewer[bot]"})

    def test_reviewer_app_bots_disjoint_from_agent_identities(self):
        ns = load_gate_constants()
        bots = ns["REVIEWER_APP_BOTS"]
        agent_logins = {login.lower() for login, _ in PINNED_AGENT_BOT_IDENTITIES}
        agent_logins |= {x.lower() for x in ns["AGENT_LOGINS"]}
        agent_ids = {uid for _, uid in PINNED_AGENT_BOT_IDENTITIES} | set(ns["AGENT_USER_IDS"])
        for login, uid in bots:
            self.assertNotIn(login.lower(), agent_logins)
            self.assertNotIn(uid, agent_ids)
        for login, uid in PINNED_AGENT_BOT_IDENTITIES:
            self.assertNotIn((login, uid), bots)

    def test_approval_relay_bot_cannot_count_as_reviewer_app(self):
        relay = "fabricbloc-approval-relay[bot]"
        relay_id = 337608266
        cfg = f"human: ['Madgeniusblink', '{relay}']\n"
        setup(files=("docs/x.md",),
              reviews=[approve(relay, body=reviewer_body(), user_id=relay_id)],
              engine_config=cfg, **AGENT)
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 1, out)

    def test_reviewer_app_approval_at_head_valid_body_passes(self):
        cfg = "human: ['Madgeniusblink', 'fabricbloc-reviewer[bot]']\n"
        bot = "fabricbloc-reviewer[bot]"
        bots = [[bot, 999001]]
        setup(files=("docs/x.md",),
              reviews=[approve(bot, body=reviewer_body(), user_id=999001)],
              engine_config=cfg, **AGENT)
        code, out = run_with_reviewer_bots("agent-review-of-record", bots)
        self.assertEqual(code, 0, out)

    def test_reviewer_app_wrong_numeric_id_fails(self):
        cfg = "human: ['Madgeniusblink', 'fabricbloc-reviewer[bot]']\n"
        bot = "fabricbloc-reviewer[bot]"
        bots = [[bot, 999001]]
        setup(files=("docs/x.md",),
              reviews=[approve(bot, body=reviewer_body(), user_id=999002)],
              engine_config=cfg, **AGENT)
        code, out = run_with_reviewer_bots("agent-review-of-record", bots)
        self.assertEqual(code, 1, out)

    def test_reviewer_app_missing_sha_in_body_fails(self):
        cfg = "human: ['Madgeniusblink', 'fabricbloc-reviewer[bot]']\n"
        bot = "fabricbloc-reviewer[bot]"
        bots = [[bot, 999001]]
        setup(files=("docs/x.md",),
              reviews=[approve(bot, body="approval-ref: cli:abcdef12", user_id=999001)],
              engine_config=cfg, **AGENT)
        code, out = run_with_reviewer_bots("agent-review-of-record", bots)
        self.assertEqual(code, 1, out)
        self.assertIn("lacks full 40-char head SHA", out)

    def test_reviewer_app_missing_approval_ref_fails(self):
        cfg = "human: ['Madgeniusblink', 'fabricbloc-reviewer[bot]']\n"
        bot = "fabricbloc-reviewer[bot]"
        bots = [[bot, 999001]]
        setup(files=("docs/x.md",),
              reviews=[approve(bot, body=HEAD, user_id=999001)],
              engine_config=cfg, **AGENT)
        code, out = run_with_reviewer_bots("agent-review-of-record", bots)
        self.assertEqual(code, 1, out)
        self.assertIn("approval-ref", out)

    def test_reviewer_app_stale_commit_id_fails(self):
        cfg = "human: ['Madgeniusblink', 'fabricbloc-reviewer[bot]']\n"
        bot = "fabricbloc-reviewer[bot]"
        bots = [[bot, 999001]]
        setup(files=("docs/x.md",),
              reviews=[approve(bot, sha=OLD, body=reviewer_body(OLD), user_id=999001)],
              engine_config=cfg, **AGENT)
        code, out = run_with_reviewer_bots("agent-review-of-record", bots)
        self.assertEqual(code, 1, out)

    def test_reviewer_app_never_human_skip(self):
        ns = load_gate_constants()
        bots = {("fabricbloc-reviewer", 999001)}
        humans = {"Madgeniusblink", "fabricbloc-reviewer"}
        commits = [commit("Madgeniusblink")]
        applies, why = ns["gate_applies"](
            "madgeniusblink/feat/x", "fabricbloc-reviewer", "User", 999001,
            commits, "dev", humans, set(), bots)
        self.assertTrue(applies)
        self.assertIn("reviewer App author never qualifies for human skip", why[0])

    def test_unparseable_ai_reviewers_fails_closed(self):
        cfg = "human: ['Madgeniusblink']\nai_reviewers:\n  - bot\n"
        setup(files=("docs/x.md",), engine_config=cfg, **AGENT)
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 1, out)
        self.assertIn("ai_reviewers", out)

    def test_finding_c_agent_pr_base_release_fails(self):
        setup(files=("docs/x.md",), base_ref="release/x", **AGENT)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("agent PRs must target main", out)

    def test_finding_c_agent_pr_base_main_follows_normal_flow(self):
        setup(files=("docs/x.md",), base_ref="main", **AGENT)
        self.assertEqual(run("agent-denied-paths")[0], 0)

    def test_bootstrap_exact_match_allows_agent_pr(self):
        setup(files=("docs/x.md",), base_ref="f6-gate-test", **AGENT)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertNotIn("agent PRs must target main", out)
        self.assertIn("BOOTSTRAP BASE ALLOWANCE ACTIVE", out)
        self.assertIn("::warning::", out)

    def test_bootstrap_near_misses_deny(self):
        cases = ("f6-gate-test-x", "F6-gate-test", "f6-gate-test/x")
        for base in cases:
            setup(files=("docs/x.md",), base_ref=base, **AGENT)
            code, out = run("agent-denied-paths")
            self.assertEqual(code, 1, out)
            self.assertIn("agent PRs must target main", out)

    def test_bootstrap_glob_entry_in_allowlist_does_not_allow(self):
        setup(files=("docs/x.md",), base_ref="f6-gate-test", **AGENT)
        code, out = run_with_bootstrap_refs(
            "agent-denied-paths", ["refs/heads/f6-gate-test/**"])
        self.assertEqual(code, 1, out)
        self.assertIn("agent PRs must target main", out)

    def test_bootstrap_empty_allowlist_restores_strict_main(self):
        setup(files=("docs/x.md",), base_ref="f6-gate-test", **AGENT)
        code, out = run_with_bootstrap_refs("agent-denied-paths", [])
        self.assertEqual(code, 1, out)
        self.assertIn("agent PRs must target main", out)
        ns = gate_ns_with_bootstrap([])
        ok, bootstrap = ns["pr_base_treated_as_main"]("main")
        self.assertTrue(ok)
        self.assertFalse(bootstrap)

    def test_bootstrap_policy_canon_path_env_ignored(self):
        canon = copy.deepcopy(load_canon())
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        gates["_bootstrap_ref_include"] = ["refs/heads/release/x"]
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(canon, f)
        f.close()
        try:
            setup(files=("docs/x.md",), base_ref="release/x", **AGENT)
            code, out = run_with_bootstrap_refs(
                "agent-denied-paths", ["refs/heads/f6-gate-test"],
                env={"POLICY_CANON_PATH": f.name},
            )
            self.assertEqual(code, 1, out)
            self.assertIn("agent PRs must target main", out)
        finally:
            os.unlink(f.name)

    def test_embedded_bootstrap_matches_canon(self):
        ns = load_gate_constants()
        gates = next(r for r in load_canon()["organization_rulesets"] if r["name"] == "canon-agent-gates")
        expected = {
            e for e in (gates.get("_bootstrap_ref_include") or [])
            if isinstance(e, str) and e.startswith("refs/heads/")
        }
        self.assertEqual(ns["BOOTSTRAP_BASE_REFS"], frozenset(expected))

    def test_validate_canon_bootstrap_rollout_mutex(self):
        from validate_canon import bootstrap_rollout_mutex_errors

        canon = copy.deepcopy(load_canon())
        self.assertEqual(bootstrap_rollout_mutex_errors(canon), [])
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        gates["conditions"]["ref_name"]["include"].append("~DEFAULT_BRANCH")
        errs = bootstrap_rollout_mutex_errors(canon)
        self.assertTrue(errs)

    def test_validate_canon_bootstrap_ref_include_exact_pass(self):
        from validate_canon import bootstrap_ref_include_exact_errors

        canon = copy.deepcopy(load_canon())
        self.assertEqual(bootstrap_ref_include_exact_errors(canon), [])

    def test_validate_canon_bootstrap_ref_include_exact_rejects(self):
        from validate_canon import bootstrap_ref_include_exact_errors

        canon = copy.deepcopy(load_canon())
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        cases = (
            "refs/heads/**",
            "~ALL",
            "~DEFAULT_BRANCH",
            "refs/heads/main",
            "refs/heads/release/**",
            "refs/heads/prod/**",
            "refs/heads/stray-branch",
        )
        for extra in cases:
            with self.subTest(extra=extra):
                c = copy.deepcopy(canon)
                g = next(r for r in c["organization_rulesets"] if r["name"] == "canon-agent-gates")
                g["conditions"]["ref_name"]["include"] = list(g["_bootstrap_ref_include"]) + [extra]
                self.assertTrue(bootstrap_ref_include_exact_errors(c))
        c = copy.deepcopy(canon)
        g = next(r for r in c["organization_rulesets"] if r["name"] == "canon-agent-gates")
        g["conditions"]["ref_name"]["include"] = ["refs/heads/f6-gate-test", "refs/heads/other"]
        self.assertTrue(bootstrap_ref_include_exact_errors(c))

    def test_finding_c_human_pr_base_release_not_failed_by_base_rule(self):
        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",), base_ref="release/x")
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertNotIn("agent PRs must target main", out)

    def test_canon_agent_gates_has_no_bypass_actors(self):
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        self.assertEqual(gates.get("bypass_actors"), [])

    def test_canon_agent_gates_includes_main_release_prod(self):
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        inc = gates.get("_post_rollout_ref_include") or gates["conditions"]["ref_name"]["include"]
        self.assertIn("~DEFAULT_BRANCH", inc)
        self.assertIn("refs/heads/release/**", inc)
        self.assertIn("refs/heads/prod/**", inc)

    def test_canon_agent_gates_repository_name_matches_target_repos(self):
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        short = set(gates["conditions"]["repository_name"]["include"])
        expected = {r.split("/", 1)[1] for r in load_gate_constants()["TARGET_REPOS"]}
        self.assertEqual(short, expected)

    def test_canon_push_protected_paths_covers_workflows(self):
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        rs = next(r for r in canon["repository_rulesets"]
                  if r.get("_repository") == "fabricbloc" and r["name"] == "canon-push-protected-paths")
        paths = rs["rules"][0]["parameters"]["restricted_file_paths"]
        self.assertIn(".github/workflows/**/*", paths)

    def test_canon_branch_creation_restricted_no_tilde_all(self):
        canon = load_canon()

        def strip_meta(o):
            if isinstance(o, dict):
                return {k: strip_meta(v) for k, v in o.items() if not k.startswith("_")}
            if isinstance(o, list):
                return [strip_meta(x) for x in o]
            return o

        apply_blob = json.dumps(strip_meta(canon))
        self.assertNotIn("~ALL", apply_blob)
        assert_creation_restricted_shape(canon)

    def test_canon_creation_and_deploy_no_standing_bypass(self):
        canon = load_canon()
        assert_creation_restricted_shape(canon)
        assert_deploy_human_only_shape(canon)

    def test_gate_workflows_rerun_on_pull_request_edited(self):
        for name in GATES:
            doc = yaml.safe_load((WF / f"{name}.yml").read_text())
            pr_on = doc.get("on") or doc.get(True) or {}
            pr = pr_on.get("pull_request") if isinstance(pr_on, dict) else None
            types = pr.get("types") if isinstance(pr, dict) else None
            self.assertIsNotNone(types, name)
            self.assertIn("edited", types, name)

    def test_coauthored_by_cursor_email_is_agent(self):
        msg = "feat: x\n\nCo-authored-by: Cursor Agent <cursoragent@cursor.com>"
        setup(commits=[commit(message=msg)], files=("docs/x.md",))
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertIn("gated because", out)

    def test_coauthored_by_codex_noreply_is_agent(self):
        msg = "feat\n\nCo-authored-by: chatgpt-codex-connector[bot] <199175422+chatgpt-codex-connector[bot]@users.noreply.github.com>"
        setup(commits=[commit(message=msg)], files=("docs/x.md",))
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertIn("gated because", out)

    def test_human_main_pr_commit_from_agent_pr_is_gated(self):
        csha = "e" * 40
        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",),
              commits=[commit(sha=csha)], base_ref="main",
              commit_pulls={csha: [{"head": {"ref": "agent/autonomous/fix/x-i1-y"},
                                    "user": {"login": "Madgeniusblink", "type": "User"}}]})
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 1, out)
        self.assertIn("gated because", out)

    def test_commit_pulls_api_error_fails_closed(self):
        csha = "f" * 40
        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",),
              commits=[commit(sha=csha)], base_ref="main")
        Fake.routes[f"/repos/BloclabsHQ/fabricbloc/commits/{csha}/pulls"] = 500
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_commit_pulls_bad_top_level_shape_fails_closed(self):
        csha = "0" * 40
        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",),
              commits=[commit(sha=csha)], base_ref="main")
        Fake.routes[f"/repos/BloclabsHQ/fabricbloc/commits/{csha}/pulls"] = {"not": "a list"}
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_commit_pulls_missing_head_ref_fails_closed(self):
        csha = "1" * 40
        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",),
              commits=[commit(sha=csha)], base_ref="main",
              commit_pulls={csha: [{"user": {"login": "Madgeniusblink", "type": "User"}, "head": {}}]})
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("head.ref", out)

    def test_commit_pulls_pagination_finds_agent_on_later_page(self):
        csha = "2" * 40
        benign = {"head": {"ref": "madgeniusblink/feat/y"}, "user": {"login": "Madgeniusblink", "type": "User"}}
        agent_pull = {"head": {"ref": "agent/autonomous/fix/x-i1-y"},
                      "user": {"login": "Madgeniusblink", "type": "User"}}
        pulls = [benign] * 100 + [agent_pull]
        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",),
              commits=[commit(sha=csha)], base_ref="main",
              commit_pulls={csha: pulls})
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 1, out)
        self.assertIn("commits/pulls", out)

    def test_commit_pulls_pagination_cap_fails_closed(self):
        csha = "4" * 40
        benign = {"head": {"ref": "madgeniusblink/feat/y"}, "user": {"login": "Madgeniusblink", "type": "User"}}
        agent_pull = {"head": {"ref": "agent/autonomous/fix/x-i1-y"},
                      "user": {"login": "Madgeniusblink", "type": "User"}}
        pulls = [benign] * 500 + [agent_pull]
        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",),
              commits=[commit(sha=csha)], base_ref="main",
              commit_pulls={csha: pulls})
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("pagination cap (500)", out)

    def test_pr_commits_pagination_cap_fails_closed(self):
        benign = commit()
        commits = [benign] * 250
        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",),
              commits=commits, ncommits=200)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("pagination cap (250)", out)

    def test_lineage_bot_pr_author_type_is_agent_provenance(self):
        csha = "3" * 40
        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",),
              commits=[commit(sha=csha)], base_ref="main",
              commit_pulls={csha: [{"head": {"ref": "chore/index-regen-x"},
                                    "user": {"login": "Madgeniusblink", "type": "Bot"}}]})
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 1, out)
        self.assertIn("commits/pulls", out)

    def test_coauthored_by_lowercase_trailer_and_display_name(self):
        msg = "feat: x\n\nco-authored-by: CURSOR AGENT <cursoragent@cursor.com>"
        setup(ref="madgeniusblink/feat/x", files=(".github/workflows/a.yml",),
              commits=[commit(message=msg)])
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("denied path", out)

    def test_coauthored_by_second_trailer_agent(self):
        msg = ("feat: x\n\nCo-authored-by: Madgeniusblink <m@example.com>\n"
               "Co-authored-by: Cursor Agent <cursoragent@cursor.com>")
        setup(ref="madgeniusblink/feat/x", files=(".github/workflows/a.yml",),
              commits=[commit(message=msg)])
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("denied path", out)

    def test_agent_head_human_commits_release_base_fails(self):
        setup(ref="agent/session/ci/x", files=("docs/x.md",),
              commits=[commit()], base_ref="release/x")
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("agent PRs must target main", out)

    def test_mutation_creation_restricted_without_include_all_heads(self):
        import copy
        canon = copy.deepcopy(load_canon())
        creation_restricted(canon)["conditions"]["ref_name"]["include"] = ["refs/heads/main"]
        with self.assertRaises(AssertionError):
            assert_creation_restricted_shape(canon)

    def test_mutation_creation_restricted_exclude_refs_heads_glob(self):
        import copy
        canon = copy.deepcopy(load_canon())
        creation_restricted(canon)["conditions"]["ref_name"]["exclude"].append("refs/heads/**")
        with self.assertRaises(AssertionError):
            assert_creation_restricted_shape(canon)

    def test_mutation_creation_restricted_enforcement_disabled(self):
        import copy
        canon = copy.deepcopy(load_canon())
        creation_restricted(canon)["enforcement"] = "disabled"
        with self.assertRaises(AssertionError):
            assert_creation_restricted_shape(canon)

    def test_mutation_deploy_drops_update_rule(self):
        import copy
        canon = copy.deepcopy(load_canon())
        deploy_human_only(canon)["rules"] = [{"type": "creation"}]
        with self.assertRaises(AssertionError):
            assert_deploy_human_only_shape(canon)

    def test_mutation_deploy_ruleset_missing_fails_shape(self):
        import copy
        canon = copy.deepcopy(load_canon())
        canon["repository_rulesets"] = [
            r for r in canon["repository_rulesets"] if r["name"] != "canon-deploy-branches-human-only"
        ]
        with self.assertRaises(StopIteration):
            deploy_human_only(canon)

    def test_mutation_creation_bypass_actor_added(self):
        import copy
        canon = copy.deepcopy(load_canon())
        creation_restricted(canon)["bypass_actors"] = [
            {"actor_id": 1, "actor_type": "OrganizationAdmin", "bypass_mode": "always"}]
        with self.assertRaises(AssertionError):
            assert_creation_restricted_shape(canon)

    def test_mutation_base_check_startswith_main_would_miss_release(self):
        a = dict(AGENT, ref="madgeniusblink/feat/x", commits=[commit("cursoragent", "cursoragent@cursor.com")])
        setup(files=("docs/x.md",), base_ref="maintenance/foo", **a)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("agent PRs must target main", out)

        setup(files=("docs/x.md",), base_ref="maintenance/foo", **a)

        def patch(body):
            return body.replace(
                "    if base_ref == DEFAULT_BASE_REF:\n        return True, False",
                "    if base_ref.startswith(\"main\"):\n        return True, base_ref != DEFAULT_BASE_REF",
            )

        code, out = run_gate_with_patch("agent-denied-paths", patch)
        self.assertEqual(code, 0, out)
        self.assertNotIn("agent PRs must target main", out)

    def test_mutation_bootstrap_prefix_match_would_allow_near_miss(self):
        setup(files=("docs/x.md",), base_ref="f6-gate-test-x", **AGENT)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)

        def patch(body):
            return body.replace(
                "    if full in bootstrap_base_ref_allowlist():\n        return True, True",
                "    allow = bootstrap_base_ref_allowlist()\n"
                "    if any(full.startswith(x.rstrip(\"*\")) for x in allow):\n"
                "        return True, True",
            )

        setup(files=("docs/x.md",), base_ref="f6-gate-test-x", **AGENT)
        code, out = run_gate_with_patch("agent-denied-paths", patch)
        self.assertEqual(code, 0, out)

    def test_mutation_bootstrap_reads_from_pr_head_repo(self):
        malicious_canon = json.dumps({
            "organization_rulesets": [{
                "name": "canon-agent-gates",
                "_bootstrap_ref_include": ["refs/heads/release/x"],
            }],
        })
        key = f"/repos/BloclabsHQ/fabricbloc/contents/{urllib.parse.quote('rulesets/canon.json')}"
        setup(files=("docs/x.md",), base_ref="release/x", **AGENT)
        Fake.routes[key] = malicious_canon
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("agent PRs must target main", out)

        def patch(body):
            return body.replace(
                "    return BOOTSTRAP_BASE_REFS\n",
                "    text = base_text(\"rulesets/canon.json\", os.environ.get(\"EVENT_HEAD_SHA\", \"\"))\n"
                "    if not text:\n        return frozenset()\n"
                "    data = json.loads(text)\n"
                "    for rs in data.get(\"organization_rulesets\") or []:\n"
                "        if rs.get(\"name\") == \"canon-agent-gates\":\n"
                "            raw = rs.get(\"_bootstrap_ref_include\") or []\n"
                "            return frozenset(e for e in raw if isinstance(e, str))\n"
                "    return frozenset()\n",
                1,
            )

        setup(files=("docs/x.md",), base_ref="release/x", **AGENT)
        Fake.routes[key] = malicious_canon
        code, out = run_gate_with_patch("agent-denied-paths", patch)
        self.assertEqual(code, 0, out)
        self.assertNotIn("agent PRs must target main", out)

    def test_mutation_bootstrap_empty_list_allows_all_bases(self):
        setup(files=("docs/x.md",), base_ref="release/x", **AGENT)
        code, out = run_with_bootstrap_refs("agent-denied-paths", [])
        self.assertEqual(code, 1, out)

        def patch(body):
            return body.replace(
                "    if full in bootstrap_base_ref_allowlist():\n        return True, True",
                "    allow = bootstrap_base_ref_allowlist()\n"
                "    if not allow:\n        return True, True\n"
                "    if full in allow:\n        return True, True",
            )

        def patch_with_empty(body):
            body = patch(body)
            return re.sub(
                r"^BOOTSTRAP_BASE_REFS = frozenset\(\{.*\}\)\s*$",
                "BOOTSTRAP_BASE_REFS = frozenset()",
                body,
                count=1,
                flags=re.M,
            )

        setup(files=("docs/x.md",), base_ref="release/x", **AGENT)
        code, out = run_gate_with_patch("agent-denied-paths", patch_with_empty)
        self.assertEqual(code, 0, out)

    def test_mutation_bootstrap_policy_canon_path_env_read(self):
        canon = copy.deepcopy(load_canon())
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        gates["_bootstrap_ref_include"] = ["refs/heads/release/x"]
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(canon, f)
        f.close()
        try:
            setup(files=("docs/x.md",), base_ref="release/x", **AGENT)
            code, out = run("agent-denied-paths", extra_env={"POLICY_CANON_PATH": f.name})
            self.assertEqual(code, 1, out)

            def patch(body):
                return body.replace(
                    "    return BOOTSTRAP_BASE_REFS\n",
                    "    path = os.environ.get(\"POLICY_CANON_PATH\", \"\").strip()\n"
                    "    if path:\n"
                    "        with open(path, encoding=\"utf-8\") as fp:\n"
                    "            data = json.load(fp)\n"
                    "        for rs in data.get(\"organization_rulesets\") or []:\n"
                    "            if rs.get(\"name\") == \"canon-agent-gates\":\n"
                    "                raw = rs.get(\"_bootstrap_ref_include\") or []\n"
                    "                return frozenset(e for e in raw if isinstance(e, str))\n"
                    "    return BOOTSTRAP_BASE_REFS\n",
                    1,
                )

            setup(files=("docs/x.md",), base_ref="release/x", **AGENT)
            code, out = run_gate_with_patch(
                "agent-denied-paths", patch, extra_env={"POLICY_CANON_PATH": f.name})
            self.assertEqual(code, 0, out)
            self.assertNotIn("agent PRs must target main", out)
        finally:
            os.unlink(f.name)

    def test_mutation_validate_canon_bootstrap_include_subset_only(self):
        from validate_canon import bootstrap_ref_include_exact_errors

        canon = copy.deepcopy(load_canon())
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        gates["conditions"]["ref_name"]["include"].append("refs/heads/stray")
        self.assertTrue(bootstrap_ref_include_exact_errors(canon))

        def patch(src):
            return src.replace(
                "        if inc_set != bootstrap_set:",
                "        if bootstrap_set - inc_set:",
            )

        ns = {"__file__": str(ROOT / "agent-gates" / "validate_canon.py")}
        src = (ROOT / "agent-gates" / "validate_canon.py").read_text()
        exec(patch(src).split("def main():")[0], ns)  # noqa: S102
        self.assertFalse(ns["bootstrap_ref_include_exact_errors"](canon))

    def test_mutation_removing_author_leg_misses_base_rule(self):
        setup(ref="madgeniusblink/feat/x", author="fabricbloc-agent-ops[bot]", atype="Bot",
              files=("docs/x.md",), commits=[commit()], base_ref="release/x")
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("agent PRs must target main", out)

        def patch(body):
            return re.sub(
                r'    if author_type == \"Bot\" or is_agent\(login=author, user_id=author_id\):\n'
                r'        why.append\(f\"agent PR author \{author\}\"\)\n',
                "",
                body,
                count=1,
            )

        setup(ref="madgeniusblink/feat/x", author="fabricbloc-agent-ops[bot]", atype="Bot",
              files=("docs/x.md",), commits=[commit()], base_ref="release/x")
        code, out = run_gate_with_patch("agent-denied-paths", patch)
        self.assertEqual(code, 0, out)
        self.assertNotIn("agent PRs must target main", out)

    def test_mutation_lineage_ignores_bot_author_type(self):
        csha = "3" * 40
        pulls = [{"head": {"ref": "chore/index-regen-x"},
                  "user": {"login": "Madgeniusblink", "type": "Bot"}}]
        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",),
              commits=[commit(sha=csha)], base_ref="main",
              commit_pulls={csha: pulls})
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 1, out)

        def patch(body):
            return body.replace(') or user.get("type") == "Bot"', ")", 1)

        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",),
              commits=[commit(sha=csha)], base_ref="main",
              commit_pulls={csha: pulls})
        code, out = run_gate_with_patch("agent-review-of-record", patch)
        self.assertEqual(code, 0, out)

    def test_mutation_commit_pulls_bad_shape_passes_human_skip(self):
        csha = "0" * 40
        setup(ref="madgeniusblink/feat/x", files=(".github/workflows/a.yml",),
              commits=[commit(sha=csha)], base_ref="main")
        Fake.routes[f"/repos/BloclabsHQ/fabricbloc/commits/{csha}/pulls"] = {"not": "a list"}
        self.assertEqual(run("agent-denied-paths")[0], 1)

        def patch(body):
            body = body.replace(
                "    pulls = paginate(path, MAX_COMMIT_PULLS, fail_at_cap=True)",
                "    pulls = call(path)\n    if not isinstance(pulls, list):\n        return False",
                1,
            )
            validation = (
                "    for p in pulls:\n"
                "        if not isinstance(p, dict):\n"
                "            fail(f\"unexpected API shape for commits/{commit_sha[:12]}/pulls entry\")\n"
                "        head = p.get(\"head\")\n"
                "        if not isinstance(head, dict) or \"ref\" not in head:\n"
                "            fail(f\"commits/{commit_sha[:12]}/pulls entry missing head.ref; failing closed\")\n"
            )
            return body.replace(validation, "", 1)

        setup(ref="madgeniusblink/feat/x", files=(".github/workflows/a.yml",),
              commits=[commit(sha=csha)], base_ref="main")
        Fake.routes[f"/repos/BloclabsHQ/fabricbloc/commits/{csha}/pulls"] = {"not": "a list"}
        code, out = run_gate_with_patch("agent-denied-paths", patch)
        self.assertEqual(code, 0, out)

    def test_mutation_commit_pulls_continues_at_cap_passes_human_skip(self):
        csha = "4" * 40
        benign = {"head": {"ref": "madgeniusblink/feat/y"}, "user": {"login": "Madgeniusblink", "type": "User"}}
        agent_pull = {"head": {"ref": "agent/autonomous/fix/x-i1-y"},
                      "user": {"login": "Madgeniusblink", "type": "User"}}
        pulls = [benign] * 500 + [agent_pull]
        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",),
              commits=[commit(sha=csha)], base_ref="main",
              commit_pulls={csha: pulls})
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("pagination cap (500)", out)

        def patch(body):
            return body.replace(
                "pulls = paginate(path, MAX_COMMIT_PULLS, fail_at_cap=True)",
                "pulls = paginate(path, MAX_COMMIT_PULLS)",
                1,
            )

        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",),
              commits=[commit(sha=csha)], base_ref="main",
              commit_pulls={csha: pulls})
        code, out = run_gate_with_patch("agent-denied-paths", patch)
        self.assertEqual(code, 0, out)

    def test_mutation_coauthor_case_sensitive_trailer(self):
        msg = "feat: x\n\nco-authored-by: CURSOR AGENT <cursoragent@cursor.com>"
        setup(ref="madgeniusblink/feat/x", files=(".github/workflows/a.yml",),
              commits=[commit(message=msg)])
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)

        def patch(body):
            return body.replace(
                'COAUTHOR_TRAILER_RE = re.compile(r"^Co-authored-by:\\s*(.+)$", re.MULTILINE | re.IGNORECASE)',
                'COAUTHOR_TRAILER_RE = re.compile(r"^Co-authored-by:\\s*(.+)$", re.MULTILINE)',
                1,
            )

        setup(ref="madgeniusblink/feat/x", files=(".github/workflows/a.yml",),
              commits=[commit(message=msg)])
        code, out = run_gate_with_patch("agent-denied-paths", patch)
        self.assertEqual(code, 0, out)

    def test_mutation_coauthor_only_first_trailer(self):
        msg = ("feat: x\n\nCo-authored-by: Madgeniusblink <m@example.com>\n"
               "Co-authored-by: Cursor Agent <cursoragent@cursor.com>")
        setup(ref="madgeniusblink/feat/x", files=(".github/workflows/a.yml",),
              commits=[commit(message=msg)])
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)

        def patch(body):
            old = (
                "    for trailer in COAUTHOR_TRAILER_RE.findall(message):\n"
                "        if _coauthor_trailer_agent(trailer):\n"
                "            return True\n"
                "    return False"
            )
            new = (
                "    m = COAUTHOR_TRAILER_RE.search(message)\n"
                "    return bool(m and _coauthor_trailer_agent(m.group(1)))"
            )
            return body.replace(old, new, 1)

        setup(ref="madgeniusblink/feat/x", files=(".github/workflows/a.yml",),
              commits=[commit(message=msg)])
        code, out = run_gate_with_patch("agent-denied-paths", patch)
        self.assertEqual(code, 0, out)

    def test_mutation_creation_restricted_exclude_refs_heads_glob(self):
        import copy
        canon = copy.deepcopy(load_canon())
        inc = creation_restricted(canon)["conditions"]["ref_name"]["include"]
        if "refs/heads/**" in inc:
            inc.remove("refs/heads/**")
        with self.assertRaises(AssertionError):
            assert_creation_restricted_shape(canon)

    def test_gov_human_handles_match_canon_excludes(self):
        ns = load_gate_constants()
        exc = creation_restricted(load_canon())["conditions"]["ref_name"]["exclude"]
        for handle in ns["GOV_HUMAN_HANDLES"]:
            for typ in ns["HUMAN_BRANCH_TYPES"]:
                self.assertIn(f"refs/heads/{handle}/{typ}/**", exc)

if __name__ == "__main__":
    unittest.main(verbosity=1)
