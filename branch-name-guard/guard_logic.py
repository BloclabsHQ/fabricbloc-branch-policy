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
PROVIDER_PREFIX_RE = re.compile(r"^(codex|claude|qwen|cursor)/.+$")
AGENT_TYPES = (
    "feat", "fix", "chore", "docs", "refactor", "test", "ci", "perf", "revert", "build", "style",
)
SLUG = r"[a-z0-9]+(-[a-z0-9]+)+"
TYPES_ALT = "|".join(AGENT_TYPES)
RESERVED_BOT_SLUGS = frozenset({"session", "autonomous", "cursor", "codex", "claude", "qwen"})
LEGACY_AGENT_RE = re.compile(rf"^agent/(session|autonomous)/({TYPES_ALT})/{SLUG}$")
AGENT_PROVIDER_PREFIX_RE = re.compile(r"^agent/(codex|claude|qwen|cursor)/.+$")
# Embedded from rulesets/canon.json (re-pin with branch_name_guard_sha when bots.json changes on main).
CANON_LEGACY_BRANCH_PR_CREATED_BEFORE = "2026-10-19T00:00:00Z"
CANON_BOTS_JSON_SHA = "80ee4b19ad84f4cdb5dc1e923e19f54fc54a2c6a"
SYNCED_BOT_SLUGS = ['aether', 'anvil', 'cursoragent', 'loom', 'madagentpm', 'madengineer', 'madgeniusbot', 'sentinel', 'sweeper', 'warden']  # auto-sync from rulesets/bots.json
API = os.environ.get("API", "https://api.github.com").rstrip("/")


def fail(msg):
    print(f"::error::{MODE}: {msg}")
    sys.exit(1)


def warn(msg):
    print(f"::warning::{MODE}: {msg}")


def _has_explicit_tz(text):
    if text.endswith("Z"):
        return True
    if len(text) >= 6 and text[-6] in "+-" and text[-3] == ":":
        return True
    if len(text) >= 5 and text[-5] in "+-" and text[-3].isdigit():
        return True
    return False


