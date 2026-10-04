#!/usr/bin/env python3
"""C2 agent PR stale label/close (API-only). Issue stale uses actions/stale in workflow."""
import os
from datetime import datetime, timezone

from common import (
    HOLD_LABELS,
    SPEC_LABELS,
    HygieneAPIError,
    call,
    dry_run,
    fail,
    fetch_manifest_denied,
    paginate,
    path_matches_any,
)

MODE = "hygiene-c2-stale"
PR_AUTHOR_DEFAULT = "Madgeniusblink"
PR_HEAD_GLOB = "agent/**"
CLOSE_MARKER = "<!-- hygiene:c2:close -->"
STALE_LABEL = "stale"


def env(name, default=""):
    return os.environ.get(name, default)


def parse_ts(s):
    s = s.replace("-07:00", "+0000").replace("Z", "+0000")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def head_matches(ref, glob):
    if glob.endswith("/**"):
        return ref.startswith(glob[:-3])
    return ref == glob


def pr_exempt_labels(labels):
    names = {l.get("name") for l in labels or []}
    if names & HOLD_LABELS:
        return "hold"
    if names & SPEC_LABELS:
        return "spec-label"
    if "blocked" in names or "security" in names:
        return "blocked-security"
    return None


def last_human_activity(token, repo, pr_number):
    events = paginate(f"/repos/{repo}/issues/{pr_number}/timeline", token=token, cap=20)
    latest = None
    for ev in reversed(events):
        et = ev.get("event")
        if et in ("committed", "commented", "reviewed", "labeled", "unlabeled"):
            actor = (ev.get("actor") or {}).get("login") or ""
            if actor.endswith("[bot]"):
                continue
            ts = ev.get("created_at") or ev.get("submitted_at")
            if ts:
                latest = parse_ts(ts)
    return latest


def changed_protected(token, repo, pr_number, denied):
    files = paginate(f"/repos/{repo}/pulls/{pr_number}/files", token=token, cap=30)
    for f in files:
        for path in (f.get("filename"), f.get("previous_filename")):
            if path and path_matches_any(path, denied):
                return True
    return False


def close_allowed():
    raw = env("CLOSE_AFTER", "2026-10-12T00:00:00-07:00")
    dt = parse_ts(raw)
    if not dt:
        return False
    return datetime.now(timezone.utc) >= dt


def main():
    token = env("GH_TOKEN")
    app_token = env("HYGIENE_APP_TOKEN")
    repo = env("REPO")
    author = env("PR_AUTHOR", PR_AUTHOR_DEFAULT)
    head_glob = env("PR_HEAD_GLOB", PR_HEAD_GLOB)
    exempt_bases = {b.strip() for b in env("EXEMPT_BASE_REFS", "f6-gate-test").split(",") if b.strip()}
    stale_days = int(env("PR_STALE_DAYS", "7"))
    close_days = int(env("PR_CLOSE_DAYS", "14"))
    if not token:
        fail(MODE, "GH_TOKEN missing")

    denied, _never = fetch_manifest_denied(repo, env("DEFAULT_BRANCH", "main"))
    prs = paginate(f"/repos/{repo}/pulls?state=open", token=token, cap=50)
    now = datetime.now(timezone.utc)
    closed = 0
    labeled = 0

    for pr in prs:
        if pr.get("draft"):
            print("skipped:draft", pr["number"])
            continue
        user = (pr.get("user") or {}).get("login")
        if user != author:
            print("skipped:author", pr["number"])
            continue
        head = (pr.get("head") or {}).get("ref") or ""
        if not head_matches(head, head_glob):
            print("skipped:head", pr["number"])
            continue
        base = (pr.get("base") or {}).get("ref")
        if base in exempt_bases:
            print("skipped:base", pr["number"])
            continue
        ex = pr_exempt_labels(pr.get("labels"))
        if ex:
            print(f"skipped:{ex}", pr["number"])
            continue
        if changed_protected(token, repo, pr["number"], denied):
            print("skipped:protected-path", pr["number"])
            continue
        activity = last_human_activity(token, repo, pr["number"])
        if not activity:
            activity = parse_ts(pr.get("created_at"))
        age_days = (now - activity).total_seconds() / 86400.0
        labels = {l.get("name") for l in pr.get("labels") or []}
        if age_days < stale_days:
            if STALE_LABEL in labels and not dry_run():
                call(
                    f"/repos/{repo}/issues/{pr['number']}/labels/{STALE_LABEL}",
                    token=token,
                    method="DELETE",
                    allow_404=True,
                )
                print("removed stale", pr["number"])
            continue
        if STALE_LABEL not in labels:
            if dry_run():
                print("DRY-RUN stale label", pr["number"])
            else:
                call(
                    f"/repos/{repo}/issues/{pr['number']}/labels",
                    token=token,
                    method="POST",
                    body={"labels": [STALE_LABEL]},
                )
            labeled += 1
        if age_days >= close_days and close_allowed():
            write_token = app_token or token
            if dry_run():
                print("DRY-RUN close", pr["number"])
            else:
                call(
                    f"/repos/{repo}/issues/{pr['number']}/comments",
                    token=write_token,
                    method="POST",
                    body={"body": f"Closing stale agent PR. {CLOSE_MARKER}"},
                )
                call(
                    f"/repos/{repo}/pulls/{pr['number']}",
                    token=write_token,
                    method="PATCH",
                    body={"state": "closed"},
                )
                closed += 1
    print(f"labeled={labeled} closed={closed}")


if __name__ == "__main__":
    main()
