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
REVIEWER_BOT = "fabricbloc-reviewer[bot]"
REVIEWER_BOT_ID = 337673700
VERDICT_BOT = "fabricbloc-verdict[bot]"
VERDICT_BOT_ID = 337980250
GITHUB_ACTIONS_APP_ID = 15368


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
    run = None
    for step in doc["jobs"][name]["steps"]:
        if isinstance(step.get("run"), str) and "<<'PY'" in step["run"]:
            run = step["run"]
            break
    if run is None:
        raise KeyError(f"no embedded PY step in {name}.yml")
    start = run.index("<<'PY'\n") + len("<<'PY'\n")
    return run[start:run.rindex("\nPY")]


MANIFEST = {"operators": {"members_expected": ["Madgeniusblink"]},
            "denied_paths": {"arch_0048_baseline": [
                ".github/workflows/", "decisions/", "architecture/decisions/",
            ],
                             "proposed_additions": ["ops/"]}}


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
        ref = q.get("ref", [None])[0]
        if ref:
            alt = Fake.routes.get(f"{key}?ref={ref}")
            if alt is not None:
                val = alt
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


def policy_repo_routes(extra_gate_owners_by_ref=None, canon_override=None):
    """Fake GitHub contents API for pinned policy JSON (never PR head)."""
    canon = canon_override or json.loads((ROOT / "rulesets" / "canon.json").read_text())
    gate_owners = json.loads((ROOT / "rulesets" / "gate-owners.json").read_text())
    reviewers = json.loads((ROOT / "rulesets" / "reviewers.json").read_text())
    base = "/repos/BloclabsHQ/fabricbloc-branch-policy/contents/"
    routes = {
        base + urllib.parse.quote("rulesets/canon.json"): json.dumps(canon),
        base + urllib.parse.quote("rulesets/gate-owners.json"): json.dumps(gate_owners),
        base + urllib.parse.quote("rulesets/reviewers.json"): json.dumps(reviewers),
    }
    for ref, body in (extra_gate_owners_by_ref or {}).items():
        routes[base + urllib.parse.quote("rulesets/gate-owners.json") + f"?ref={ref}"] = (
            json.dumps(body) if not isinstance(body, str) else body
        )
    return routes


def owner_approved_labeled(created_at="2026-10-05T11:00:00Z", login="madgeniusblink", user_id=42707764, **extra):
    ev = {
        "event": "labeled",
        "label": {"name": "owner-approved"},
        "actor": {"login": login, "id": user_id, "type": "User"},
        "created_at": created_at,
    }
    ev.update(extra)
    return ev


def push_activity_entry(head=HEAD, pushed_at="2026-10-05T10:30:00Z"):
    return {"after": head, "timestamp": pushed_at}


def setup(ref="madgeniusblink/feat/x", author="Madgeniusblink", atype="User", author_id=None,
          files=(".github/workflows/a.yml",), commits=None, reviews=(), manifest=MANIFEST, head=HEAD,
          changed=None, ncommits=None, renames=(), engine_config=None, base_ref="main",
          commit_pulls=None, repo="BloclabsHQ/fabricbloc",
          issue_labels=(), issue_events=(), head_commit_date="2026-10-05T10:00:00Z",
          push_activity=None, check_suites=(), policy_routes_extra=None):
    commits = [commit()] if commits is None else commits
    fl = []
    for f in files:
        if isinstance(f, dict):
            fl.append(f)
        else:
            fl.append({"filename": f})
    fl += [{"filename": n, "previous_filename": o} for o, n in renames]
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
        f"/repos/{repo}/issues/7/labels": [{"name": n} for n in issue_labels],
        f"/repos/{repo}/issues/7/events": list(issue_events),
        f"/repos/{repo}/commits/{head}": {
            "commit": {
                "committer": {"date": head_commit_date},
                "author": {"date": head_commit_date},
            }
        },
        f"/repos/{repo}/commits/{head}/check-suites": {
            "check_suites": [{"created_at": c} if isinstance(c, str) else c for c in check_suites]
        },
    }
    routes[f"/repos/{repo}/activity?ref={f'refs/heads/{ref}'}"] = (
        push_activity if push_activity is not None else []
    )
    extra = policy_routes_extra or {}
    routes.update(
        policy_repo_routes(
            extra_gate_owners_by_ref=extra.get("extra_gate_owners_by_ref"),
            canon_override=extra.get("canon_override"),
        )
    )
    commit_pulls = commit_pulls or {}
    for c in commits:
        sha = c.get("sha")
        if not sha:
            continue
        key = f"/repos/{repo}/commits/{sha}/pulls"
        if sha in commit_pulls:
            routes[key] = commit_pulls[sha]
        else:
            routes[key] = []
    Fake.routes = routes


def run(mode, repo="BloclabsHQ/fabricbloc", event_head=HEAD, gh_token="test", extra_env=None):
    env = dict(
        os.environ,
        MODE=mode,
        API=API,
        GH_TOKEN=gh_token,
        REPO=repo,
        PR="7",
        EVENT_HEAD_SHA=event_head,
        REPO_DEFAULT_BRANCH="main",
    )
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


def creation_restricted(canon, repository="fabricbloc"):
    return next(
        r for r in canon["repository_rulesets"]
        if r["name"] == "canon-branch-creation-restricted" and r.get("_repository") == repository
    )


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


def assert_creation_restricted_shape(canon, repository="fabricbloc", extra_required_excludes=()):
    rs = creation_restricted(canon, repository=repository)
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
    for path in extra_required_excludes:
        assert path in exc, f"missing required exclude {path} for {repository}"


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


# canon-push-protected-paths patterns not mirrored in FLOOR_DENIED / FLOOR_PROVIDER_CONTROL.
# Keep empty unless a pattern is intentionally gated only at push ruleset layer (document why).
FLOOR_DENIED_CANON_EXCEPTIONS = ()


def canon_push_protected_path_patterns(canon=None):
    if canon is None:
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
    rs = next(
        r
        for r in canon["repository_rulesets"]
        if r.get("_repository") == "fabricbloc" and r["name"] == "canon-push-protected-paths"
    )
    return rs["rules"][0]["parameters"]["restricted_file_paths"]


