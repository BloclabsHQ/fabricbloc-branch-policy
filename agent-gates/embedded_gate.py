# F6 agent gate. Canonical copy is embedded, byte-identical, in
# agent-denied-paths.yml and agent-review-of-record.yml (agent-gates/sync_embedded_gate.py
# and agent-gates/test.py enforce that). It never checks out or executes pull-request code:
# every input is the event payload plus GitHub REST reads of the PR and of the BASE
# commit. Python stdlib only. Any API error or ambiguity fails closed.
import json, os, re, sys, urllib.error, urllib.parse, urllib.request

SELF_REPO = "BloclabsHQ/fabricbloc-branch-policy"
TARGET_REPOS = {"BloclabsHQ/fabricbloc"}
DEFAULT_BASE_REF = "main"
MANIFEST = "agents/runtime/engine/policy/cursor-env/manifest.json"
ENGINE_CONFIG = "agents/runtime/engine/config.yaml"
# Floor: applies even if a later human PR thins the base manifest.
FLOOR_DENIED = [
    "agents/runtime/engine/", "agents/agents.yaml", ".github/workflows/",
    ".github/actions/", "decisions/", "architecture/decisions/",
    "CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS",
]
INCLUDE_PROPOSED = False  # flip to True (and re-pin) once FOUNDER-DECISIONS Q9 = yes
AGENT_USER_IDS = {199161495}
AGENT_LOGINS = {"cursoragent"}
AGENT_EMAILS = {"cursoragent@cursor.com", "199161495+cursoragent@users.noreply.github.com"}
# Dedicated reviewer GitHub App (fabricbloc-reviewer). Cris fills after App creation:
#   REVIEWER_APP_BOTS = {("fabricbloc-reviewer[bot]", <id from GET /users/fabricbloc-reviewer%5Bbot%5D>)}
# Empty until then: no App approval can count (fail closed). Re-pin ruleset SHA after change.
REVIEWER_APP_BOTS = set()
APPROVAL_REF_RE = re.compile(
    r"approval-ref:\s*(slack:\d+\.\d+|cli:[A-Za-z0-9._-]{6,64})")
HUMAN_RE = re.compile(r"^([a-z0-9]([a-z0-9-]{0,37}[a-z0-9])?)/(feat|fix|chore|docs|refactor|test|ci|perf|revert|build|style)/[a-z0-9]+(-[a-z0-9]+)*$")
MAX_FILES = 3000   # pulls/{n}/files hard limit
MAX_COMMITS = 250  # pulls/{n}/commits hard limit

API = os.environ.get("API", "https://api.github.com").rstrip("/")
TOKEN = os.environ.get("GH_TOKEN", "")
MODE = os.environ.get("MODE", "")
REPO = os.environ.get("REPO", "")


def fail(msg):
    print(f"::error::{MODE}: {msg}")
    sys.exit(1)


def is_reviewer_app(login, user_id, bots):
    if not login or user_id is None:
        return False
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    return (login, uid) in bots


def reviewer_app_body_ok(body, head):
    text = body or ""
    if head not in text:
        return False, f"review body lacks full 40-char head SHA {head}"
    if not APPROVAL_REF_RE.search(text):
        return False, (
            "review body lacks approval-ref matching "
            "approval-ref: (slack:<ts>|cli:<token>)")
    return True, None


