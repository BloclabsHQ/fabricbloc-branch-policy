#!/usr/bin/env python3
"""Validate domains/04-cursor/cloud-sessions.yaml against schemas/cloud-sessions.schema.json."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY = Path(__file__).resolve().parent / "cloud-sessions.yaml"
SCHEMA = ROOT / "schemas" / "cloud-sessions.schema.json"
BOTS_JSON = ROOT / "rulesets" / "bots.json"


def load_branch_name_policy():
    import importlib.util

    path = ROOT / "scripts" / "branch-name-policy.py"
    spec = importlib.util.spec_from_file_location("branch_name_policy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_policy() -> dict:
    return yaml.safe_load(POLICY.read_text())


def semantic_checks(data: dict) -> list[str]:
    errs: list[str] = []
    caps = data.get("caps") or {}
    max_run = int(caps.get("max_concurrent_running") or 0)
    per_bot = int(caps.get("max_concurrent_per_bot") or 0)
    if per_bot * 2 < max_run:
        errs.append(
            f"max_concurrent_running={max_run} exceeds two bots at max_concurrent_per_bot={per_bot}"
        )
    regex = ((data.get("launch") or {}).get("branch_name") or {}).get("session_branch_regex")
    if regex:
        try:
            re.compile(regex)
        except re.error as e:
            errs.append(f"session_branch_regex invalid: {e}")
        if not re.match(regex, "agent/session/chore/warden-cloud-sessions-p1"):
            errs.append("session_branch_regex rejects known good agent/session branch")
    waits = data.get("waits") or {}
    if int(waits.get("max_in_agent_wait_seconds") or 0) > 120:
        errs.append("max_in_agent_wait_seconds must be <= 120 (Loom memo)")
    branch_name = (data.get("launch") or {}).get("branch_name") or {}
    try:
        bnp = load_branch_name_policy()
        bots = bnp.load_bot_slugs(BOTS_JSON)
        expected_bot = bnp.bot_branch_regex_from_bots(bots)
        expected_agent = bnp.agent_re_combined(bots)
        if branch_name.get("bot_branch_regex") != expected_bot:
            errs.append("bot_branch_regex must match rulesets/bots.json (run branch-name sync / update yaml)")
        if branch_name.get("agent_re") != expected_agent:
            errs.append("agent_re must match rulesets/bots.json (run branch-name sync / update yaml)")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errs.append(f"bots.json / branch-name-policy: {exc}")
    return errs


def main() -> int:
    try:
        import jsonschema
    except ImportError:
        print("jsonschema required (pip install jsonschema)", file=sys.stderr)
        return 1
    data = load_policy()
    schema = json.loads(SCHEMA.read_text())
    v = jsonschema.Draft202012Validator(schema)
    schema_errs = sorted(v.iter_errors(data), key=lambda e: e.path)
    for e in schema_errs:
        print(f"schema: {e.message} at {list(e.path)}")
    sem = semantic_checks(data)
    for m in sem:
        print(f"semantic: {m}")
    bad = bool(schema_errs or sem)
    if not bad:
        print(f"OK {POLICY.relative_to(ROOT)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
