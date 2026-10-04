#!/usr/bin/env python3
"""Validate rulesets/canon.json bodies against GitHub's published OpenAPI schema.

Usage: python3 agent-gates/validate_canon.py [path/to/api.github.com.json]
Without an argument it downloads the description from
https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json
Needs: pip install jsonschema. TODO-PIN placeholders are replaced by a dummy SHA.
"""
import json, sys, urllib.request
from pathlib import Path
import jsonschema

URL = "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json"
CANON_PATH = Path(__file__).resolve().parents[1] / "rulesets" / "canon.json"


def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [strip(x) for x in o]
    return o


def bootstrap_rollout_mutex_errors(canon):
    errs = []
    for rs in canon.get("organization_rulesets") or []:
        if not isinstance(rs, dict) or rs.get("name") != "canon-agent-gates":
            continue
        bootstrap = rs.get("_bootstrap_ref_include") or []
        if not bootstrap:
            continue
        inc = (rs.get("conditions") or {}).get("ref_name", {}).get("include") or []
        for marker in ("~DEFAULT_BRANCH", "refs/heads/main"):
            if marker in inc:
                errs.append(
                    f"canon-agent-gates: _bootstrap_ref_include must be empty when "
                    f"ref_name.include contains {marker} (rollout state)")
    return errs


def main():
    api = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else json.load(
        urllib.request.urlopen(URL, timeout=120))
    canon = json.loads(CANON_PATH.read_text())
    mutex_errs = bootstrap_rollout_mutex_errors(canon)
    for msg in mutex_errs:
        print(f"BAD bootstrap/rollout mutex {msg}")
    bad = len(mutex_errs)
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
