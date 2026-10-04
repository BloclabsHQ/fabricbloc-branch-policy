#!/usr/bin/env python3
"""Verify merged-PR head check runs before a deploy proceeds (fail closed)."""
import json
import os

from common import HygieneAPIError, call, fail

MODE = "hygiene-c7-deploy-green-gate"
DEFAULT_CHECKS = ("Lint", "Security Scan", "Test")


def env(name, default=""):
    return os.environ.get(name, default)


def parse_checks(raw):
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        fail(MODE, "REQUIRED_CHECKS must be a JSON array of check names")
    if not isinstance(parsed, list) or not parsed:
        fail(MODE, "REQUIRED_CHECKS must be a non-empty JSON array")
    out = []
    for item in parsed:
        if not isinstance(item, str) or not item.strip():
            fail(MODE, "each REQUIRED_CHECKS entry must be a non-empty string")
        out.append(item.strip())
    return out


def check_run_ok(run):
    conclusion = run.get("conclusion")
    if conclusion in ("success", "skipped"):
        return True
    return False


def latest_runs_by_name(runs):
    by_name = {}
    for run in runs:
        name = (run.get("name") or "").strip()
        if not name:
            continue
        prev = by_name.get(name)
        if prev is None or (run.get("id") or 0) > (prev.get("id") or 0):
            by_name[name] = run
    return by_name


def fetch_check_runs(token, repo, ref):
    path = f"/repos/{repo}/commits/{ref}/check-runs"
    runs = []
    page = 1
    while page <= 10:
        data = call(f"{path}?per_page=100&page={page}", token=token)
        chunk = (data or {}).get("check_runs") or []
        runs.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return runs


def merged_prs_for_commit(token, repo, sha):
    pulls = call(f"/repos/{repo}/commits/{sha}/pulls", token=token)
    if not pulls:
        return []
    return [p for p in pulls if p.get("merged_at")]


def pick_merged_pr(prs):
    return sorted(prs, key=lambda p: p.get("merged_at") or "", reverse=True)[0]


def verify_pr_head_checks(token, repo, commit_sha, required_names):
    prs = merged_prs_for_commit(token, repo, commit_sha)
    if not prs:
        fail(MODE, f"no merged pull request associated with commit {commit_sha[:7]}")
    pr = pick_merged_pr(prs)
    head_sha = (pr.get("head") or {}).get("sha") or ""
    if not head_sha:
        fail(MODE, f"merged PR #{pr.get('number')} missing head.sha")
    by_name = latest_runs_by_name(fetch_check_runs(token, repo, head_sha))
    missing = []
    bad = []
    for req in required_names:
        run = by_name.get(req)
        if run is None:
            missing.append(req)
            continue
        if not check_run_ok(run):
            bad.append(f"{req}={run.get('conclusion')}")
    if missing:
        fail(
            MODE,
            f"PR #{pr.get('number')} head {head_sha[:7]} missing checks: {', '.join(missing)}",
        )
    if bad:
        fail(
            MODE,
            f"PR #{pr.get('number')} head {head_sha[:7]} failed checks: {', '.join(bad)}",
        )
    return {
        "commit_sha": commit_sha,
        "pr_number": pr.get("number"),
        "head_sha": head_sha,
        "checks": required_names,
    }


def main():
    token = env("GH_TOKEN")
    repo = env("REPO")
    commit_sha = env("COMMIT_SHA")
    if not token:
        fail(MODE, "GH_TOKEN missing")
    if not repo:
        fail(MODE, "REPO missing")
    if not commit_sha or len(commit_sha) != 40:
        fail(MODE, "COMMIT_SHA must be a 40-char commit SHA")
    raw_checks = env("REQUIRED_CHECKS")
    required = parse_checks(raw_checks) if raw_checks else list(DEFAULT_CHECKS)
    try:
        result = verify_pr_head_checks(token, repo, commit_sha, required)
    except HygieneAPIError as exc:
        fail(MODE, str(exc))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
