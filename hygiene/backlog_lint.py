#!/usr/bin/env python3
"""C6 delegate-spec backlog lint (issues API + pinned checklist template)."""
import os
import re
from datetime import datetime, timezone

from common import call, dry_run, fail, paginate

MODE = "hygiene-c6-backlog-lint"
LIFECYCLE = frozenset({"spec:draft", "spec:gate", "spec:ready", "in-progress", "blocked"})
MARKER = "<!-- hygiene:c6:lint -->"
TARGET_RE = re.compile(r"Target:\s*([\w.-]+/[\w.-]+)\s*·\s*lane:\s*(\S+)")
IMPL_RE = re.compile(r"Implementation PR:\s*https://github\.com/[\w.-]+/[\w.-]+/pull/\d+", re.I)
SPEC_PATH_RE = re.compile(r"docs/specs/\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md")
TRACKING_RE = re.compile(r"Tracking issue:\s*(https://github\.com/\S+)", re.I)
ROW_TABLE_RE = re.compile(r"^\|\s*(R\d+|D\d+|W\d+|S\d+|T\d+|M\d+)\s*\|", re.M)
ROW_CHECKLIST_RE = re.compile(r"^\s*-\s*\[(PASS|FAIL)\]\s*(R\d+|D\d+|W\d+|S\d+|T\d+|M\d+)\b", re.M | re.I)


def env(name, default=""):
    return os.environ.get(name, default)


def template_gate_open():
    return env("TEMPLATE_GATE_READY", "").strip().lower() == "true"


def inert_run():
    if not template_gate_open():
        print("inert: HYGIENE_C6_TEMPLATE_READY != true (fabricbloc #1565 gate)")
        return True
    if dry_run():
        print("dry-run: no issue mutations")
        return True
    return False


def load_template(token, repo, ref, path):
    raw = call(
        f"/repos/{repo}/contents/{path}?ref={ref}",
        token=token,
        accept="application/vnd.github.raw",
    )
    if not isinstance(raw, str):
        fail(MODE, "template unreadable")
    return raw


def row_ids_from_template(text):
    ids = {m.group(1).upper() for m in ROW_TABLE_RE.finditer(text or "")}
    ids.update(m.group(2).upper() for m in ROW_CHECKLIST_RE.finditer(text or ""))
    return sorted(ids)


def lifecycle_labels(labels):
    names = [l.get("name") for l in labels or [] if l.get("name") in LIFECYCLE and l.get("name") != "blocked"]
    return names


def parse_ts(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def in_progress_labeled_at(token, repo, issue_number):
    events = paginate(f"/repos/{repo}/issues/{issue_number}/timeline", token=token, cap=30)
    latest = None
    for ev in events:
        if ev.get("event") != "labeled":
            continue
        if (ev.get("label") or {}).get("name") != "in-progress":
            continue
        ts = parse_ts(ev.get("created_at"))
        if ts and (latest is None or ts > latest):
            latest = ts
    return latest


def tracking_issue_ok(token, body):
    m = TRACKING_RE.search(body or "")
    if not m:
        return False
    url = m.group(1).rstrip(").")
    parts = url.replace("https://github.com/", "").split("/")
    if len(parts) < 4 or parts[2] != "issues":
        return False
    try:
        num = int(parts[3])
    except ValueError:
        return False
    issue = call(f"/repos/{parts[0]}/{parts[1]}/issues/{num}", token=token, allow_404=True)
    return issue is not None


def lint_issue(token, repo, issue, template_rows, needs_pr_days, *, mutate):
    num = issue["number"]
    body = issue.get("body") or ""
    labels = issue.get("labels") or []
    fails = []
    life = lifecycle_labels(labels)
    if len(life) > 1:
        fails.append("W3:multiple-lifecycle")
    if len(issue.get("assignees") or []) != 1:
        fails.append("R1:assignee")
    if not TARGET_RE.search(body):
        fails.append("R2:target-lane")
    life_set = {l.get("name") for l in labels}
    if "in-progress" in life_set and not IMPL_RE.search(body):
        fails.append("R3:implementation-pr")
    if life_set & {"spec:gate", "spec:ready", "in-progress"}:
        for rid in template_rows:
            if rid.startswith(("D", "R", "W")):
                if not re.search(rf"\[(PASS|FAIL)\]\s*{rid}\b", body, re.I) and not re.search(
                    rf"\|\s*{rid}\s*\|[^\n]*\b(PASS|FAIL)\b", body, re.I
                ):
                    fails.append(f"{rid}:missing-row")
        if not SPEC_PATH_RE.search(body):
            fails.append("D1:spec-path")
        if not tracking_issue_ok(token, body):
            fails.append("D2:tracking-issue")
    comment_body = MARKER + "\n" + "\n".join(f"FAIL {f}" for f in fails) if fails else MARKER + "\nPASS"
    if not mutate:
        print(f"issue #{num} lint preview: {len(fails)} fails")
        return
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

    label_names = {l.get("name") for l in labels}
    if "in-progress" not in label_names:
        if "needs-pr" in label_names:
            call(
                f"/repos/{repo}/issues/{num}/labels/needs-pr",
                token=token,
                method="DELETE",
                allow_404=True,
            )
        return
    if IMPL_RE.search(body):
        if "needs-pr" in label_names:
            call(
                f"/repos/{repo}/issues/{num}/labels/needs-pr",
                token=token,
                method="DELETE",
                allow_404=True,
            )
        return
    labeled_at = in_progress_labeled_at(token, repo, num)
    if labeled_at and (datetime.now(timezone.utc) - labeled_at.astimezone(timezone.utc)).days >= needs_pr_days:
        if "needs-pr" not in label_names:
            call(
                f"/repos/{repo}/issues/{num}/labels",
                token=token,
                method="POST",
                body={"labels": ["needs-pr"]},
            )


def main():
    token = env("GH_TOKEN")
    repo = env("REPO")
    template_repo = env("TEMPLATE_REPO", "BloclabsHQ/fabricbloc")
    template_ref = env("TEMPLATE_REF", "main")
    template_path = env("TEMPLATE_PATH", "templates/spec/GATE-CHECKLIST.md")
    needs_pr_days = int(env("NEEDS_PR_DAYS", "3"))
    if not token:
        fail(MODE, "GH_TOKEN missing")
    mutate = not inert_run()
    template = load_template(token, template_repo, template_ref, template_path)
    rows = row_ids_from_template(template)
    print(f"template_rows={rows} mutate={mutate}")
    for issue in paginate(f"/repos/{repo}/issues?state=open&per_page=100", token=token, cap=10):
        if not ({l.get("name") for l in issue.get("labels") or []} & LIFECYCLE):
            continue
        lint_issue(token, repo, issue, rows, needs_pr_days, mutate=mutate)


if __name__ == "__main__":
    main()