def call(path, accept="application/vnd.github+json", allow_404=False):
    req = urllib.request.Request(API + path, headers={
        "Authorization": f"Bearer {TOKEN}", "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "fabricbloc-agent-gates"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None
        fail(f"GitHub API {exc.code} on {path.split('?')[0]}; failing closed")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        fail(f"GitHub API unreachable ({type(exc).__name__}); failing closed")
    return body if accept.endswith(".raw") else json.loads(body or "null")


def paginate(path, cap):
    out, page = [], 1
    while True:
        sep = "&" if "?" in path else "?"
        batch = call(f"{path}{sep}per_page=100&page={page}")
        if not isinstance(batch, list):
            fail(f"unexpected API shape for {path}")
        out += batch
        if len(batch) < 100 or len(out) >= cap:
            return out
        page += 1


def base_text(path, sha):
    q = urllib.parse.quote(path)
    return call(f"/repos/{REPO}/contents/{q}?ref={sha}", "application/vnd.github.raw", allow_404=True)


def is_agent(login=None, email=None, user_id=None):
    try:
        if user_id is not None and int(user_id) in AGENT_USER_IDS:
            return True
    except (TypeError, ValueError):
        pass
    if login:
        l = login.strip().lower()
        if l in AGENT_LOGINS or l.endswith("[bot]"):
            return True
    e = (email or "").strip().lower()
    return e in AGENT_EMAILS or e.endswith("[bot]@users.noreply.github.com")


def _parse_flow_list_items(inner):
    """Split flow-list inner text into items (unquoted, single- or double-quoted)."""
    items = []
    i, n = 0, len(inner)

    def skip_sep():
        nonlocal i
        while i < n and inner[i] in " \t\n\r,":
            i += 1

    while True:
        skip_sep()
        if i >= n:
            break
        if inner[i] == "'":
            i += 1
            start = i
            while i < n and inner[i] != "'":
                i += 1
            if i >= n:
                return None
            items.append(inner[start:i])
            i += 1
        elif inner[i] == '"':
            i += 1
            start = i
            while i < n and inner[i] != '"':
                i += 1
            if i >= n:
                return None
            items.append(inner[start:i])
            i += 1
        else:
            start = i
            while i < n and inner[i] != ",":
                i += 1
            token = inner[start:i].strip()
            if not token:
                return None
            items.append(token)
    skip_sep()
    if i < n:
        return None
    return items


def parse_flow_list_line(cfg, key):
    """Parse a one-line YAML flow list like [a, 'b[bot]'] (quoted strings may contain ])."""
    if not cfg:
        return None
    if not re.search(rf"^\s*{key}:", cfg, re.M):
        return None
    m = re.search(rf"^\s*{key}:\s*\[(.*)\]\s*$", cfg, re.M)
    if not m:
        return False
    parsed = _parse_flow_list_items(m.group(1))
    if parsed is None:
        return False
    out = {s.strip() for s in parsed if s.strip()}
    return out


def ai_reviewers_from_cfg(cfg):
    parsed = parse_flow_list_line(cfg, "ai_reviewers")
    if parsed is None:
        return set()
    if parsed is False:
        fail(
            "base config.yaml has ai_reviewers: but it is not a one-line flow list "
            "[a, b]; failing closed")
    return parsed


def agent_identity_in_pr(author, author_type, author_id, commits):
    """Agent identity from PR author or any commit (not head-ref prefix alone)."""
    if author_type == "Bot" or is_agent(login=author, user_id=author_id):
        return True
    for c in commits:
        inner = c.get("commit") or {}
        for top, key in (("author", "author"), ("committer", "committer")):
            node = c.get(top) or {}
            login = node.get("login")
            uid = node.get("id")
            email = (inner.get(key) or {}).get("email")
            if is_agent(login=login, email=email, user_id=uid):
                return True
    return False


def gate_applies(head_ref, author, author_type, author_id, commits, humans, ai_reviewers, reviewer_bots):
    why = []
    if head_ref.lower().startswith("agent/"):
        why.append("agent/** head ref")
    if author_type == "Bot" or is_agent(login=author, user_id=author_id):
        why.append(f"agent PR author {author}")
    for c in commits:
        inner = c.get("commit") or {}
        for top, key in (("author", "author"), ("committer", "committer")):
            node = c.get(top) or {}
            login = node.get("login")
            uid = node.get("id")
            email = (inner.get(key) or {}).get("email")
            if is_agent(login=login, email=email, user_id=uid):
                why.append(f"agent commit identity {login or email} on {c.get('sha', '')[:12]}")
    if why:
        return True, why
    if is_reviewer_app(author, author_id, reviewer_bots):
        return True, ["reviewer App author never qualifies for human skip"]
    m = HUMAN_RE.match(head_ref)
    if (author in humans and author not in ai_reviewers
            and m and m.group(1) == author.lower()):
        return False, ["GOV-0022 human ref owned by an allowlisted human author, no agent commits"]
    return True, ["default deny: not a recognised human PR"]


def manifest_at(sha):
    text = base_text(MANIFEST, sha)
    if text is None:
        print(f"{MODE}: base has no {MANIFEST}; using the pinned floor only")
        return {}
    try:
        return json.loads(text)
    except ValueError:
        fail("base manifest is not valid JSON")


def participants(commits, allow, author):
    out = {author} if author else set()
    for c in commits:
        linked = False
        for top in ("author", "committer"):
            login = (c.get(top) or {}).get("login")
            if login:
                out.add(login)
                linked = True
        if linked:
            continue
        inner = c.get("commit") or {}
        for key in ("author", "committer"):
            node = inner.get(key) or {}
            name, email = (node.get("name") or "").lower(), (node.get("email") or "").lower()
            for h in allow:
                if h.lower() == name or h.lower() in email:
                    out.add(h)
    return out


def approval_qualifies(review, head, allow, excluded, reviewer_bots):
    login = (review.get("user") or {}).get("login")
    uid = (review.get("user") or {}).get("id")
    if not login or review.get("state") != "APPROVED":
        return False
    if review.get("commit_id") != head:
        return False
    if login not in allow or login in excluded:
        return False
    if not is_agent(login=login):
        return True
    if is_reviewer_app(login, uid, reviewer_bots):
        ok, reason = reviewer_app_body_ok(review.get("body") or "", head)
        if not ok:
            print(f"{MODE}: rejecting reviewer App approval from {login}: {reason}")
            return False
        return True
    return False


def main():
    if MODE not in ("agent-denied-paths", "agent-review-of-record"):
        fail(f"unknown MODE {MODE!r}")
    if not TOKEN.strip():
        fail("GH_TOKEN is empty; cannot call the GitHub API")
    if REPO == SELF_REPO:
        print(f"{MODE}: running in the policy repo itself; nothing to gate.")
        return
    if REPO not in TARGET_REPOS:
        fail(f"{REPO} is not onboarded in this pinned gate (TARGET_REPOS); add it and re-pin")
    reviewer_bots = REVIEWER_APP_BOTS
    number = os.environ.get("PR", "")
    if not number.isdigit():
        fail("no pull request number in the event (only pull_request events are supported)")
    pr = call(f"/repos/{REPO}/pulls/{number}")
    event_head = os.environ.get("EVENT_HEAD_SHA", "")
    head, base_sha = pr["head"]["sha"], pr["base"]["sha"]
    if event_head and event_head != head:
        fail(f"stale run: event head {event_head[:12]} != live head {head[:12]}; the newer push has its own run")
    head_ref = pr["head"]["ref"]
    base_ref = pr["base"]["ref"]
    author = (pr.get("user") or {}).get("login") or ""
    author_type = (pr.get("user") or {}).get("type") or ""
    author_id = (pr.get("user") or {}).get("id")
    manifest = manifest_at(base_sha)
    humans = set((manifest.get("operators") or {}).get("members_expected") or [])
    cfg = base_text(ENGINE_CONFIG, base_sha)
    ai_rev = ai_reviewers_from_cfg(cfg)
    reported_commits = int(pr.get("commits") or 0)
    if reported_commits >= MAX_COMMITS:
        fail(f"PR has {reported_commits} commits (API cap {MAX_COMMITS}); cannot see them all")
    commits = paginate(f"/repos/{REPO}/pulls/{number}/commits", MAX_COMMITS)
    if len(commits) != reported_commits:
        fail(f"commit count mismatch (PR says {reported_commits}, listed {len(commits)})")
    if agent_identity_in_pr(author, author_type, author_id, commits):
        if base_ref != DEFAULT_BASE_REF:
            fail("agent PRs must target main")
    applies, why = gate_applies(head_ref, author, author_type, author_id, commits, humans, ai_rev, reviewer_bots)
    if not applies:
        print(f"{MODE}: not gated ({why[0]}); human merge authority applies.")
        return
    print(f"{MODE}: gated because: {'; '.join(why[:5])}")

    if MODE == "agent-denied-paths":
        changed_n = int(pr.get("changed_files") or 0)
        if changed_n > MAX_FILES:
            fail(f"PR changes {changed_n} files (> {MAX_FILES}); cannot list them all")
        files = paginate(f"/repos/{REPO}/pulls/{number}/files", MAX_FILES)
        if len(files) != changed_n:
            fail(f"file count mismatch (PR says {changed_n}, listed {len(files)})")
        paths = set()
        for f in files:
            paths.add(f["filename"])
            if f.get("previous_filename"):
                paths.add(f["previous_filename"])  # moving a denied file out is a hit
        if not paths:
            fail("empty diff against base; refusing to pass an empty check (GOV-0012)")
        dp = manifest.get("denied_paths") or {}
        denied = list(FLOOR_DENIED) + list(dp.get("arch_0048_baseline") or [])
        if INCLUDE_PROPOSED:
            denied += list(dp.get("proposed_additions") or [])

        def hit(p, e):
            return p.startswith(e) if e.endswith("/") else (p == e or p.startswith(e))

        bad = sorted({p for p in paths for e in denied if hit(p, e)})
        for p in bad:
            print(f"::error file={p}::denied path for agent PRs (ARCH-0048 decision 5)")
        if bad:
            fail(f"{len(bad)} denied path(s)")
        print(f"{MODE}: {len(paths)} path(s), none denied.")
        return

    # agent-review-of-record: ai_reviewers may approve; they never qualify for human skip.
    allow = set(humans)
    if cfg:
        for key in ("human", "ai_reviewers"):
            parsed = parse_flow_list_line(cfg, key)
            if parsed not in (None, False):
                allow |= parsed
    if not allow:
        fail("no reviewer allowlist at base (manifest operators.members_expected)")
    excluded = participants(commits, allow, author)
    reviews = paginate(f"/repos/{REPO}/pulls/{number}/reviews", 10000)
    latest = {}
    for r in reviews:
        login = (r.get("user") or {}).get("login")
        if login and r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[login] = r
    blocked = sorted(l for l, r in latest.items() if r["state"] == "CHANGES_REQUESTED")
    if blocked:
        fail(f"open CHANGES_REQUESTED from {blocked}")
    ok = sorted(l for l, r in latest.items()
                if approval_qualifies(r, head, allow, excluded, reviewer_bots))
    if not ok:
        fail(f"no allowlisted, independent APPROVE at head {head[:12]}; a new push needs a new review, then re-run this check")
    print(f"{MODE}: approved at {head[:12]} by {ok}")


main()
