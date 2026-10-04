#!/usr/bin/env python3
"""C3 auto-merge (evaluate + enable/disable via hygiene App token). Gated on canon-agent-gates."""
import json
import os

from common import (
    FLOOR_NEVER_ALLOWLIST,
    HOLD_LABELS,
    TARGET_REPOS,
    HygieneAPIError,
    call,
    dry_run,
    fail,
    fetch_manifest_denied,
    paginate,
    path_matches_any,
)

MODE = "hygiene-c3-auto-merge"
ENGINE_AUTHOR = "fabricbloc-agent-ops[bot]"


def env(name, default=""):
    return os.environ.get(name, default)


def gate_enforced(token, repo, base, gate_path, pin_sha):
    rules = call(f"/repos/{repo}/rules/branches/{base}", token=token) or []
    for rule in rules:
        if rule.get("type") != "workflows":
            continue
        for wf in (rule.get("parameters") or {}).get("workflows") or []:
            if wf.get("path") == gate_path and wf.get("sha") == pin_sha:
                return True
    return False


def pr_blocked(pr, denied):
    if pr.get("draft"):
        return "draft"
    labels = {l.get("name") for l in pr.get("labels") or []}
    if labels & HOLD_LABELS:
        return "hold"
    if "security" in labels:
        return "security"
    head = (pr.get("head") or {}).get("ref") or ""
    if head.startswith("agent/autonomous/"):
        return "engine-branch"
    user = (pr.get("user") or {}).get("login")
    if user == ENGINE_AUTHOR:
        return "engine-author"
    return None


def graphql(token, query, variables):
    return call(
        "/graphql",
        token=token,
        method="POST",
        body={"query": query, "variables": variables},
    )


def disable_auto_merge(token, node_id):
    q = """
    mutation($id: ID!) {
      disablePullRequestAutoMerge(input: {pullRequestId: $id}) {
        clientMutationId
      }
    }
    """
    graphql(token, q, {"id": node_id})


def enable_auto_merge(token, node_id, head_oid):
    q = """
    mutation($id: ID!, $sha: GitObjectID!) {
      enablePullRequestAutoMerge(input: {pullRequestId: $id, mergeMethod: SQUASH, expectedHeadOid: $sha}) {
        clientMutationId
      }
    }
    """
    print(f"enable expectedHeadOid={head_oid}")
    if dry_run():
        return
    graphql(token, q, {"id": node_id, "sha": head_oid})


def evaluate_pr(token, app_token, repo, pr_number, gate_path, agent_gates_sha, denied):
    pr = call(f"/repos/{repo}/pulls/{pr_number}", token=token)
    reason = pr_blocked(pr, denied)
    if reason:
        print(f"skip:{reason}")
        return
    files = paginate(f"/repos/{repo}/pulls/{pr_number}/files", token=token, cap=30)
    for f in files:
        for path in (f.get("filename"), f.get("previous_filename")):
            if path and path_matches_any(path, denied):
                print("skip:protected-path")
                return
    base = (pr.get("base") or {}).get("ref") or "main"
    if not gate_enforced(token, repo, base, gate_path, agent_gates_sha):
        print("skip:gate-not-enforced")
        return
    head_sha = (pr.get("head") or {}).get("sha")
    node = call(f"/repos/{repo}/pulls/{pr_number}", token=token).get("node_id")
    if not app_token:
        print("skip:no-app-token")
        return
    enable_auto_merge(app_token, node, head_sha)


def main():
    token = env("GH_TOKEN")
    app_token = env("HYGIENE_APP_TOKEN")
    repo = env("REPO")
    gate_path = env("REQUIRED_GATE_PATH", ".github/workflows/agent-review-of-record.yml")
    agent_gates_sha = env("AGENT_GATES_SHA", "")
    pr_number = env("PR_NUMBER")
    if repo not in TARGET_REPOS:
        print("skip:not-target-repo")
        return
    if repo in FLOOR_NEVER_ALLOWLIST:
        print("skip:never-allowlist")
        return
    if not token:
        fail(MODE, "GH_TOKEN missing")
    denied, never = fetch_manifest_denied(repo, env("DEFAULT_BRANCH", "main"))
    if pr_number:
        evaluate_pr(token, app_token, repo, int(pr_number), gate_path, agent_gates_sha, denied)
    else:
        print("summary-only dry-run reconcile")


if __name__ == "__main__":
    main()
