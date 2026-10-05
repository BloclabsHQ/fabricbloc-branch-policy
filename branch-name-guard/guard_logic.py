#!/usr/bin/env python3
"""GOV-0022 branch naming (embedded in branch-name-guard.yml)."""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MODE = "branch-name-guard"
HUMAN_RE = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,37}[a-z0-9])?/"
    r"(feat|fix|chore|docs|refactor|test|ci|perf|revert|build|style)/"
    r"[a-z0-9]+(-[a-z0-9]+)*$"
)
PROVIDER_RE = re.compile(r"^(codex|claude|qwen)/")
LEGACY_AGENT_RE = re.compile(
    r"^agent/(session|autonomous)/"
    r"(feat|fix|chore|docs|refactor|test|ci|perf|revert|build|style)/"
    r"[a-z0-9]+(-[a-z0-9]+)+$"
)
KINDS = ("chore", "feat", "fix", "test")
API = os.environ.get("API", "https://api.github.com").rstrip("/")
TOKEN = os.environ.get("GH_TOKEN", "")


def fail(msg):
    print(f"::error::{MODE}: {msg}")
    sys.exit(1)


def load_bots():
    raw = os.environ.get("BOTS_JSON", "").strip()
    if raw:
        data = json.loads(raw)
    else:
        path = Path(__file__).resolve().parents[1] / "rulesets" / "bots.json"
        data = json.loads(path.read_text())
    bots = data.get("bots") or []
    out = []
    for b in bots:
        if not isinstance(b, str) or not re.fullmatch(r"[a-z0-9-]+", b):
            fail(f"invalid bot slug {b!r} in bots.json")
        out.append(b)
    if not out:
        fail("bots.json has no bots")
    return out


def bot_agent_re(bots):
    alt = "|".join(re.escape(b) for b in bots)
    return re.compile(
        rf"^agent/({alt})/({'|'.join(KINDS)})/[a-z0-9-]+$"
    )


def parse_legacy_until(raw):
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def branch_had_commits_before(repo, branch, until_dt, token):
    if not token:
        return False
    until = until_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    q_branch = urllib.parse.quote(branch, safe="")
    path = f"/repos/{repo}/commits?sha={q_branch}&until={until}&per_page=1"
    req = urllib.request.Request(
        API + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "branch-name-guard",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode() or "[]")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return False
    return bool(data)


def attributed_bot(branch, bots):
    m = bot_agent_re(bots).match(branch)
    if m:
        return m.group(1)
    m = LEGACY_AGENT_RE.match(branch)
    if m:
        slug = branch.split("/")[-1]
        if "-" in slug:
            return slug.split("-", 1)[0].lower()
    return ""


def validate(branch, base_branches, bots, legacy_until, repo, token):
    for b in base_branches:
        if branch == b:
            print(f"{MODE}: '{branch}' is a base branch, exempt.")
            return 0
    if branch.startswith("agent/"):
        new_re = bot_agent_re(bots)
        if new_re.match(branch):
            bot = attributed_bot(branch, bots)
            print(f"::notice title=attributed_bot::{bot}")
            print(f"{MODE}: '{branch}' matches agent/<bot> grammar.")
            return 0
        if LEGACY_AGENT_RE.match(branch):
            now = datetime.now(timezone.utc)
            if legacy_until is None or now < legacy_until:
                bot = attributed_bot(branch, bots)
                if bot:
                    print(f"::notice title=attributed_bot::{bot}")
                print(f"{MODE}: '{branch}' matches legacy agent grammar (dual-accept).")
                return 0
            if branch_had_commits_before(repo, branch, legacy_until, token):
                bot = attributed_bot(branch, bots)
                if bot:
                    print(f"::notice title=attributed_bot::{bot}")
                print(f"{MODE}: legacy branch pre-dates LEGACY_BRANCH_ACCEPT_UNTIL.")
                return 0
            fail(
                f"'{branch}' uses legacy agent/session grammar after "
                f"LEGACY_BRANCH_ACCEPT_UNTIL; use agent/<bot>/{{chore|feat|fix|test}}/<slug>"
            )
        fail(f"'{branch}' does not match agent naming convention.")
    if PROVIDER_RE.match(branch):
        fail(f"'{branch}' uses blocked provider prefix.")
    if HUMAN_RE.match(branch):
        print(f"{MODE}: '{branch}' matches human convention.")
        return 0
    fail(f"'{branch}' does not match the FabricBloc naming convention.")


def main():
    branch = os.environ.get("BRANCH", "")
    if not branch:
        fail("BRANCH is empty")
    base = os.environ.get("BASE_BRANCHES", "main,dev,master")
    base_branches = [b.strip() for b in base.split(",") if b.strip()]
    legacy_until = parse_legacy_until(os.environ.get("LEGACY_BRANCH_ACCEPT_UNTIL", ""))
    bots = load_bots()
    repo = os.environ.get("REPO", "")
    token = os.environ.get("GH_TOKEN", "")
    sys.exit(
        validate(branch, base_branches, bots, legacy_until, repo, token)
    )


if __name__ == "__main__":
    main()