def parse_timestamp(raw, label):
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    elif not _has_explicit_tz(text):
        if "T" not in text:
            fail(f"{label} must be ISO-8601 with timezone (got {raw!r})")
        text = text + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        fail(f"{label} is not valid ISO-8601: {raw!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def effective_legacy_cutoff():
    canon = parse_timestamp(CANON_LEGACY_BRANCH_PR_CREATED_BEFORE, "canon legacy_branch_pr_created_before")
    raw = os.environ.get("LEGACY_BRANCH_PR_CREATED_BEFORE", "").strip()
    if not raw:
        return canon
    var = parse_timestamp(raw, "LEGACY_BRANCH_PR_CREATED_BEFORE")
    if var > canon:
        warn(
            f"LEGACY_BRANCH_PR_CREATED_BEFORE {raw!r} is later than canon "
            f"{CANON_LEGACY_BRANCH_PR_CREATED_BEFORE}; using canon (var may only move cutoff earlier)"
        )
        return canon
    return var


def api_get_json(path, token):
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
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        fail(f"GitHub API error on {path.split('?')[0]}: {exc}")


def ref_is_on_main_history(policy_repo, token, ref):
    """True when ref is main or an ancestor of main (trusted policy pin)."""
    if ref in ("main", "refs/heads/main"):
        return True
    base = urllib.parse.quote(ref, safe="")
    head = urllib.parse.quote("main", safe="")
    try:
        data = api_get_json(f"/repos/{policy_repo}/compare/{base}...{head}", token)
    except urllib.error.HTTPError:
        return False
    # base=pin, head=main: ancestor pin yields status "ahead" (main is ahead of pin).
    return (data or {}).get("status") in ("ahead", "identical")


def fetch_bots_json_at_ref(policy_repo, token, ref):
    q = urllib.parse.quote("rulesets/bots.json", safe="")
    req = urllib.request.Request(
        f"{API}/repos/{policy_repo}/contents/{q}?ref={urllib.parse.quote(ref, safe='')}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.raw",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "branch-name-guard",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_bots_json_from_api():
    """Trusted refs only (org pin + main) — never PR head."""
    policy_repo = os.environ.get("POLICY_REPO", "BloclabsHQ/fabricbloc-branch-policy")
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        return None
    pin = os.environ.get("POLICY_BOTS_JSON_SHA", "").strip() or CANON_BOTS_JSON_SHA
    refs = []
    for ref in (pin, "main"):
        if ref and ref not in refs:
            refs.append(ref)
    last_exc = None
    for ref in refs:
        if ref != "main" and not ref_is_on_main_history(policy_repo, token, ref):
            fail(
                f"POLICY_BOTS_JSON_SHA {ref!r} is not on main history; "
                f"refusing untrusted rulesets/bots.json"
            )
        try:
            return fetch_bots_json_at_ref(policy_repo, token, ref)
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code == 404:
                continue
            fail(f"cannot load rulesets/bots.json from {policy_repo}@{ref}: {exc}")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            fail(f"cannot load rulesets/bots.json from {policy_repo}@{ref}: {exc}")
    if last_exc:
        warn(
            f"rulesets/bots.json not found at pinned refs ({', '.join(refs)}); "
            f"using SYNCED_BOT_SLUGS from policy sync"
        )
    return None


def _bots_from_data(data):
    bots = []
    for b in data.get("bots") or []:
        if not isinstance(b, str) or not re.fullmatch(r"[a-z0-9-]+", b):
            fail(f"invalid bot slug {b!r} in bots.json")
        low = b.lower()
        if low in RESERVED_BOT_SLUGS:
            fail(f"bot slug {b!r} is reserved (session/autonomous/provider)")
        bots.append(low)
    if not bots:
        fail("bots.json has no bots")
    return bots


def load_bots():
    raw = os.environ.get("BOTS_JSON", "").strip()
    if raw:
        return _bots_from_data(json.loads(raw))
    try:
        path = Path(__file__).resolve().parents[1] / "rulesets" / "bots.json"
    except (RuntimeError, OSError, IndexError):
        path = None
    if path is not None and path.is_file():
        return _bots_from_data(json.loads(path.read_text()))
    data = fetch_bots_json_from_api()
    if data is not None:
        return _bots_from_data(data)
    if not SYNCED_BOT_SLUGS:
        fail("cannot load rulesets/bots.json and SYNCED_BOT_SLUGS is empty")
    return list(SYNCED_BOT_SLUGS)


def bot_agent_re(bots):
    alt = "|".join(re.escape(b) for b in bots)
    return re.compile(rf"^agent/({alt})/({TYPES_ALT})/{SLUG}$")


def parse_pr_created_at(raw):
    if not raw or not raw.strip():
        return None
    return parse_timestamp(raw, "PR created_at")


def legacy_allowed_for_pr(legacy_cutoff, pr_created_at):
    """After cutoff, legacy branch names only for PRs opened before cutoff."""
    now = datetime.now(timezone.utc)
    if now < legacy_cutoff:
        return True
    created = parse_pr_created_at(pr_created_at)
    if created is None:
        return False
    return created < legacy_cutoff


def attributed_bot(branch, bots):
    """Routing hint only — not authority (GOV-0033 D5)."""
    m = bot_agent_re(bots).fullmatch(branch)
    if m:
        return m.group(1)
    m = LEGACY_AGENT_RE.fullmatch(branch)
    if m:
        slug = branch.split("/")[-1]
        if "-" in slug:
            return slug.split("-", 1)[0].lower()
    return ""


def validate(branch, base_branches, bots, legacy_cutoff, pr_created_at):
    for b in base_branches:
        if branch == b:
            print(f"{MODE}: '{branch}' is a base branch, exempt.")
            return 0
    if branch.startswith("agent/"):
        if AGENT_PROVIDER_PREFIX_RE.fullmatch(branch):
            fail(f"'{branch}' uses blocked provider-style agent prefix (bot slugs are role IDs, not providers)")
        new_re = bot_agent_re(bots)
        if new_re.fullmatch(branch):
            bot = attributed_bot(branch, bots)
            print(f"::notice title=attributed_bot::{bot}")
            print(f"{MODE}: '{branch}' matches agent/<bot>/<type>/<scope>-<slug> (routing hint only).")
            return 0
        if LEGACY_AGENT_RE.fullmatch(branch):
            if legacy_allowed_for_pr(legacy_cutoff, pr_created_at):
                bot = attributed_bot(branch, bots)
                if bot:
                    print(f"::notice title=attributed_bot::{bot}")
                print(f"{MODE}: '{branch}' matches legacy session/autonomous grammar.")
                return 0
            fail(
                f"'{branch}' uses legacy agent/(session|autonomous)/ grammar for a PR opened after "
                f"LEGACY_BRANCH_PR_CREATED_BEFORE; use agent/<bot>/{{type}}/{{scope}}-{{slug}} "
                f"(see BR-01 / bots.json)"
            )
        fail(f"'{branch}' does not match agent naming convention.")
    if PROVIDER_PREFIX_RE.fullmatch(branch):
        fail(f"'{branch}' uses blocked provider prefix.")
    if HUMAN_RE.fullmatch(branch):
        print(f"{MODE}: '{branch}' matches human convention.")
        return 0
    fail(f"'{branch}' does not match the FabricBloc naming convention.")


def main():
    branch = os.environ.get("BRANCH", "")
    if not branch:
        fail("BRANCH is empty")
    base = os.environ.get("BASE_BRANCHES", "main,dev,master")
    base_branches = [b.strip() for b in base.split(",") if b.strip()]
    legacy_cutoff = effective_legacy_cutoff()
    pr_created_at = os.environ.get("PR_CREATED_AT", "")
    bots = load_bots()
    sys.exit(validate(branch, base_branches, bots, legacy_cutoff, pr_created_at))


if __name__ == "__main__":
    main()