def _canon_pattern_probe_paths(pattern):
    p = (pattern or "").replace("\\", "/")
    if p.endswith("/**/*"):
        root = p[: -len("/**/*")]
        probes = [f"{root}/__probe__", f"{root}/nested/__probe__"]
    elif p.endswith("*"):
        base = p[:-1]
        probes = [base, base + "suffix"]
    else:
        probes = [p]
    probes.append(probes[0].swapcase())
    return probes


def assert_canon_push_paths_covered_by_floor():
    ns = load_gate_constants()
    match_entry = ns["path_matches_denied_entry"]
    match_glob = ns["path_matches_glob_ci"]
    floor = list(ns["FLOOR_DENIED"]) + list(ns["FLOOR_PROVIDER_CONTROL"])
    missing = []
    for pattern in canon_push_protected_path_patterns():
        if pattern in FLOOR_DENIED_CANON_EXCEPTIONS:
            continue
        covered = False
        classify = ns["classify_agent_path_tier"]
        for probe in _canon_pattern_probe_paths(pattern):
            if not match_glob(probe, pattern):
                continue
            if any(match_entry(probe, entry) for entry in floor):
                covered = True
                break
            if classify(probe, list(ns["FLOOR_DENIED"])) in ("cris_only", "verdict_eligible"):
                covered = True
                break
        if not covered:
            missing.append(pattern)
    if missing:
        raise AssertionError(
            "canon-push-protected-paths pattern(s) not covered by FLOOR_DENIED or "
            f"FLOOR_PROVIDER_CONTROL (add to embedded_gate.py or FLOOR_DENIED_CANON_EXCEPTIONS): "
            + ", ".join(missing)
        )


