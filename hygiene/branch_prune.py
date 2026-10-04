#!/usr/bin/env python3
"""C5 weekly prune of merged agent/** branches (stdlib, API-only)."""
import json
import os
import time

from common import HygieneAPIError, call, fail, paginate, repo_short, slack_post_message

MODE = "hygiene-c5-branch-prune"
BRANCH_GLOB_PREFIX = "agent/"
MIN_AGE_HOURS_DEFAULT = 72


def env(name, default=""):
    return os.environ.get(name, default)


def list_agent_branches(token, repo):
    refs = paginate(f"/repos/{repo}/git/matching-refs/heads/{BRANCH_GLOB_PREFIX}", token=token)
    out = []
    for ref in refs:
        ref_name = ref.get("ref") or ""
        if not ref_name.startswith("refs/heads/agent/"):
            continue
        out.append(ref_name[len("refs/heads/") :])
    return out


def branch_protected(token, repo, branch):
    info = call(f"/repos/{repo}/branches/{branch}", token=token, allow_404=True)
    if info is None:
        return True, "missing"
    if info.get("protected"):
        return True, "protected"
    rules = call(f"/repos/{repo}/rules/branches/{branch}", token=token, allow_404=True) or []
    for rule in rules:
        if isinstance(rule, dict) and rule.get("type") == "deletion":
            return True, "ruleset-deletion"
    return False, "ok"


def open_pr_heads(token, repo):
    prs = paginate(f"/repos/{repo}/pulls?state=open", token=token, cap=50)
    return {(p.get("head") or {}).get("ref") for p in prs}


def merged_pr_for_tip(token, repo, branch, sha):
    prs = call(
        f"/repos/{repo}/commits/{sha}/pulls",
        token=token,
        accept="application/vnd.github+json",
    )
    if not isinstance(prs, list):
        return None
    for pr in prs:
        head = pr.get("head") or {}
        if pr.get("merged_at") and head.get("ref") == branch and head.get("sha") == sha:
            return pr
    return None


def branch_tip_sha(token, repo, branch):
    ref = call(f"/repos/{repo}/git/ref/heads/{branch}", token=token, allow_404=True)
    if not ref:
        return None
    return (ref.get("object") or {}).get("sha")


def branch_tip_age_hours(token, repo, branch):
    sha = branch_tip_sha(token, repo, branch)
    if not sha:
        return None, None
    commit = call(f"/repos/{repo}/commits/{sha}", token=token)
    date = ((commit or {}).get("commit") or {}).get("author", {}).get("date")
    if not date:
        return sha, None
    # ISO8601
    from datetime import datetime, timezone

    ts = datetime.strptime(date.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
    age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    return sha, age_h


def engine_active_branch(token, repo, branch):
    if not branch.startswith("agent/autonomous/"):
        return False
    # Without engine ledger API, skip autonomous branches with no merged proof (report only).
    return False


def delete_branch(token, repo, branch):
    call(f"/repos/{repo}/git/refs/heads/{branch}", token=token, method="DELETE", allow_404=True)


def main():
    token = env("GH_TOKEN")
    slack = env("SLACK_BOT_TOKEN")
    repo = env("REPO")
    run_id = env("GITHUB_RUN_ID", "local")
    mode = (env("HYGIENE_MODE") or "dry-run").strip().lower()
    ack = env("HYGIENE_C5_DRYRUN_ACK", "").strip()
    min_age = float(env("MIN_AGE_HOURS", str(MIN_AGE_HOURS_DEFAULT)))
    channel = env("CHANNEL", "C0C531H03M4")

    if not token:
        fail(MODE, "GH_TOKEN missing")
    if mode == "live" and not ack:
        fail(MODE, "live refused: set HYGIENE_C5_DRYRUN_ACK to a completed dry-run run id")

    delete_branch_on_merge = call(f"/repos/{repo}", token=token).get("delete_branch_on_merge")
    print(f"delete_branch_on_merge={delete_branch_on_merge}")

    heads = open_pr_heads(token, repo)
    branches = list_agent_branches(token, repo)
    to_delete = []
    keep = []
    unmerged_report = []

    for branch in branches:
        if not branch.startswith(BRANCH_GLOB_PREFIX):
            keep.append((branch, "non-agent-prefix"))
            continue
        prot, reason = branch_protected(token, repo, branch)
        if prot:
            keep.append((branch, reason))
            continue
        if branch in heads:
            keep.append((branch, "open-pr"))
            continue
        sha, age_h = branch_tip_age_hours(token, repo, branch)
        if sha is None:
            keep.append((branch, "no-tip"))
            continue
        merged_pr = merged_pr_for_tip(token, repo, branch, sha)
        if not merged_pr:
            unmerged_report.append((branch, sha))
            continue
        if age_h is not None and age_h < min_age:
            keep.append((branch, f"younger-than-{min_age}h"))
            continue
        if engine_active_branch(token, repo, branch):
            keep.append((branch, "engine-active"))
            continue
        to_delete.append((branch, sha, merged_pr.get("number")))

    deleted = 0
    for branch, sha, prn in to_delete:
        if mode == "live":
            try:
                delete_branch(token, repo, branch)
                deleted += 1
                print(f"deleted {branch} pr=#{prn} sha={sha[:7]}")
            except HygieneAPIError as exc:
                if exc.code == 404:
                    deleted += 1
                else:
                    raise
        else:
            print(f"DRY-RUN delete {branch} pr=#{prn} sha={sha[:7]}")

    summary = {
        "run_id": run_id,
        "mode": mode,
        "deleted": deleted,
        "candidates": len(to_delete),
        "keep": len(keep),
        "unmerged_report": len(unmerged_report),
    }
    print(json.dumps(summary))
    lines = [
        f"*hygiene C5 branch prune* `{repo}` run `{run_id}` mode `{mode}`",
        f"deleted={deleted} candidates={len(to_delete)} keep={len(keep)} unmerged_listed={len(unmerged_report)}",
        "<!-- hygiene:c5:run:" + run_id + " -->",
    ]
    for b, sha, prn in to_delete[:40]:
        lines.append(f"• delete `{b}` (merged PR #{prn}, {sha[:7]})")
    for b, sha in unmerged_report[:20]:
        lines.append(f"• report unmerged `{b}` ({sha[:7]})")
    for b, reason in keep[:20]:
        lines.append(f"• keep `{b}` ({reason})")

    text = "\n".join(lines)
    if slack and channel:
        try:
            slack_post_message(slack, channel, text)
        except Exception as exc:
            fail(MODE, f"slack report failed: {exc}")
    elif channel and not slack:
        print(f"::warning::{MODE}: SLACK_BOT_TOKEN missing; report skipped (see job log)")
    elif mode == "live":
        fail(MODE, "SLACK_BOT_TOKEN required for live mode")


if __name__ == "__main__":
    main()
