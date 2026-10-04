#!/usr/bin/env python3
"""C1 pr-ops Slack notifier (logic aligned with fabricbloc #1562 scripts/pr-ops-notify.py @4967d8c).

Uses GitHub REST + Slack Web API only. Never checks out PR head code.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from common import HygieneAPIError, call, dry_run, fail, paginate

MODE = "hygiene-c1-pr-ops-notify"
MARKER_RE = re.compile(
    r"<!--\s*fabricbloc-pr-ops-thread-ts=(?P<ts>\d+(?:\.\d+)?)"
    r"(?:\s+ready-sha=(?P<ready>[0-9a-f]{40}|))?"
    r"(?:\s+lifecycle=(?P<life>\w+))?\s*-->",
    re.I,
)
INTEGRATION_GITHUB_ACTIONS = 15368


def env(name, default=""):
    return os.environ.get(name, default)


def slack_post(token, channel, text, thread_ts=None):
    payload = {"channel": channel, "text": text, "unfurl_links": False, "unfurl_media": False}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    if not body.get("ok"):
        raise RuntimeError(body.get("error") or "slack error")
    return body.get("ts")


def alert_fail(token, alert_channel, msg):
    if token and alert_channel:
        try:
            slack_post(token, alert_channel, f":rotating_light: {MODE}: {msg}")
        except Exception:
            pass
    fail(MODE, msg)


def parse_marker(body):
    m = MARKER_RE.search(body or "")
    if not m:
        return {}
    out = {"thread_ts": m.group("ts")}
    if m.group("ready"):
        out["ready_sha"] = m.group("ready")
    if m.group("life"):
        out["lifecycle"] = m.group("life").lower()
    return out


def marker_comment(comments, authors):
    author_set = {a.strip().lower() for a in authors.split(",") if a.strip()}
    for c in comments:
        login = ((c.get("user") or {}).get("login") or "").lower()
        if author_set and login not in author_set:
            continue
        parsed = parse_marker(c.get("body"))
        if parsed:
            return c, parsed
    return None, {}


def upsert_marker(token, repo, pr, comment_id, body):
    if comment_id:
        call(
            f"/repos/{repo}/issues/comments/{comment_id}",
            token=token,
            method="PATCH",
            body={"body": body},
        )
    else:
        call(f"/repos/{repo}/issues/{pr}/comments", token=token, method="POST", body={"body": body})


def build_marker(thread_ts, ready_sha=None, lifecycle=None):
    parts = [f"<!-- fabricbloc-pr-ops-thread-ts={thread_ts}"]
    if ready_sha:
        parts.append(f" ready-sha={ready_sha}")
    if lifecycle:
        parts.append(f" lifecycle={lifecycle}")
    parts.append(" -->")
    return "".join(parts)


def skip_head(ref, globs):
    ref = ref or ""
    for g in globs:
        g = g.strip()
        if not g:
            continue
        if g.endswith("*"):
            if ref.startswith(g[:-1]):
                return True
        elif ref == g:
            return True
    return False


def required_contexts(repo, base_ref):
    rules = call(f"/repos/{repo}/rules/branches/{urllib.parse.quote(base_ref, safe='')}")
    contexts = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        rtype = rule.get("type")
        params = rule.get("parameters") or {}
        if rtype == "required_status_checks":
            for chk in params.get("required_status_checks") or []:
                if isinstance(chk, dict) and chk.get("context"):
                    contexts.append(chk)
        if rtype == "workflows":
            for wf in (params.get("workflows") or []):
                if isinstance(wf, dict) and wf.get("path"):
                    contexts.append({"context": wf["path"].split("/")[-1].replace(".yml", ""), "integration_id": INTEGRATION_GITHUB_ACTIONS})
    return contexts


def checks_green(repo, sha, contexts):
    if not contexts:
        return False, "no required contexts from rules API"
    combined = call(f"/repos/{repo}/commits/{sha}/check-runs?per_page=100")
    runs = (combined or {}).get("check_runs") or []
    statuses = call(f"/repos/{repo}/commits/{sha}/status")
    status_list = (statuses or {}).get("statuses") or []
    for ctx in contexts:
        name = ctx.get("context")
        iid = ctx.get("integration_id")
        matched = False
        for run in runs:
            if run.get("name") != name:
                continue
            if iid is not None and run.get("app", {}).get("id") != iid:
                continue
            matched = True
            if run.get("conclusion") != "success":
                return False, f"check-run {name}={run.get('conclusion')}"
            break
        if matched:
            continue
        for st in status_list:
            if st.get("context") != name:
                continue
            if iid is not None and (st.get("creator", {}) or {}).get("id") != iid:
                continue
            matched = True
            if st.get("state") != "success":
                return False, f"status {name}={st.get('state')}"
            break
        if not matched:
            return False, f"missing context {name}"
    return True, "ok"


def format_open(pr, repo):
    return (
        f"*OPEN* `{repo}` PR #{pr['number']}: {pr.get('title')}\n"
        f"{pr.get('html_url')}\n"
        f"head `{pr.get('head', {}).get('ref')}` → `{pr.get('base', {}).get('ref')}`"
    )


def format_ready(pr, repo):
    return f"*READY* `{repo}` PR #{pr['number']}: {pr.get('html_url')}"


def format_closed(pr, repo, merged):
    tag = "MERGED" if merged else "CLOSED"
    return f"*{tag}* `{repo}` PR #{pr['number']}: {pr.get('html_url')}"


def process_pr(token, slack_token, repo, pr_number, *, event_action=None, sweep=False):
    channel = env("CHANNEL", "C0C531H03M4")
    alert_channel = env("ALERT_CHANNEL", "C0C29LWFABZ")
    authors = env("MARKER_AUTHORS", "github-actions[bot]")
    skip_globs = [g for g in env("SKIP_HEAD_GLOBS", "").split(",") if g.strip()]
    is_dry = dry_run()

    pr = call(f"/repos/{repo}/pulls/{pr_number}", token=token)
    if not pr:
        fail(MODE, f"PR #{pr_number} not found")

    head_ref = (pr.get("head") or {}).get("ref") or ""
    if skip_head(head_ref, skip_globs):
        print(f"skip_head_glob ref={head_ref}")
        return

    comments = paginate(f"/repos/{repo}/issues/{pr_number}/comments", token=token)
    marker_c, marker = marker_comment(comments, authors)
    thread_ts = marker.get("thread_ts")
    lifecycle = marker.get("lifecycle")

    merged = bool(pr.get("merged_at"))
    state = pr.get("state")
    draft = bool(pr.get("draft"))

    action = event_action or env("EVENT_ACTION", "")
    if sweep and state == "open":
        action = action or "sweep"

    if state == "closed":
        if lifecycle == "closed":
            print("lifecycle already closed")
            return
        msg = format_closed(pr, repo, merged)
        if is_dry:
            print(f"DRY-RUN would post: {msg}")
        else:
            if not thread_ts:
                thread_ts = slack_post(slack_token, channel, format_open(pr, repo))
            slack_post(slack_token, channel, msg, thread_ts=thread_ts)
            body = build_marker(thread_ts, marker.get("ready_sha"), lifecycle="closed")
            upsert_marker(token, repo, pr_number, (marker_c or {}).get("id"), body)
        return

    if not thread_ts and action in ("opened", "reopened", "ready_for_review", "sweep", ""):
        msg = format_open(pr, repo)
        if is_dry:
            print(f"DRY-RUN would OPEN: {msg}")
            thread_ts = "dry-run-ts"
        else:
            thread_ts = slack_post(slack_token, channel, msg)
            body = build_marker(thread_ts)
            upsert_marker(token, repo, pr_number, (marker_c or {}).get("id"), body)
        if draft:
            return

    head_sha = (pr.get("head") or {}).get("sha") or ""
    base_ref = (pr.get("base") or {}).get("ref") or "main"
    if draft:
        return

    ready_sha = marker.get("ready_sha")
    if ready_sha == head_sha:
        print(f"ready-sha already {head_sha[:7]}")
        return

    contexts = required_contexts(repo, base_ref)
    green, reason = checks_green(repo, head_sha, contexts)
    if not green:
        print(f"not ready: {reason}")
        return

    if not thread_ts:
        print("READY skipped: no thread (READY never opens root)")
        return

    msg = format_ready(pr, repo)
    if is_dry:
        print(f"DRY-RUN would READY: {msg}")
    else:
        slack_post(slack_token, channel, msg, thread_ts=thread_ts)
        body = build_marker(thread_ts, ready_sha=head_sha, lifecycle=marker.get("lifecycle"))
        upsert_marker(token, repo, pr_number, (marker_c or {}).get("id"), body)


def sweep_open_prs(token, slack_token, repo):
    prs = paginate(f"/repos/{repo}/pulls?state=open&base={env('DEFAULT_BRANCH', 'main')}", token=token, cap=20)
    for pr in prs:
        process_pr(token, slack_token, repo, pr["number"], sweep=True)


def main():
    token = env("GH_TOKEN")
    slack_token = env("SLACK_BOT_TOKEN")
    repo = env("REPO")
    if not token:
        fail(MODE, "GH_TOKEN missing")
    if not slack_token:
        alert_fail("", env("ALERT_CHANNEL", "C0C29LWFABZ"), "SLACK_BOT_TOKEN missing")

    try:
        pr_number = env("PR_NUMBER")
        if env("SWEEP", "").lower() in ("1", "true", "yes"):
            sweep_open_prs(token, slack_token, repo)
        elif pr_number:
            process_pr(
                token,
                slack_token,
                repo,
                int(pr_number),
                event_action=env("EVENT_ACTION"),
            )
        else:
            fail(MODE, "PR_NUMBER or SWEEP required")
    except HygieneAPIError as exc:
        alert_fail(slack_token, env("ALERT_CHANNEL", "C0C29LWFABZ"), str(exc))
    except RuntimeError as exc:
        alert_fail(slack_token, env("ALERT_CHANNEL", "C0C29LWFABZ"), str(exc))


if __name__ == "__main__":
    main()