def run_gate_with_patch(mode, patch_src, extra_env=None):
    body = patch_src(embedded(mode))
    env = dict(
        os.environ,
        MODE=mode,
        API=API,
        GH_TOKEN="test",
        REPO="BloclabsHQ/fabricbloc",
        PR="7",
        EVENT_HEAD_SHA=HEAD,
        REPO_DEFAULT_BRANCH="main",
    )
    if extra_env:
        env.update(extra_env)
    p = subprocess.run([sys.executable, "-c", body], env=env, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout + p.stderr


def run_with_reviewer_bots(mode, bots, **kwargs):
    pairs = ", ".join(repr((str(b[0]), int(b[1]))) for b in bots)
    body = embedded(mode)
    body = re.sub(
        r"^REVIEWER_APP_BOTS = \{[^\n]*\}",
        f"REVIEWER_APP_BOTS = {{{pairs}}}",
        body,
        count=1,
        flags=re.M,
    )
    env = dict(
        os.environ,
        MODE=mode,
        API=API,
        GH_TOKEN="test",
        REPO="BloclabsHQ/fabricbloc",
        PR="7",
        EVENT_HEAD_SHA=HEAD,
        REPO_DEFAULT_BRANCH="main",
    )
    env.update(kwargs.get("env", {}))
    p = subprocess.run([sys.executable, "-c", body], env=env, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout + p.stderr


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

    def test_agent_denied_paths_triggers_include_label_events(self):
        doc = yaml.safe_load((WF / "agent-denied-paths.yml").read_text())
        on = doc.get("on") or doc.get(True) or {}
        types = (on.get("pull_request") or {}).get("types") or []
        self.assertIn("labeled", types)
        self.assertIn("unlabeled", types)

    def test_cris_only_without_owner_approval_fails(self):
        setup(files=(".github/workflows/ci.yml",), **AGENT)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("Cris-only", out)

    def test_cris_only_owner_approved_label_passes_denied_paths(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(),),
            push_activity=[push_activity_entry(pushed_at="2026-10-05T10:30:00Z")],
            head_commit_date="2001-01-01T00:00:00Z",
            **AGENT,
        )
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertIn("AG-06 owner override", out)

    def test_owner_approval_label_before_push_fails(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(created_at="2026-10-05T11:00:00Z"),),
            push_activity=[push_activity_entry(pushed_at="2026-10-05T11:30:00Z")],
            **AGENT,
        )
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("not after head push", out)

    def test_owner_approval_backdated_commit_date_irrelevant_push_wins(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(created_at="2026-10-05T11:00:00Z"),),
            push_activity=[push_activity_entry(pushed_at="2026-10-05T10:30:00Z")],
            head_commit_date="2001-01-01T00:00:00Z",
            **AGENT,
        )
        self.assertEqual(run("agent-denied-paths")[0], 0)

    def test_owner_approval_no_push_time_fails_closed(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(),),
            push_activity=[],
            check_suites=(),
            **AGENT,
        )
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("no repository activity push timestamp", out)

    def test_owner_approval_check_suite_fallback_removed(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(created_at="2026-10-05T11:00:00Z"),),
            push_activity=[],
            check_suites=("2026-10-05T10:30:00Z",),
            **AGENT,
        )
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("no repository activity push timestamp", out)

    def test_cross_branch_check_suite_predate_does_not_bypass_activity_miss(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(created_at="2026-10-05T12:00:00Z"),),
            push_activity=[],
            check_suites=("2026-10-05T09:00:00Z",),
            **AGENT,
        )
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_activity_entry_requires_timestamp_field(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(),),
            push_activity=[{"after": HEAD, "created_at": "2026-10-05T10:30:00Z"}],
            **AGENT,
        )
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_owner_approval_wrong_actor_fails(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(login="notcris", user_id=1),),
            push_activity=[push_activity_entry()],
            **AGENT,
        )
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_owner_approval_wrong_user_id_e2e(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(user_id=1),),
            push_activity=[push_activity_entry()],
            **AGENT,
        )
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("not a configured gate owner", out)

    def test_owner_approval_bot_actor_fails(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(
                login="madgeniusblink[bot]", user_id=42707764, type="Bot",
            ),),
            push_activity=[push_activity_entry()],
            **AGENT,
        )
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("bot", out.lower())

    def test_owner_approval_github_app_event_fails_when_allowlist_empty(self):
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        pin = "cafebabecafebabecafebabecafebabecafebabe"
        canon.setdefault("pins", {})["agent_gates_sha"] = pin
        owners_cfg = json.loads((ROOT / "rulesets" / "gate-owners.json").read_text())
        owners_cfg["allowed_label_apps"] = []
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(
                performed_via_github_app={"id": 999, "slug": "evil-app", "name": "Evil"},
            ),),
            push_activity=[push_activity_entry()],
            policy_routes_extra={
                "extra_gate_owners_by_ref": {pin: owners_cfg},
                "canon_override": canon,
            },
            **AGENT,
        )
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("allowed_label_apps", out)

    def test_gate_owners_json_seeds_cursor_github_app_id(self):
        cfg = json.loads((ROOT / "rulesets" / "gate-owners.json").read_text())
        self.assertIn(1210556, cfg.get("allowed_label_apps") or [])

    def test_owner_approval_allowed_github_app_passes(self):
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        pin = "cafebabecafebabecafebabecafebabecafebabe"
        canon.setdefault("pins", {})["agent_gates_sha"] = pin
        owners_cfg = json.loads((ROOT / "rulesets" / "gate-owners.json").read_text())
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(
                performed_via_github_app={"id": 1210556, "slug": "cursor"},
            ),),
            push_activity=[push_activity_entry()],
            policy_routes_extra={
                "extra_gate_owners_by_ref": {pin: owners_cfg},
                "canon_override": canon,
            },
            **AGENT,
        )
        self.assertEqual(run("agent-denied-paths")[0], 0)
        self.assertEqual(run("agent-review-of-record")[0], 0)

    def test_owner_approval_cursor_app_non_owner_fails(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(
                login="notcris",
                user_id=1,
                performed_via_github_app={"id": 1210556, "slug": "cursor"},
            ),),
            push_activity=[push_activity_entry()],
            **AGENT,
        )
        for wf in ("agent-denied-paths", "agent-review-of-record"):
            code, out = run(wf)
            self.assertEqual(code, 1, out)
            self.assertIn("not a configured gate owner", out)

    def test_owner_approval_cursor_app_wrong_user_id_fails(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(
                login="madgeniusblink",
                user_id=1,
                performed_via_github_app={"id": 1210556, "slug": "cursor"},
            ),),
            push_activity=[push_activity_entry()],
            **AGENT,
        )
        for wf in ("agent-denied-paths", "agent-review-of-record"):
            code, out = run(wf)
            self.assertEqual(code, 1, out)
            self.assertIn("not a configured gate owner", out)

    def test_owner_approval_disallowed_github_app_fails(self):
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        pin = "cafebabecafebabecafebabecafebabecafebabe"
        canon.setdefault("pins", {})["agent_gates_sha"] = pin
        owners_cfg = json.loads((ROOT / "rulesets" / "gate-owners.json").read_text())
        owners_cfg["allowed_label_apps"] = ["cursor"]
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(
                performed_via_github_app={"id": 999, "slug": "other-app"},
            ),),
            push_activity=[push_activity_entry()],
            policy_routes_extra={
                "extra_gate_owners_by_ref": {pin: owners_cfg},
                "canon_override": canon,
            },
            **AGENT,
        )
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_non_owner_relabel_after_owner_fails(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(
                owner_approved_labeled(created_at="2026-10-05T11:00:00Z"),
                owner_approved_labeled(
                    created_at="2026-10-05T11:05:00Z", login="notcris", user_id=1,
                ),
            ),
            push_activity=[push_activity_entry()],
            **AGENT,
        )
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_owner_unlabeled_revokes_pass(self):
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(
                owner_approved_labeled(),
                {
                    "event": "unlabeled",
                    "label": {"name": "owner-approved"},
                    "actor": {"login": "madgeniusblink", "id": 42707764, "type": "User"},
                    "created_at": "2026-10-05T11:05:00Z",
                },
            ),
            push_activity=[push_activity_entry()],
            **AGENT,
        )
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_review_of_record_owner_approval_passes_without_github_approve(self):
        setup(
            files=(".github/workflows/ci.yml",),
            reviews=[],
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(),),
            push_activity=[push_activity_entry()],
            **AGENT,
        )
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 0, out)
        self.assertIn("owner override satisfies review-of-record", out)

    def test_review_of_record_owner_label_with_changes_requested_still_fails(self):
        setup(
            files=(".github/workflows/ci.yml",),
            reviews=[approve(), approve("other", state="CHANGES_REQUESTED")],
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(),),
            push_activity=[push_activity_entry()],
            **AGENT,
        )
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 1, out)
        self.assertIn("CHANGES_REQUESTED", out)

    def test_owner_label_does_not_clear_projection_hard_fail(self):
        setup(
            files=({"filename": "docs/x.md", "patch": "+run git submodule update --init\n"},),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(),),
            push_activity=[push_activity_entry()],
            **AGENT,
        )
        env = dict(os.environ, PROJECTION_ENFORCE="fail")
        p = subprocess.run(
            [sys.executable, "-c", embedded("agent-denied-paths")],
            env={**env, "MODE": "agent-denied-paths", "API": API, "GH_TOKEN": "test",
                 "REPO": "BloclabsHQ/fabricbloc", "PR": "7", "EVENT_HEAD_SHA": HEAD,
                 "REPO_DEFAULT_BRANCH": "main"},
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("projection violation", p.stdout + p.stderr)

    def test_owner_label_does_not_clear_provider_hard_fail(self):
        setup(
            files=(".cursor/rules.json",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(),),
            push_activity=[push_activity_entry()],
            **AGENT,
        )
        env = dict(os.environ, PROVIDER_CONTROL_ENFORCE="fail")
        p = subprocess.run(
            [sys.executable, "-c", embedded("agent-denied-paths")],
            env={**env, "MODE": "agent-denied-paths", "API": API, "GH_TOKEN": "test",
                 "REPO": "BloclabsHQ/fabricbloc", "PR": "7", "EVENT_HEAD_SHA": HEAD,
                 "REPO_DEFAULT_BRANCH": "main"},
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("provider control", p.stdout + p.stderr)

    def test_gate_owners_json_read_from_pin_not_pr_head(self):
        pin = "cafebabecafebabecafebabecafebabecafebabe"
        evil = {
            "owner_approved_label": "owner-approved",
            "gate_owners": [{"login": "evil", "user_id": 1}],
        }
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        canon.setdefault("pins", {})["agent_gates_sha"] = pin
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(),),
            push_activity=[push_activity_entry()],
            policy_routes_extra={
                "extra_gate_owners_by_ref": {
                    pin: json.loads((ROOT / "rulesets" / "gate-owners.json").read_text()),
                    "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef": evil,
                },
                "canon_override": canon,
            },
            **AGENT,
        )
        self.assertEqual(run("agent-denied-paths")[0], 0)

    def test_missing_gate_owners_json_not_hard_fail(self):
        routes = policy_repo_routes()
        base = "/repos/BloclabsHQ/fabricbloc-branch-policy/contents/"
        key = base + urllib.parse.quote("rulesets/gate-owners.json")
        routes.pop(key, None)
        pin = json.loads(routes[base + urllib.parse.quote("rulesets/canon.json")])
        pin_ref = pin.get("pins", {}).get("agent_gates_sha") or "main"
        routes.pop(f"{key}?ref={pin_ref}", None)
        setup(
            files=(".github/workflows/ci.yml",),
            issue_labels=("owner-approved",),
            issue_events=(owner_approved_labeled(),),
            push_activity=[push_activity_entry()],
            **AGENT,
        )
        Fake.routes.pop(key, None)
        Fake.routes.pop(f"{key}?ref={pin_ref}", None)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("gate-owners.json missing", out)
        self.assertNotIn("missing policy file", out)

    def test_gate_owner_identity_requires_login_and_user_id(self):
        ns = load_gate_constants()
        owners = [{"login": "madgeniusblink", "user_id": 42707764}]
        self.assertTrue(
            ns["gate_owner_identity_matches"](
                {"login": "Madgeniusblink", "id": 42707764}, owners
            )
        )
        self.assertFalse(
            ns["gate_owner_identity_matches"](
                {"login": "madgeniusblink", "id": 1}, owners
            )
        )
        cfg = {"allowed_label_apps": []}
        ok, _ = ns["gate_owner_label_actor_ok"](
            {"login": "madgeniusblink", "id": 42707764, "type": "User"}, {}, cfg
        )
        self.assertTrue(ok)

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

    def test_cursor_and_claude_provider_paths_warn_by_default(self):
        setup(files=(".cursor/environment.json",), **AGENT)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertIn("::warning", out)
        self.assertIn("AG-04", out)
        setup(files=(".claude/settings.json",), **AGENT)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertIn("provider control path", out)

    def test_cursor_and_claude_provider_paths_fail_when_enforced(self):
        setup(files=(".cursor/environment.json",), **AGENT)
        env = dict(os.environ, PROVIDER_CONTROL_ENFORCE="fail")
        p = subprocess.run(
            [sys.executable, "-c", embedded("agent-denied-paths")],
            env={**env, "MODE": "agent-denied-paths", "API": API, "GH_TOKEN": "test",
                 "REPO": "BloclabsHQ/fabricbloc", "PR": "7", "EVENT_HEAD_SHA": HEAD,
                 "REPO_DEFAULT_BRANCH": "main"},
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("provider control path", p.stdout + p.stderr)

    def test_floor_workflows_still_fail_without_provider_switch(self):
        setup(files=(".github/workflows/evil.yml",), **AGENT)
        self.assertEqual(run("agent-denied-paths")[0], 1)

    def test_proposed_ops_not_denied_until_include_proposed(self):
        setup(files=("ops/deploy/x.sh",), **AGENT)
        self.assertEqual(run("agent-denied-paths")[0], 0)

    def test_projection_ignores_removed_context_lines(self):
        setup(
            files=({
                "filename": "docs/projection.md",
                "patch": (
                    " context line\n"
                    "-run git submodule update --init\n"
                    "+plain docs only\n"
                ),
            },),
            **AGENT,
        )
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertNotIn("AG-05", out)

    def test_projection_warn_does_not_fail(self):
        setup(
            files=({
                "filename": "docs/projection.md",
                "patch": "+see ../../fabricbloc/skills/foo for copy\n",
            },),
            **AGENT,
        )
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertIn("::warning", out)
        self.assertIn("AG-05", out)

    def test_no_patch_emits_warning(self):
        setup(files=({"filename": "docs/binary.png"},), **AGENT)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertIn("no diff patch", out)

    def test_no_patch_denied_fail_mode(self):
        setup(
            files=({"filename": ".github/workflows/a.yml"},),
            **AGENT,
        )
        env = dict(os.environ, PROJECTION_ENFORCE="fail")
        p = subprocess.run(
            [sys.executable, "-c", embedded("agent-denied-paths")],
            env={**env, "MODE": "agent-denied-paths", "API": API, "GH_TOKEN": "test",
                 "REPO": "BloclabsHQ/fabricbloc", "PR": "7", "EVENT_HEAD_SHA": HEAD,
                 "REPO_DEFAULT_BRANCH": "main"},
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("no diff patch", p.stdout + p.stderr)

    def test_projection_enforce_invalid_fails_loud(self):
        setup(files=("docs/x.md",), **AGENT)
        env = dict(os.environ, PROJECTION_ENFORCE="maybe")
        p = subprocess.run(
            [sys.executable, "-c", embedded("agent-denied-paths")],
            env={**env, "MODE": "agent-denied-paths", "API": API, "GH_TOKEN": "test",
                 "REPO": "BloclabsHQ/fabricbloc", "PR": "7", "EVENT_HEAD_SHA": HEAD,
                 "REPO_DEFAULT_BRANCH": "main"},
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("PROJECTION_ENFORCE", p.stdout + p.stderr)

    def test_mutation_ag04_skips_denied_path_check(self):
        setup(files=(".github/workflows/evil.yml",), **AGENT)
        self.assertEqual(run("agent-denied-paths")[0], 1)

        def patch(body):
            return body.replace(
                "        if cris_only:\n            fail(f\"{len(cris_only)} Cris-only denied path(s)\")",
                "        if False and cris_only:\n            fail(f\"{len(cris_only)} Cris-only denied path(s)\")",
                1,
            )

        setup(files=(".github/workflows/evil.yml",), **AGENT)
        code, out = run_gate_with_patch("agent-denied-paths", patch)
        self.assertEqual(code, 0, out)

    def test_mutation_ag05_scans_full_patch_not_added_only(self):
        setup(
            files=({
                "filename": "docs/projection.md",
                "patch": "-run git submodule update --init\n+safe added line\n",
            },),
            **AGENT,
        )
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertNotIn("AG-05", out)

        def patch(body):
            return body.replace(
                "            added = projection_added_text(patch)\n"
                "            if not added:\n"
                "                continue\n"
                "            for pat, msg in PROJECTION_PATTERNS:\n"
                "                if pat.search(added):",
                "            for pat, msg in PROJECTION_PATTERNS:\n"
                "                if pat.search(patch):",
                1,
            )

        setup(
            files=({
                "filename": "docs/projection.md",
                "patch": "-run git submodule update --init\n+safe added line\n",
            },),
            **AGENT,
        )
        code, out = run_gate_with_patch("agent-denied-paths", patch)
        self.assertEqual(code, 0, out)
        self.assertIn("AG-05", out)

    def test_projection_fail_mode(self):
        setup(
            files=({"filename": "docs/projection.md",
                    "patch": "+run git submodule update --init\n"},),
            **AGENT,
        )
        env = dict(os.environ, PROJECTION_ENFORCE="fail")
        p = subprocess.run(
            [sys.executable, "-c", embedded("agent-denied-paths")],
            env={**env, "MODE": "agent-denied-paths", "API": API, "GH_TOKEN": "test",
                 "REPO": "BloclabsHQ/fabricbloc", "PR": "7", "EVENT_HEAD_SHA": HEAD,
                 "REPO_DEFAULT_BRANCH": "main"},
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)

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
                "BloclabsHQ/fabric-wallet",
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

    def test_review_file_count_mismatch_fails_before_auto_approve(self):
        setup(files=("docs/guide.md",), changed=99, reviews=[], **AGENT)
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 1, out)
        self.assertIn("file count mismatch", out)

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

    def test_verdict_app_approve_never_qualifies_review_of_record(self):
        ns = load_gate_constants()
        review = {
            "state": "APPROVED",
            "commit_id": HEAD,
            "user": {"login": VERDICT_BOT, "id": VERDICT_BOT_ID},
            "body": reviewer_body(),
        }
        allow = {"Madgeniusblink", VERDICT_BOT}
        self.assertFalse(
            ns["approval_qualifies"](review, HEAD, allow, set(), ns["REVIEWER_APP_BOTS"])
        )
        cfg = (
            f"human: ['Madgeniusblink']\n"
            f"ai_reviewers: ['{VERDICT_BOT}']\n"
        )
        setup(
            files=("docs/x.md",),
            reviews=[approve(VERDICT_BOT, body=reviewer_body(), user_id=VERDICT_BOT_ID)],
            engine_config=cfg,
            **AGENT,
        )
        self.assertEqual(run("agent-review-of-record")[0], 1)

    def test_humans_from_manifest_empty_floors_gov_handles(self):
        ns = load_gate_constants()
        self.assertEqual(
            ns["humans_from_manifest"]({}),
            set(ns["GOV_HUMAN_HANDLES"]),
        )
        self.assertEqual(
            ns["humans_from_manifest"]({"operators": {"members_expected": []}}),
            set(ns["GOV_HUMAN_HANDLES"]),
        )

    def test_review_of_record_allowlist_empty_manifest_includes_reviewer_bot(self):
        ns = load_gate_constants()
        humans = ns["humans_from_manifest"]({})
        allow = ns["review_of_record_allowlist"](humans, None, ns["REVIEWER_APP_BOTS"])
        self.assertIn(ns["GOV_HUMAN_HANDLES"][0], allow)
        self.assertIn(REVIEWER_BOT, allow)

    def test_review_of_record_allowlist_empty_inputs_stays_empty(self):
        ns = load_gate_constants()
        self.assertEqual(ns["review_of_record_allowlist"](set(), None, set()), set())

    def test_context_empty_manifest_review_not_blocked_on_allowlist(self):
        setup(
            files=("docs/x.md",),
            manifest={},
            repo="BloclabsHQ/context",
            reviews=[],
            **AGENT,
        )
        code, out = run("agent-review-of-record", repo="BloclabsHQ/context")
        self.assertEqual(code, 1, out)
        self.assertNotIn("no reviewer allowlist", out)

    def test_gate_workflows_checks_write_permission(self):
        denied = yaml.safe_load((WF / "agent-denied-paths.yml").read_text()).get("permissions") or {}
        self.assertEqual(denied.get("checks"), "write")
        ror_doc = yaml.safe_load((WF / "agent-review-of-record.yml").read_text())
        gate_job = (ror_doc.get("jobs") or {}).get("agent-review-of-record") or {}
        gate_perms = gate_job.get("permissions") or {}
        self.assertEqual(gate_perms.get("checks"), "write")
        mint_job = (ror_doc.get("jobs") or {}).get("reviewer-app-auto-approve") or {}
        self.assertEqual(mint_job.get("environment"), "reviewer")
        mint_perms = mint_job.get("permissions") or {}
        self.assertEqual(mint_perms.get("issues"), "write")

    def test_review_of_record_split_pull_request_and_target(self):
        doc = yaml.safe_load((WF / "agent-review-of-record.yml").read_text())
        on = doc.get("on") or doc.get(True) or {}
        for key in ("pull_request", "pull_request_target"):
            types = (on.get(key) or {}).get("types") or []
            self.assertIn("edited", types, key)
            self.assertIn("labeled", types, key)
            self.assertIn("unlabeled", types, key)
        gate = (doc.get("jobs") or {}).get("agent-review-of-record") or {}
        self.assertNotIn("environment", gate)
        gate_if = gate.get("if") or ""
        self.assertIn("pull_request", gate_if)
        mint = (doc.get("jobs") or {}).get("reviewer-app-auto-approve") or {}
        self.assertEqual(mint.get("environment"), "reviewer")
        mint_if = mint.get("if") or ""
        self.assertIn("pull_request_target", mint_if)
        self.assertIn("owner-approved", mint_if)
        self.assertIn("issue_comment", mint_if)
        self.assertIn(VERDICT_BOT, mint_if)
        issue_types = (on.get("issue_comment") or {}).get("types") or []
        self.assertIn("created", issue_types)
        self.assertGreaterEqual(int(mint.get("timeout-minutes") or 0), 10)
        gate_step = gate["steps"][0]
        gate_env = gate_step.get("env") or {}
        self.assertEqual(gate_env.get("ROR_JOB"), "gate")
        self.assertNotIn("REVIEWER_APP_TOKEN", gate_env)
        self.assertNotIn("REVIEWER_APP_PRIVATE_KEY", gate_env)
        self.assertNotIn("secrets.", str(gate_step))
        mint_run = [s for s in mint["steps"] if s.get("env", {}).get("ROR_JOB") == "mint"][0]
        self.assertIn("REVIEWER_APP_TOKEN", mint_run["env"])

    def test_reviewer_env_docs_forbid_refs_pull_deployment_rules(self):
        text = (ROOT / "docs" / "REVIEWER-IDENTITY.md").read_text()
        low = text.lower()
        self.assertIn("refs/pull", text)
        self.assertTrue(
            "refs/pull" in text
            and (
                "may not match" in low
                or "must not match" in low
                or "no environment deployment rule may match" in low
            ),
            "docs must forbid refs/pull/* deployment rules",
        )

    def test_reviewer_app_approval_at_head_valid_body_passes(self):
        cfg = f"human: ['Madgeniusblink']\nai_reviewers: ['{REVIEWER_BOT}']\n"
        setup(files=("docs/x.md",),
              reviews=[approve(REVIEWER_BOT, body=reviewer_body(), user_id=REVIEWER_BOT_ID)],
              engine_config=cfg, **AGENT)
        self.assertEqual(run("agent-review-of-record")[0], 0)

    def test_reviewer_app_wrong_numeric_id_fails(self):
        cfg = f"human: ['Madgeniusblink']\nai_reviewers: ['{REVIEWER_BOT}']\n"
        setup(files=("docs/x.md",),
              reviews=[approve(REVIEWER_BOT, body=reviewer_body(), user_id=REVIEWER_BOT_ID + 1)],
              engine_config=cfg, **AGENT)
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 1, out)

    def test_reviewer_app_wrong_login_right_id_fails(self):
        cfg = f"human: ['Madgeniusblink']\nai_reviewers: ['{REVIEWER_BOT}']\n"
        setup(files=("docs/x.md",),
              reviews=[approve("spoof-reviewer[bot]", body=reviewer_body(), user_id=REVIEWER_BOT_ID)],
              engine_config=cfg, **AGENT)
        self.assertEqual(run("agent-review-of-record")[0], 1)

    def test_reviewer_app_missing_sha_in_body_fails(self):
        cfg = f"human: ['Madgeniusblink']\nai_reviewers: ['{REVIEWER_BOT}']\n"
        setup(files=("docs/x.md",),
              reviews=[approve(REVIEWER_BOT, body="approval-ref: cli:abcdef12", user_id=REVIEWER_BOT_ID)],
              engine_config=cfg, **AGENT)
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 1, out)
        self.assertIn("lacks full 40-char head SHA", out)

    def test_reviewer_app_missing_approval_ref_fails(self):
        cfg = f"human: ['Madgeniusblink']\nai_reviewers: ['{REVIEWER_BOT}']\n"
        setup(files=("docs/x.md",),
              reviews=[approve(REVIEWER_BOT, body=HEAD, user_id=REVIEWER_BOT_ID)],
              engine_config=cfg, **AGENT)
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 1, out)
        self.assertIn("approval-ref", out)

    def test_reviewer_app_stale_commit_id_fails(self):
        cfg = f"human: ['Madgeniusblink']\nai_reviewers: ['{REVIEWER_BOT}']\n"
        setup(files=("docs/x.md",),
              reviews=[approve(REVIEWER_BOT, sha=OLD, body=reviewer_body(OLD), user_id=REVIEWER_BOT_ID)],
              engine_config=cfg, **AGENT)
        self.assertEqual(run("agent-review-of-record")[0], 1)

    def test_reviewer_app_never_human_skip(self):
        ns = load_gate_constants()
        bots = ns["REVIEWER_APP_BOTS"]
        humans = {"Madgeniusblink", REVIEWER_BOT}
        commits = [commit("Madgeniusblink")]
        applies, why = ns["gate_applies"](
            "madgeniusblink/feat/x", REVIEWER_BOT, "User", REVIEWER_BOT_ID,
            commits, "dev", "main", humans, set(), bots)
        self.assertTrue(applies)
        self.assertFalse(any("GOV-0022 human ref owned" in w for w in why))

    def test_unparseable_ai_reviewers_fails_closed(self):
        cfg = "human: ['Madgeniusblink']\nai_reviewers:\n  - bot\n"
        setup(files=("docs/x.md",), engine_config=cfg, **AGENT)
        code, out = run("agent-review-of-record")
        self.assertEqual(code, 1, out)
        self.assertIn("ai_reviewers", out)

    def test_finding_c_agent_pr_base_release_fails(self):
        setup(files=("docs/x.md",), base_ref="release/x", repo="BloclabsHQ/fabricbloc", **AGENT)
        code, out = run("agent-denied-paths", repo="BloclabsHQ/fabricbloc")
        self.assertEqual(code, 1, out)
        self.assertIn("agent PRs must target main", out)

    def test_fabricbloc_default_main_agent_base_release_rejected(self):
        setup(files=("docs/x.md",), base_ref="release/x", repo="BloclabsHQ/fabricbloc", **AGENT)
        code, out = run(
            "agent-denied-paths",
            repo="BloclabsHQ/fabricbloc",
            extra_env={"REPO_DEFAULT_BRANCH": "main"},
        )
        self.assertEqual(code, 1, out)
        self.assertIn("agent PRs must target main", out)

    def test_finding_c_agent_pr_base_main_follows_normal_flow(self):
        setup(files=("docs/x.md",), base_ref="main", **AGENT)
        self.assertEqual(run("agent-denied-paths")[0], 0)

    def test_keyflo_default_dev_agent_base_dev_allowed(self):
        setup(files=("docs/x.md",), base_ref="dev", repo="BloclabsHQ/keyflo-session-issuer", **AGENT)
        env = {"REPO_DEFAULT_BRANCH": "dev"}
        self.assertEqual(run("agent-denied-paths", repo="BloclabsHQ/keyflo-session-issuer", extra_env=env)[0], 0)

    def test_keyflo_default_dev_agent_base_main_allowed(self):
        setup(files=("docs/x.md",), base_ref="main", repo="BloclabsHQ/keyflo-session-issuer", **AGENT)
        env = {"REPO_DEFAULT_BRANCH": "dev"}
        self.assertEqual(run("agent-denied-paths", repo="BloclabsHQ/keyflo-session-issuer", extra_env=env)[0], 0)

    def test_keyflo_default_dev_agent_base_release_rejected(self):
        setup(files=("docs/x.md",), base_ref="release/x", repo="BloclabsHQ/keyflo-session-issuer", **AGENT)
        env = {"REPO_DEFAULT_BRANCH": "dev"}
        code, out = run("agent-denied-paths", repo="BloclabsHQ/keyflo-session-issuer", extra_env=env)
        self.assertEqual(code, 1, out)
        self.assertIn("agent PRs must target main", out)

    def test_context_default_main_agent_base_dev_rejected(self):
        setup(files=("docs/x.md",), base_ref="dev", repo="BloclabsHQ/context", **AGENT)
        code, out = run("agent-denied-paths", repo="BloclabsHQ/context")
        self.assertEqual(code, 1, out)
        self.assertIn("agent PRs must target main", out)

    def test_finding_c_human_pr_base_release_not_failed_by_base_rule(self):
        setup(ref="madgeniusblink/feat/x", files=("docs/x.md",), base_ref="release/x")
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertNotIn("agent PRs must target main", out)

    def test_canon_agent_gates_has_no_bypass_actors(self):
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        self.assertEqual(gates.get("bypass_actors"), [])

    def test_canon_agent_gates_pull_request_review_count(self):
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        pr_rules = [r for r in gates.get("rules") or [] if r.get("type") == "pull_request"]
        self.assertEqual(pr_rules, [], "live-matching apply body must be workflows-only")
        held_pr = [r for r in gates.get("_held_rules") or [] if r.get("type") == "pull_request"]
        self.assertEqual(len(held_pr), 1, held_pr)
        params = held_pr[0]["parameters"]
        self.assertEqual(params.get("required_approving_review_count"), 1)
        self.assertNotIn("allowed_merge_methods", params)
        self.assertIn("_held_note", gates)

    def test_canon_agent_gates_live_ref_include(self):
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        self.assertNotIn("_bootstrap_ref_include", gates)
        self.assertNotIn("_post_rollout_ref_include", gates)
        self.assertEqual(
            gates["conditions"]["ref_name"]["include"],
            [
                "~DEFAULT_BRANCH",
                "refs/heads/main",
                "refs/heads/release/**",
                "refs/heads/prod/**",
            ],
        )

    def test_validate_canon_live_ref_include_rejects_bootstrap(self):
        from validate_canon import agent_gates_live_ref_errors

        canon = copy.deepcopy(load_canon())
        self.assertEqual(agent_gates_live_ref_errors(canon), [])
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        gates["_bootstrap_ref_include"] = ["refs/heads/f6-gate-test"]
        self.assertTrue(agent_gates_live_ref_errors(canon))

    def test_canon_agent_gates_repository_name_matches_target_repos(self):
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        short = set(gates["conditions"]["repository_name"]["include"])
        expected = {r.split("/", 1)[1] for r in load_gate_constants()["TARGET_REPOS"]}
        self.assertEqual(short, expected)

    def test_canon_wallet_green_ci_contract(self):
        canon = json.loads((ROOT / "rulesets" / "canon.json").read_text())
        rs = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-wallet-green-ci")
        self.assertNotIn("_founder_decision", rs)
        self.assertIn("_apply_after", rs)
        self.assertEqual(rs.get("bypass_actors"), [])
        self.assertEqual(
            rs["conditions"]["repository_name"]["include"],
            ["fabric-wallet"],
        )
        self.assertEqual(
            rs["conditions"]["ref_name"]["include"],
            ["refs/heads/dev", "refs/heads/main"],
        )
        pr_rule = next(r for r in rs["rules"] if r["type"] == "pull_request")
        self.assertEqual(pr_rule["parameters"]["required_approving_review_count"], 0)
        checks_rule = next(r for r in rs["rules"] if r["type"] == "required_status_checks")
        params = checks_rule["parameters"]
        self.assertTrue(params["strict_required_status_checks_policy"])
        contexts = [c["context"] for c in params["required_status_checks"]]
        self.assertEqual(contexts, ["Lint", "Security Scan", "Test", "Migration Checksum"])
        for entry in params["required_status_checks"]:
            self.assertEqual(entry["integration_id"], 15368)

    def test_decisions_wallet_green_ci_yes(self):
        text = (ROOT / "DECISIONS.md").read_text()
        self.assertRegex(text, r"\*\*WALLET-GREEN-CI:\*\*.*\*\*\[Yes\]\*\*", re.S)

    def test_canon_push_protected_paths_covered_by_floor_denied(self):
        assert_canon_push_paths_covered_by_floor()

    def test_agent_denied_repair_decision_script(self):
        setup(files=("scripts/repair-decision-probe.py",), **AGENT)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("denied path", out)

    def test_agent_denied_repair_decision_rename_old_path(self):
        setup(
            renames=[("scripts/repair-decision-old.py", "scripts/other.py")],
            **AGENT,
        )
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("denied path", out)

    def test_verdict_eligible_adr_passes_denied_paths(self):
        setup(files=("architecture/decisions/ARCH-0045.md",), **AGENT)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertIn("Verdict-eligible", out)

    def test_verdict_eligible_engine_test_md_passes(self):
        setup(
            files=(
                "agents/runtime/engine/tests/test_policy.py",
                "agents/runtime/engine/README.md",
            ),
            **AGENT,
        )
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 0, out)
        self.assertIn("Verdict-eligible", out)

    def test_engine_py_outside_tests_still_cris_only(self):
        setup(files=("agents/runtime/engine/runner.py",), **AGENT)
        code, out = run("agent-denied-paths")
        self.assertEqual(code, 1, out)
        self.assertIn("Cris-only", out)

    def test_context_creation_restricted_shape(self):
        assert_creation_restricted_shape(load_canon(), repository="context")

    def test_keyflo_creation_restricted_shape(self):
        assert_creation_restricted_shape(
            load_canon(),
            repository="keyflo-session-issuer",
            extra_required_excludes=("refs/heads/dev",),
        )

    def test_creation_restricted_target_repos_no_bypass(self):
        for repo in ("fabricbloc", "context", "keyflo-session-issuer"):
            self.assertEqual(creation_restricted(load_canon(), repository=repo).get("bypass_actors"), [])

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
            if name == "agent-review-of-record":
                pr = pr_on.get("pull_request_target") if isinstance(pr_on, dict) else None
            else:
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
                "    if base_ref == DEFAULT_BASE_REF:\n        return True",
                "    if base_ref.startswith(\"main\"):\n        return True",
            )

        code, out = run_gate_with_patch("agent-denied-paths", patch)
        self.assertEqual(code, 0, out)
        self.assertNotIn("agent PRs must target main", out)

    def test_mutation_validate_canon_live_ref_loosened(self):
        from validate_canon import agent_gates_live_ref_errors

        canon = copy.deepcopy(load_canon())
        gates = next(r for r in canon["organization_rulesets"] if r["name"] == "canon-agent-gates")
        gates["conditions"]["ref_name"]["include"].append("refs/heads/stray")
        self.assertTrue(agent_gates_live_ref_errors(canon))

        def patch(src):
            return src.replace(
                '        if list(inc) != list(LIVE_REF_INCLUDE):',
                '        if set(LIVE_REF_INCLUDE) - set(inc):',
            )

        ns = {"__file__": str(ROOT / "agent-gates" / "validate_canon.py")}
        src = (ROOT / "agent-gates" / "validate_canon.py").read_text()
        exec(patch(src).split("def main():")[0], ns)  # noqa: S102
        self.assertFalse(ns["agent_gates_live_ref_errors"](canon))

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


