#!/usr/bin/env python3
"""Canonical GOV-0022 branch naming (BR-01 / BR-04). Source for guard, drift, and harness."""
import json
import re
from pathlib import Path

# BR-01: normative ADR — https://github.com/BloclabsHQ/fabricbloc/blob/main/decisions/GOV-0022-branch-naming-and-provider-agnostic-enforcement.md

AGENT_TYPES = (
    "feat",
    "fix",
    "chore",
    "docs",
    "refactor",
    "test",
    "ci",
    "perf",
    "revert",
    "build",
    "style",
)
SLUG = r"[a-z0-9]+(-[a-z0-9]+)+"
TYPES_ALT = "|".join(AGENT_TYPES)
RESERVED_BOT_SLUGS = frozenset(
    {"session", "autonomous", "cursor", "codex", "claude", "qwen"}
)
BLOCKED_PROVIDER_PREFIXES = re.compile(r"^(codex|claude|qwen|cursor)/")

LEGACY_AGENT_RE = re.compile(
    rf"^agent/(session|autonomous)/({TYPES_ALT})/{SLUG}$"
)


def load_bot_slugs(bots_json_path=None):
    path = Path(bots_json_path) if bots_json_path else Path(__file__).resolve().parents[1] / "rulesets" / "bots.json"
    data = json.loads(path.read_text())
    bots = []
    for b in data.get("bots") or []:
        if not isinstance(b, str) or not re.fullmatch(r"[a-z0-9-]+", b):
            raise ValueError(f"invalid bot slug {b!r}")
        low = b.lower()
        if low in RESERVED_BOT_SLUGS:
            raise ValueError(f"bot slug {b!r} is reserved (session/autonomous/provider)")
        bots.append(low)
    if not bots:
        raise ValueError("bots.json has no bots")
    return bots


def bot_agent_re(bots):
    alt = "|".join(re.escape(b) for b in bots)
    return re.compile(rf"^agent/({alt})/({TYPES_ALT})/{SLUG}$")


def bot_branch_regex_from_bots(bots):
    alt = "|".join(re.escape(b) for b in bots)
    return rf"^agent/({alt})/({TYPES_ALT})/{SLUG}$"


def session_branch_regex():
    return LEGACY_AGENT_RE.pattern


def _strip_regex_anchors(pattern):
    if pattern.startswith("^") and pattern.endswith("$"):
        return pattern[1:-1]
    return pattern


def agent_re_combined(bots=None):
    """Harness/engine: accept legacy session/autonomous or registered bot grammar."""
    bots = bots or load_bot_slugs()
    legacy = _strip_regex_anchors(LEGACY_AGENT_RE.pattern)
    bot = _strip_regex_anchors(bot_branch_regex_from_bots(bots))
    return f"^({legacy}|{bot})$"


def agent_re_for_engine_manifest(bots=None):
    """Alias for combined agent branch regex (legacy + bot)."""
    return agent_re_combined(bots)


WORKFLOW_LITERALS = (
    "branch-name-guard.yml",
    "agent-denied-paths.yml",
    "agent-review-of-record.yml",
    "gate-issue-link.yml",
    "hygiene-auto-merge.yml",
    "hygiene-branch-prune.yml",
)
