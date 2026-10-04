#!/usr/bin/env python3
"""C6 delegate-spec backlog lint (issues API + pinned checklist template)."""
import os
import re
from datetime import datetime, timezone

from common import call, fail, paginate

MODE = "hygiene-c6-backlog-lint"
LIFECYCLE = frozenset({"spec:draft", "spec:gate", "spec:ready", "in-progress", "blocked"})
MARKER = "<!-- hygiene:c6:lint -->"
TARGET_RE = re.compile(r"Target:\s*([\w.-]+/[\w.-]+)\s*·\s*lane:\s*(\S+)")
IMPL_RE = re.compile(r"Implementation PR:\s*https://github\.com/[\w.-]+/[\w.-]+/pull/\d+", re.I)
SPEC_PATH_RE = re.compile(r"docs/specs/\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md")
ROW_RE = re.compile(r"^\s*-\s*\[(PASS|FAIL)\]\s*(R\d+|D\d+|W\d+|S\d+|T\d+|M\d+)\b", re.M | re.I)


def env(name, default=""):
    return os.environ.get(name, default)


def load_template(token, repo, ref, path):
    raw = call(
        f"/repos/{repo}/contents/{path}?ref={ref}",
        token=token,
        accept="application/vnd.github.raw",
    )
    return raw if isinstance(raw, str) else ""


def row_ids_from_template(text):
    return sorted(set(m.group(2).upper() for m in ROW_RE.finditer(text or "")))


def lifecycle_labels(labels):
    names = [l.get("name") for l in labels or [] if l.get("name") in LIFECYCLE and l.get("name") != "blocked"]
    return names


def lint_issue(token, repo, issue, template_rows, needs_pr_days):
    num = issue["number"]
    body = issue.get("body") or ""
    labels = issue.get("labels") or []
    fails = []
    life = lifecycle_labels(labels)
    if len(life) > 1:
        fails.append("W3:multiple-lifecycle")
    assignees = issue.get("assignees") or []
    if len(assignees) != 1:
        fails.append("R1:assignee")
    if not TARGET_RE.search(body):
        fails.append("R2:target-lane")
    life_set = {l.get("name") for l in labels}
    if "in-progress" in life_set and not IMPL_RE.search(body):
        fails.append("R3:implementation-pr")
    if life_set & {"spec:gate", "spec:ready", "in-progress"}:
        for rid in template_rows:
            if rid.startswith("D") or rid.startswith("R") or rid.startswith("W"):
                if not re.search(rf"\[(PASS|FAIL)\]\s*{rid}\b", body, re.I):
                    fails.append(f"{rid}:missing-row")
        if not SPEC_PATH_RE.search(body):
            fails.append("D1:spec-path")
    comment_body = MARKER + "\n" + "\n".join(f"FAIL {f}" for f in fails) if fails else MARKER + "\nPASS"
    comments = paginate(f"/repos/{repo}/issues/{num}/comments", token=token, cap=10)
    existing = next((c for c in comments if MARKER in (c.get("body") or "")), None)
    if existing:
        if existing.get("body") != comment_body:
            call(
                f"/repos/{repo}/issues/comments/{existing['id']}",
                token=token,
                method="PATCH",
                body={"body": comment_body},
            )
    else:
        call(f"/repos/{repo}/issues/{num}/comments", token=token, method="POST", body={"body": comment_body})

    if "in-progress" in life_set and not IMPL_RE.search(body):
        # needs-pr from label age approximated via updated_at
        updated = parse_ts(issue.get("updated_at"))
        if updated and (datetime.now(timezone.utc) - updated).days >= needs_pr_days:
            if "needs-pr" not in {l.get("name") for l in labels}:
                call(
                    f"/repos/{repo}/issues/{num}/labels",
                    token=token,
                    method="POST",
                    body={"labels": ["needs-pr"]},
                )
    elif "needs-pr" in {l.get("name") for l in labels} and IMPL_RE.search(body):
        call(
            f"/repos/{repo}/issues/{num}/labels/needs-pr",
            token=token,
            method="DELETE",
            allow_404=True,
        )


def parse_ts(s):
    if not s:
        return None
    s = s.replace("Z", "+0000")
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%f%z")


def main():
    token = env("GH_TOKEN")
    repo = env("REPO")
    template_repo = env("TEMPLATE_REPO", "BloclabsHQ/fabricbloc")
    template_ref = env("TEMPLATE_REF", "main")
    template_path = env("TEMPLATE_PATH", "templates/spec/GATE-CHECKLIST.md")
    needs_pr_days = int(env("NEEDS_PR_DAYS", "3"))
    if not token:
        fail(MODE, "GH_TOKEN missing")
    template = load_template(token, template_repo, template_ref, template_path)
    rows = row_ids_from_template(template)
    print(f"template_rows={rows}")
    issues = paginate(f"/repos/{repo}/issues?state=open&per_page=100", token=token, cap=10)
    for issue in issues:
        if not ({l.get("name") for l in issue.get("labels") or []} & LIFECYCLE):
            continue
        lint_issue(token, repo, issue, rows, needs_pr_days)


if __name__ == "__main__":
    main()
