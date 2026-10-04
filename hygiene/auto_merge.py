#!/usr/bin/env python3
"""C3 auto-merge (evaluate + enable/disable via hygiene App token). Gated on canon-agent-gates."""
import json
import os

from common import (
    FLOOR_NEVER_ALLOWLIST,
    HOLD_LABELS,
    TARGET_REPOS,
    call,
    dry_run,
    fail,
    fetch_manifest_denied,
    paginate,
    path_matches_any,
)

MODE = "hygiene-c3-auto-merge"
ENGINE_AUTHOR = "fabricbloc-agent-ops[bot]"
ENGINE_MARKER = "<!-- hygiene:c3:engine-owned -->"


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


def skip_reason(pr, denied, extra_paths):
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


def dependabot_allowed(pr, allow_flag, update_type):
    user = (pr.get("user") or {}).get("login")
    if user != "dependabot[bot]":
        return True
    if not allow_flag:
        return False
    if update_type in ("version-update:semver-patch", "version-update:semver-minor"):
        return True
    return False


def graphql(token, query, variables):
    return call(
        "/graphql",
        token=token,
        method="POST",
        body={"query": query, "variables": variables},
    )


def auto_merge_enabled(token, node_id):
    q = """
    query($id: ID!) {
      node(id: $id) {
        ... on PullRequest {
          autoMergeRequest { enabledAt mergeMethod }
          headRefOid
        }
      }
    }
    """
    data = graphql(token, q, {"id": node_id})
    node = (data or {}).get("data", {}).get("node") or {}
    return node.get("autoMergeRequest"), node.get("headRefOid")


def disable_auto_merge(token, node_id):
    if dry_run():
        print(f"DRY-RUN disable auto-merge {node_id}")
        return
    q = """
    mutation($id: ID!) {
      disablePullRequestAutoMerge(input: {pullRequestId: $id}) {
        clientMutationId
      }
    }
    """
    graphql(token, q, {"id": node_id})


def enable_auto_merge(token, node_id, head_oid):
    print(f"enable expectedHeadOid={head_oid}")
    if dry_run():
        return True
    q = """
    mutation($id: ID!, $sha: GitObjectID!) {
      enablePullRequestAutoMerge(input: {pullRequestId: $id, mergeMethod: SQUASH, expectedHeadOid: $sha}) {
        clientMutationId
      }
    }
    """
    try:
        graphql(token, q, {"id": node_id, "sha": head_oid})
        return True
    except Exception as exc:
        print(f"enable failed: {exc}")
        return False


def direct_squash_merge(token, repo, pr_number, head_sha):
    print(f"fallback PUT merge sha={head_sha}")
    if dry_run():
        return
    call(
        f"/repos/{repo}/pulls/{pr_number}/merge",
        token=token,
        method="PUT",
        body={"merge_method": "squash", "sha": head_sha},
    )


def comment(token, repo, pr_number, body):
    if dry_run():
        print(f"DRY-RUN comment: {body[:80]}")
        return
    call(f"/repos/{repo}/issues/{pr_number}/comments", token=token, method="POST", body={"body": body})


def handle_engine_owned(token, app_token, repo, pr_number, pr):
    node = pr.get("node_id")
    am, _ = auto_merge_enabled(token, node)
    if am:
        disable_auto_merge(app_token or token, node)
        comment(token, repo, pr_number, f"Auto-merge disabled: engine-owned PR. {ENGINE_MARKER}")


def evaluate_pr(token, app_token, repo, pr_number, gate_path, agent_gates_sha, denied, extra_paths, allow_dependabot, update_type, event_action):
    pr = call(f"/repos/{repo}/pulls/{pr_number}", token=token)
    node = pr.get("node_id")
    reason = skip_reason(pr, denied, extra_paths)
    if reason in ("engine-branch", "engine-author"):
        handle_engine_owned(token, app_token, repo, pr_number, pr)
        print(f"skip:{reason}")
        return
    if event_action in ("labeled",) and reason == "hold":
        disable_auto_merge(app_token or token, node)
        print("auto_merge_disabled:hold")
        return
    if event_action == "synchronize":
        disable_auto_merge(app_token or token, node)
        print("auto_merge_disabled:synchronize")
    if reason:
        print(f"skip:{reason}")
        if reason in ("hold", "security"):
            disable_auto_merge(app_token or token, node)
        return
    if not dependabot_allowed(pr, allow_dependabot, update_type):
        print("skip:dependabot-major")
        return
    files = paginate(f"/repos/{repo}/pulls/{pr_number}/files", token=token, cap=30)
    for f in files:
        for path in (f.get("filename"), f.get("previous_filename")):
            if path and (path_matches_any(path, denied) or path_matches_any(path, extra_paths)):
                print("skip:protected-path")
                return
    base = (pr.get("base") or {}).get("ref") or "main"
    if not gate_enforced(token, repo, base, gate_path, agent_gates_sha):
        print("skip:gate-not-enforced")
        return
    head_sha = (pr.get("head") or {}).get("sha")
    if not app_token:
        print("skip:no-app-token")
        return
    if not enable_auto_merge(app_token, node, head_sha):
        direct_squash_merge(app_token, repo, pr_number, head_sha)


def list_open_prs(token, repo, base):
    return paginate(f"/repos/{repo}/pulls?state=open&base={base}", token=token, cap=30)


def main():
    token = env("GH_TOKEN")
    app_token = env("HYGIENE_APP_TOKEN")
    repo = env("REPO")
    gate_path = env("REQUIRED_GATE_PATH", ".github/workflows/agent-review-of-record.yml")
    agent_gates_sha = env("AGENT_GATES_SHA", "")
    pr_number = env("PR_NUMBER")
    event_action = env("EVENT_ACTION", "")
    reconcile = env("RECONCILE", "").lower() in ("1", "true", "yes")
    allow_dependabot = env("ALLOW_DEPENDABOT", "true").lower() == "true"
    update_type = env("DEPENDABOT_UPDATE_TYPE", "")
    extra = [p.strip() for p in env("EXTRA_PROTECTED_PATHS", "").split(",") if p.strip()]
    base = env("DEFAULT_BRANCH", "main")

    if repo not in TARGET_REPOS:
        print("skip:not-target-repo")
        return
    if repo in FLOOR_NEVER_ALLOWLIST:
        print("skip:never-allowlist")
        return
    if not token:
        fail(MODE, "GH_TOKEN missing")
    denied, _never = fetch_manifest_denied(repo, base, mode=MODE)

    targets = []
    if pr_number:
        targets = [int(pr_number)]
    elif reconcile:
        targets = [p["number"] for p in list_open_prs(token, repo, base)]
        print(f"reconcile prs={len(targets)}")
    else:
        print("no PR_NUMBER and not RECONCILE; nothing to do")
        return

    for num in targets:
        evaluate_pr(
            token,
            app_token,
            repo,
            num,
            gate_path,
            agent_gates_sha,
            denied,
            extra,
            allow_dependabot,
            update_type,
            event_action,
        )


if __name__ == "__main__":
    main()
