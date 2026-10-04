#!/usr/bin/env python3
"""C4 ci-red issue tracker for consecutive workflow failures on default branch."""
import json
import os
import re

from common import HygieneAPIError, call, dry_run, fail, paginate

MODE = "hygiene-c4-ci-red"
MARKER_RE = re.compile(r"<!--\s*hygiene:ci-red:(?P<repo>[^:]+):(?P<wf>\d+)\s*-->")


def env(name, default=""):
    return os.environ.get(name, default)


def parse_owners(raw):
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def run_is_failure(run):
    if run.get("conclusion") in ("cancelled", "skipped", "neutral"):
        return None
    if run.get("conclusion") in ("failure", "timed_out"):
        return True
    if run.get("conclusion") == "success":
        return False
    return None


def last_two_runs(token, repo, workflow_id, branch):
    data = call(
        f"/repos/{repo}/actions/workflows/{workflow_id}/runs?branch={branch}&status=completed&per_page=2",
        token=token,
    )
    runs = (data or {}).get("workflow_runs") or []
    return runs[:2]


def find_issue(token, repo, marker):
    issues = paginate(f"/repos/{repo}/issues?state=open&labels=ci-red", token=token, cap=10)
    for issue in issues:
        if marker in (issue.get("body") or ""):
            return issue
    return None


def ensure_labels(token, repo, labels):
    for lab in labels:
        call(f"/repos/{repo}/labels/{lab}", token=token, allow_404=True)


def process_workflow(token, repo, wf_name, wf_id, branch, owners, default_label):
    marker = f"<!-- hygiene:ci-red:{repo}:{wf_id} -->"
    runs = last_two_runs(token, repo, wf_id, branch)
    outcomes = [run_is_failure(r) for r in runs]
    outcomes = [o for o in outcomes if o is not None]
    consecutive = 0
    for o in outcomes:
        if o:
            consecutive += 1
        else:
            break
    action = "none"
    if len(outcomes) >= 2 and outcomes[0] and outcomes[1]:
        action = "open_or_update"
    elif outcomes and outcomes[0] is False:
        action = "close"
    elif len(outcomes) == 1 and outcomes[0]:
        action = "none"
        print(f"consecutive=1 action=none workflow={wf_name}")
        return
    print(f"workflow={wf_name} consecutive={consecutive} action={action}")

    owner_cfg = owners.get(wf_name) or owners.get(f"{wf_name}.yml") or {}
    label = owner_cfg.get("label") or default_label
    assignee = owner_cfg.get("assignee")

    issue = find_issue(token, repo, marker)
    if action == "close" and issue:
        if dry_run():
            print(f"DRY-RUN close issue #{issue['number']}")
            return
        call(
            f"/repos/{repo}/issues/{issue['number']}",
            token=token,
            method="PATCH",
            body={"state": "closed"},
        )
        call(
            f"/repos/{repo}/issues/{issue['number']}/comments",
            token=token,
            method="POST",
            body={"body": f"Closed: green run {runs[0].get('html_url')}"},
        )
        return
    if action != "open_or_update":
        return
    title = f"ci-red: {wf_name} on {branch}"
    fail_count = sum(1 for r in runs if run_is_failure(r))
    body = (
        f"{marker}\n"
        f"Consecutive failures: {fail_count}\n"
        f"Latest: {runs[0].get('html_url')} @ `{runs[0].get('head_sha', '')[:7]}`\n"
    )
    labels = ["ci-red", label]
    if dry_run():
        print(f"DRY-RUN issue {title}")
        return
    if issue:
        call(
            f"/repos/{repo}/issues/{issue['number']}",
            token=token,
            method="PATCH",
            body={"body": body},
        )
        call(
            f"/repos/{repo}/issues/{issue['number']}/comments",
            token=token,
            method="POST",
            body={"body": f"Still failing: {runs[0].get('html_url')}"},
        )
    else:
        payload = {"title": title, "body": body, "labels": labels}
        if assignee:
            payload["assignees"] = [assignee]
        call(f"/repos/{repo}/issues", token=token, method="POST", body=payload)


def main():
    token = env("GH_TOKEN")
    repo = env("REPO")
    branch = env("DEFAULT_BRANCH", "main")
    wf_json = env("WORKFLOW_NAMES", "[]")
    owners = parse_owners(env("OWNERS_JSON"))
    if not token:
        fail(MODE, "GH_TOKEN missing")
    try:
        names = json.loads(wf_json)
    except json.JSONDecodeError:
        fail(MODE, "WORKFLOW_NAMES must be JSON array")
    for name in names:
        wf = call(f"/repos/{repo}/actions/workflows/{name}", token=token, allow_404=True)
        if not wf:
            print(f"skip missing workflow {name}")
            continue
        process_workflow(token, repo, name, wf["id"], branch, owners, "owner:madengineer")


if __name__ == "__main__":
    main()
