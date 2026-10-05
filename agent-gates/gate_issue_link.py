#!/usr/bin/env python3
"""Org gate: PR body must link an open issue (read-only GitHub API)."""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SELF_REPO = "BloclabsHQ/fabricbloc-branch-policy"
DEPENDABOT = "dependabot[bot]"
NO_ISSUE_LABEL = "no-issue"
NO_ISSUE_LABELER = "madgeniusblink"
CLOSING_RE = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b"
)
CROSS_REPO_RE = re.compile(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)\b")
MODE = "gate-issue-link"
API = os.environ.get("API", "https://api.github.com").rstrip("/")
TOKEN = os.environ.get("GH_TOKEN", "")
REPO = os.environ.get("REPO", "")


def fail(msg):
    print(f"::error::{MODE}: {msg}")
    sys.exit(1)


def warn(msg):
    print(f"::warning::{MODE}: {msg}")


def call(path, accept="application/vnd.github+json", allow_404=False):
    req = urllib.request.Request(
        API + path,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "fabricbloc-gate-issue-link",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None
        fail(f"GitHub API {exc.code} on {path.split('?')[0]}; failing closed")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        fail(f"GitHub API unreachable ({type(exc).__name__}); failing closed")
    return json.loads(body or "null")


def parse_enforce_after(raw):
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        fail(f"ISSUE_LINK_ENFORCE_AFTER is not ISO-8601: {raw!r}")


def enforce_mode():
    raw = os.environ.get("ISSUE_LINK_ENFORCE_AFTER", "")
    deadline = parse_enforce_after(raw)
    if deadline is None:
        return "closed"
    now = datetime.now(timezone.utc)
    if now < deadline:
        return "warn"
    return "closed"


def parse_issue_refs(body, default_repo):
    refs = []
    seen = set()
    for m in CLOSING_RE.finditer(body or ""):
        num = int(m.group(1))
        key = (default_repo, num)
        if key not in seen:
            seen.add(key)
            refs.append(key)
    for m in CROSS_REPO_RE.finditer(body or ""):
        repo = m.group(1)
        num = int(m.group(2))
        key = (repo, num)
        if key not in seen:
            seen.add(key)
            refs.append(key)
    return refs


def issue_is_valid_open_issue(owner_repo, number):
    owner, name = owner_repo.split("/", 1)
    item = call(f"/repos/{owner}/{name}/issues/{number}", allow_404=True)
    if item is None:
        return False, f"issue {owner_repo}#{number} not found"
    if item.get("pull_request"):
        return False, f"{owner_repo}#{number} is a pull request, not an issue"
    if (item.get("state") or "").lower() != "open":
        return False, f"issue {owner_repo}#{number} is not open"
    return True, None


def label_applied_by_madgeniusblink(repo, pr_number):
    events = call(f"/repos/{repo}/issues/{pr_number}/events?per_page=100")
    if not isinstance(events, list):
        fail("unexpected issue events shape")
    for ev in reversed(events):
        if ev.get("event") != "labeled":
            continue
        label = (ev.get("label") or {}).get("name") or ""
        if label.lower() != NO_ISSUE_LABEL:
            continue
        actor = (ev.get("actor") or {}).get("login") or ""
        if actor.lower() == NO_ISSUE_LABELER:
            return True
        return False
    return False


def pr_has_audited_no_issue(repo, pr_number, labels):
    names = {(lab.get("name") or "").lower() for lab in labels or []}
    if NO_ISSUE_LABEL not in names:
        return False
    return label_applied_by_madgeniusblink(repo, pr_number)


def check_labeled_event(payload):
    action = payload.get("action") or ""
    if action != "labeled":
        return
    label = (payload.get("label") or {}).get("name") or ""
    if label.lower() != NO_ISSUE_LABEL:
        return
    actor = (payload.get("sender") or {}).get("login") or ""
    if actor.lower() != NO_ISSUE_LABELER:
        fail(
            f"label {NO_ISSUE_LABEL!r} may only be applied by {NO_ISSUE_LABELER}; "
            f"got {actor!r}"
        )


def finish(violations, mode):
    if not violations:
        print(f"{MODE}: issue link requirement satisfied")
        return
    summary = "; ".join(violations)
    if mode == "warn":
        warn(f"phase-in (ISSUE_LINK_ENFORCE_AFTER not reached): {summary}")
        print(f"## {MODE} (warn-only)\n\n{summary}")
        return
    fail(summary)


def main():
    if not TOKEN.strip():
        fail("GH_TOKEN is empty")
    if REPO == SELF_REPO:
        print(f"{MODE}: policy repo; nothing to gate.")
        return
    number = os.environ.get("PR", "")
    if not number.isdigit():
        fail("missing pull request number")
    mode = enforce_mode()
    payload_raw = os.environ.get("EVENT_PAYLOAD", "")
    if payload_raw.strip():
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            fail("EVENT_PAYLOAD is not valid JSON")
        check_labeled_event(payload)
    pr = call(f"/repos/{REPO}/pulls/{number}")
    author = ((pr.get("user") or {}).get("login") or "").lower()
    if author == DEPENDABOT.lower():
        print(f"{MODE}: dependabot exempt")
        return
    if pr_has_audited_no_issue(REPO, int(number), pr.get("labels")):
        print(f"{MODE}: no-issue label exempt (applied by {NO_ISSUE_LABELER})")
        return
    body = pr.get("body") or ""
    refs = parse_issue_refs(body, REPO)
    violations = []
    if not refs:
        violations.append(
            "PR body needs Closes|Fixes|Resolves #N or owner/repo#N linking an open issue"
        )
    else:
        for owner_repo, num in refs:
            ok, reason = issue_is_valid_open_issue(owner_repo, num)
            if not ok:
                violations.append(reason)
    finish(violations, mode)


if __name__ == "__main__":
    main()