class TestMintDeniedPathsPoll(unittest.TestCase):
    """Mint path waits for agent-denied-paths (GitHub Actions app 15368) before App APPROVE."""

    def _poll_env(self):
        return {
            "DENIED_PATHS_POLL_INTERVAL_SEC": "0",
            "DENIED_PATHS_POLL_TIMEOUT_SEC": "1",
        }

    def _run_denied_paths_check(self, eg, *, head=HEAD, pr_number="7", wait=True, check_runs_state):
        """check_runs_state: list of check_runs payloads returned on successive API reads."""
        state = {"i": 0, "heads": {str(pr_number): head}}

        class FakeResp:
            def __init__(self, payload):
                self._payload = payload

            def read(self):
                return json.dumps(self._payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout=30):
            url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
            path = urllib.parse.urlparse(url).path
            if path.endswith(f"/pulls/{pr_number}"):
                live = state["heads"][str(pr_number)]
                return FakeResp({"head": {"sha": live}})
            if f"/commits/{head}/check-runs" in path:
                idx = min(state["i"], len(check_runs_state) - 1)
                state["i"] += 1
                runs = check_runs_state[idx]
                if callable(runs):
                    runs = runs()
                return FakeResp({"check_runs": runs})
            raise AssertionError(f"unexpected urlopen {path}")

        orig_repo, orig_token = eg.REPO, eg.TOKEN
        orig_open = eg.urllib.request.urlopen
        orig_sleep = eg.time.sleep
        eg.REPO = "BloclabsHQ/fabricbloc"
        eg.TOKEN = "test"
        eg.urllib.request.urlopen = fake_urlopen
        eg.time.sleep = lambda _s: None
        env = dict(os.environ)
        env.update(self._poll_env())
        for k, v in env.items():
            os.environ[k] = v
        try:
            return eg.agent_denied_paths_successful(
                head, wait_denied_paths=wait, pr_number=pr_number
            )
        finally:
            eg.urllib.request.urlopen = orig_open
            eg.time.sleep = orig_sleep
            eg.REPO, eg.TOKEN = orig_repo, orig_token

    def _ga_run(self, *, status="completed", conclusion="success", run_id=1):
        return {
            "name": "agent-denied-paths",
            "status": status,
            "conclusion": conclusion,
            "app": {"id": GITHUB_ACTIONS_APP_ID, "slug": "github-actions"},
            "started_at": "2026-10-05T12:00:00Z",
            "id": run_id,
        }

    def test_in_progress_then_success_proceeds(self):
        import embedded_gate as eg

        ok = self._run_denied_paths_check(
            eg,
            check_runs_state=[
                [self._ga_run(status="in_progress", conclusion=None)],
                [self._ga_run(status="completed", conclusion="success")],
            ],
        )
        self.assertTrue(ok)

    def test_in_progress_then_failure_fails_closed(self):
        import embedded_gate as eg

        ok = self._run_denied_paths_check(
            eg,
            check_runs_state=[
                [self._ga_run(status="in_progress", conclusion=None)],
                [self._ga_run(status="completed", conclusion="failure")],
            ],
        )
        self.assertFalse(ok)

    def test_never_completes_before_timeout_fails_closed(self):
        import embedded_gate as eg

        ok = self._run_denied_paths_check(
            eg,
            check_runs_state=[[self._ga_run(status="in_progress", conclusion=None)]] * 20,
        )
        self.assertFalse(ok)

    def test_head_changes_mid_poll_fails_closed(self):
        import embedded_gate as eg

        new_head = "n" * 40
        state = {"i": 0, "heads": {"7": HEAD}}

        class FakeResp:
            def __init__(self, payload):
                self._payload = payload

            def read(self):
                return json.dumps(self._payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout=30):
            url = req.full_url if hasattr(req, "full_url") else req.get_full_url()
            path = urllib.parse.urlparse(url).path
            if path.endswith("/pulls/7"):
                if state["i"] == 0:
                    state["heads"]["7"] = HEAD
                else:
                    state["heads"]["7"] = new_head
                state["i"] += 1
                return FakeResp({"head": {"sha": state["heads"]["7"]}})
            if f"/commits/{HEAD}/check-runs" in path:
                return FakeResp({"check_runs": [self._ga_run(status="in_progress", conclusion=None)]})
            raise AssertionError(path)

        orig_open = eg.urllib.request.urlopen
        orig_sleep = eg.time.sleep
        eg.urllib.request.urlopen = fake_urlopen
        eg.time.sleep = lambda _s: None
        os.environ.update(self._poll_env())
        try:
            ok = eg.agent_denied_paths_successful(
                HEAD, wait_denied_paths=True, pr_number="7"
            )
        finally:
            eg.urllib.request.urlopen = orig_open
            eg.time.sleep = orig_sleep
        self.assertFalse(ok)

    def test_mint_job_env_sets_poll_defaults(self):
        doc = yaml.safe_load((WF / "agent-review-of-record.yml").read_text())
        mint = (doc.get("jobs") or {}).get("reviewer-app-auto-approve") or {}
        mint_run = [s for s in mint["steps"] if s.get("env", {}).get("ROR_JOB") == "mint"][0]
        env = mint_run.get("env") or {}
        self.assertEqual(env.get("DENIED_PATHS_POLL_INTERVAL_SEC"), "10")
        self.assertEqual(env.get("DENIED_PATHS_POLL_TIMEOUT_SEC"), "300")


if __name__ == "__main__":
    unittest.main(verbosity=1)
