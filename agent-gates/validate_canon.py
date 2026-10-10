#!/usr/bin/env python3
"""Validate rulesets/canon.json bodies against GitHub's published OpenAPI schema.

Usage: python3 agent-gates/validate_canon.py [path/to/api.github.com.json]
Without an argument it downloads the description from
https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json
Needs: pip install jsonschema. TODO-PIN placeholders are replaced by a dummy SHA.
"""
import json, re, subprocess, sys, urllib.request
from pathlib import Path
import jsonschema

URL = "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json"
CANON_PATH = Path(__file__).resolve().parents[1] / "rulesets" / "canon.json"

LIVE_REF_INCLUDE = (
    "~DEFAULT_BRANCH",
    "refs/heads/main",
    "refs/heads/release/**",
    "refs/heads/prod/**",
)


def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [strip(x) for x in o]
    return o


def agent_gates_pin_ancestor_errors(canon, repo_root=None):
    """Require a published pin, including in detached Actions checkouts."""
    pin = ((canon.get("pins") or {}).get("agent_gates_sha") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", pin):
        return [f"pins.agent_gates_sha must be a 40-char lowercase hex commit (got {pin[:20]!r}...)"]
    root = Path(repo_root) if repo_root else CANON_PATH.parent.parent
    r = subprocess.run(
        ["git", "merge-base", "--is-ancestor", pin, "refs/remotes/origin/main"],
        cwd=root,
        capture_output=True,
    )
    if r.returncode == 1:
        return [f"pins.agent_gates_sha {pin} is not an ancestor of origin/main"]
    if r.returncode != 0:
        return ["cannot verify pins.agent_gates_sha ancestry; fetch origin/main with complete history"]
    return []


def agent_gates_live_ref_errors(canon):
    errs = []
    for rs in canon.get("organization_rulesets") or []:
        if not isinstance(rs, dict) or rs.get("name") != "canon-agent-gates":
            continue
        if rs.get("_bootstrap_ref_include"):
            errs.append("canon-agent-gates: _bootstrap_ref_include must be absent after rollout")
        if rs.get("_post_rollout_ref_include"):
            errs.append("canon-agent-gates: _post_rollout_ref_include must be absent; use conditions.ref_name.include")
        inc = (rs.get("conditions") or {}).get("ref_name", {}).get("include") or []
        if list(inc) != list(LIVE_REF_INCLUDE):
            errs.append(
                "canon-agent-gates: conditions.ref_name.include must match live post-rollout ref_include"
            )
    return errs


def main():
    api = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else json.load(
        urllib.request.urlopen(URL, timeout=120))
    canon = json.loads(CANON_PATH.read_text())
    ref_errs = agent_gates_live_ref_errors(canon)
    for msg in ref_errs:
        print(f"BAD live ref include {msg}")
    pin_errs = agent_gates_pin_ancestor_errors(canon)
    for msg in pin_errs:
        print(f"BAD agent_gates pin {msg}")
    bad = len(ref_errs) + len(pin_errs)
    for path, items in (("/orgs/{org}/rulesets", canon["organization_rulesets"]),
                        ("/repos/{owner}/{repo}/rulesets", canon["repository_rulesets"])):
        sch = dict(api["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"])
        sch["components"] = api["components"]
        v = jsonschema.validators.validator_for(sch)(sch)
        for rs in items:
            body = json.loads(json.dumps(strip(rs)).replace(
                '"TODO-PIN agent_gates_sha"', '"' + "0" * 40 + '"'))
            errs = [e.message for e in v.iter_errors(body)]
            print(f"{'OK ' if not errs else 'BAD'} {path} {rs['name']} {errs[:3] if errs else ''}")
            bad += bool(errs)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
