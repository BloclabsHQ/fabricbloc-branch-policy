"""Shared constants and GitHub API helpers for repo-hygiene scripts (stdlib only)."""
import fnmatch
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

SELF_REPO = "BloclabsHQ/fabricbloc-branch-policy"
DEFAULT_BASE_REF = "main"
MANIFEST = "agents/runtime/engine/policy/cursor-env/manifest.json"

FLOOR_DENIED = [
    "agents/runtime/engine/",
    "agents/agents.yaml",
    ".github/workflows/",
    ".github/actions/",
    "decisions/",
    "architecture/decisions/",
    "CODEOWNERS",
    ".github/CODEOWNERS",
    "docs/CODEOWNERS",
]

HYGIENE_EXTRA_PROTECTED = [
    "infra/",
    "ops/",
    "iac/",
    "**/iam/**",
    "**/*.tf",
    "architecture/SECRETS.md",
    "architecture/ENV_FILES.md",
    "policy/",
    "rulesets/",
]

# Floor never_allowlist (manifest may extend; hygiene always applies proposed_additions).
FLOOR_NEVER_ALLOWLIST = frozenset({
    "BloclabsHQ/fabric-iac",
    "BloclabsHQ/fabric-tss",
    "BloclabsHQ/fabric-contracts",
    "BloclabsHQ/fabric-auth",
    "BloclabsHQ/fabric-wallet",
    "BloclabsHQ/go-foundation",
    "BloclabsHQ/fabric-platform",
    "BloclabsHQ/github-actions",
    "BloclabsHQ/fabricbloc-branch-policy",
    "BloclabsHQ/context",
})

HOLD_LABELS = frozenset({"HOLD", "DO NOT MERGE"})
SPEC_LABELS = frozenset({"spec:draft", "spec:gate", "spec:ready", "blocked", "security"})

TARGET_REPOS = {"BloclabsHQ/fabricbloc"}

MAX_PAGES = 100

API = os.environ.get("API", "https://api.github.com").rstrip("/")
TOKEN = os.environ.get("GH_TOKEN", "")


def fail(mode, msg):
    print(f"::error::{mode}: {msg}")
    sys.exit(1)


def call(path, *, token=None, accept="application/vnd.github+json", allow_404=False, method="GET", body=None):
    tok = token if token is not None else TOKEN
    data = None
    headers = {
        "Authorization": f"Bearer {tok}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fabricbloc-hygiene",
    }
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None
        raise HygieneAPIError(exc.code, path.split("?")[0])
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HygieneAPIError(0, f"{type(exc).__name__}") from exc
    if accept.endswith(".raw") or accept.endswith("+raw"):
        return raw
    return json.loads(raw or "null")


class HygieneAPIError(Exception):
    def __init__(self, code, path):
        self.code = code
        self.path = path
        super().__init__(f"GitHub API {code} on {path}")


def paginate(path, *, cap=MAX_PAGES, token=None):
    out, page = [], 1
    while page <= cap:
        sep = "&" if "?" in path else "?"
        chunk = call(f"{path}{sep}page={page}&per_page=100", token=token)
        if not chunk:
            break
        if not isinstance(chunk, list):
            break
        out.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    if page > cap:
        raise HygieneAPIError(0, f"pagination cap {cap} on {path.split('?')[0]}")
    return out


def repo_short(full_name):
    return full_name.split("/", 1)[-1]


def path_matches_any(path, patterns):
    path = path or ""
    for pat in patterns:
        if fnmatch.fnmatch(path, pat) or path.startswith(pat.rstrip("*")):
            return True
        if pat.endswith("/") and path.startswith(pat):
            return True
    return False


def fetch_manifest_denied(repo, ref):
    try:
        raw = call(
            f"/repos/{repo}/contents/{urllib.parse.quote(MANIFEST, safe='')}?ref={urllib.parse.quote(ref, safe='')}",
            accept="application/vnd.github.raw",
        )
        data = json.loads(raw)
    except (HygieneAPIError, json.JSONDecodeError, TypeError):
        return list(FLOOR_DENIED), set(FLOOR_NEVER_ALLOWLIST)
    dp = (data.get("denied_paths") or {}) if isinstance(data, dict) else {}
    denied = list(FLOOR_DENIED)
    denied += list(dp.get("arch_0048_baseline") or [])
    denied += list(dp.get("proposed_additions") or [])
    denied += list(HYGIENE_EXTRA_PROTECTED)
    never = set(FLOOR_NEVER_ALLOWLIST)
    for name in data.get("never_allowlist") or []:
        if isinstance(name, str):
            never.add(name if "/" in name else f"BloclabsHQ/{name}")
    return denied, never


def dry_run(mode_env=None):
    mode = (mode_env or os.environ.get("HYGIENE_MODE") or "dry-run").strip().lower()
    return mode == "dry-run"


def hygiene_enabled(c_var, org_var=None):
    org = (org_var or os.environ.get("HYGIENE_ENABLED") or "").strip().lower()
    if org == "false":
        return False
    mode = (c_var or os.environ.get("HYGIENE_MODE") or "").strip().lower()
    return mode != "off"


MARKER_BOT_RE = re.compile(r"<!--\s*hygiene:([\w-]+):([^>]+)\s*-->")


def slack_post_message(token, channel, text, thread_ts=None):
    payload = {"channel": channel, "text": text, "unfurl_links": False, "unfurl_media": False}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    if not body.get("ok"):
        raise RuntimeError(body.get("error") or "slack error")
    return body.get("ts")
