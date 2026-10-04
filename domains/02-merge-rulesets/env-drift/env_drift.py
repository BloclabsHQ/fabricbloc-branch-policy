#!/usr/bin/env python3
"""Deployment-environment drift check for BloclabsHQ/fabricbloc (ROLLOUT-ADDENDUM R4).

Flags:
  * any environment in the repo whose can_admins_bypass is true
    (agents act as an org-admin identity, so bypass = agents can deploy
    agent-ops from any ref and read AGENT_OPS_OP_TOKEN);
  * an environment whose API payload does not report can_admins_bypass at all
    (unverified: the UI has no checkbox for it, so the API is the only witness);
  * agent-ops deployment branch policies that are anything other than exactly
    one rule: name "main", type "branch", under custom_branch_policies=true /
    protected_branches=false;
  * agent-ops required reviewers without prevent_self_review (R4 "Add").

Pure functions over the GitHub REST JSON:
  GET /repos/{repo}/environments
  GET /repos/{repo}/environments/{name}/deployment-branch-policies
Fetching is injected (same Fetch signature as drift_check.py), so the tests run
on fixtures with no network.

Contract (same as drift_check.py): silent + exit 0 when clean; one JSON
document on stdout + exit 1 on drift; exit 2 on usage/config error. Never reads
environment secrets or variables: only environment metadata endpoints.

Offline use (JSON saved with `gh api`):
  python3 domains/02-merge-rulesets/env-drift/env_drift.py \\
      --environments-json envs.json \\
      --branch-policies agent-ops=agent-ops-branch-policies.json
Live use (short-lived fabricbloc-policy-audit installation token):
  POLICY_AUDIT_INSTALLATION_TOKEN=... python3 domains/02-merge-rulesets/env-drift/env_drift.py --live
Scheduled: `.github/workflows/policy-env-drift.yml` (MR-11).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
GITHUB_API = os.environ.get("GITHUB_API_URL", "https://api.github.com")

# Default policy; manifest.json "environments" overrides it when present.
DEFAULT_POLICY: dict[str, Any] = {
    "repo": "BloclabsHQ/fabricbloc",
    "can_admins_bypass_must_be": False,
    "exact_branch_policies": {
        "agent-ops": {
            "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
            "branch_policies": [{"name": "main", "type": "branch"}],
        }
    },
    "prevent_self_review_when_reviewers": ["agent-ops"],
}

Finding = dict[str, str]
Fetch = Callable[[str, dict[str, str]], Any]


def finding(check: str, detail: str, severity: str = "drift") -> Finding:
    return {"check": check, "severity": severity, "detail": detail}


def policy_from_manifest(manifest: dict[str, Any] | None) -> dict[str, Any]:
    pol = dict(DEFAULT_POLICY)
    if manifest and isinstance(manifest.get("environments"), dict):
        pol.update({k: v for k, v in manifest["environments"].items() if not k.startswith("_")})
    return pol


# ─── pure checks ────────────────────────────────────────────────────────────

def bypass_findings(environments: list[dict[str, Any]], policy: dict[str, Any]) -> list[Finding]:
    """Every environment: can_admins_bypass must equal the policy value (false)."""
    out: list[Finding] = []
    want = policy["can_admins_bypass_must_be"]
    for env in sorted(environments, key=lambda e: str(e.get("name"))):
        name = env.get("name", "?")
        if "can_admins_bypass" not in env:
            out.append(finding("environments", f"{name}: API did not report can_admins_bypass (cannot verify)", "unverified"))
            continue
        got = env["can_admins_bypass"]
        if got is not want:
            out.append(finding("environments", f"{name}: can_admins_bypass = {json.dumps(got)}, expected {json.dumps(want)} (admin identities, including agents, can bypass its protection rules)"))
    return out


def normalize_branch_policies(payload: Any) -> list[dict[str, str]]:
    items = payload.get("branch_policies", []) if isinstance(payload, dict) else (payload or [])
    return sorted(
        ({"name": str(p.get("name")), "type": str(p.get("type") or "branch")} for p in items),
        key=lambda p: (p["type"], p["name"]),
    )


def branch_policy_findings(environments: list[dict[str, Any]], branch_policies: dict[str, Any], policy: dict[str, Any]) -> list[Finding]:
    """Environments listed in exact_branch_policies must match exactly."""
    out: list[Finding] = []
    by_name = {e.get("name"): e for e in environments}
    for name, want in sorted(policy["exact_branch_policies"].items()):
        env = by_name.get(name)
        if env is None:
            out.append(finding("environments", f"{name}: environment not found (expected it to exist with a main-only deployment branch policy)"))
            continue
        dbp = env.get("deployment_branch_policy")
        want_dbp = want["deployment_branch_policy"]
        if dbp is None:
            out.append(finding("environments", f"{name}: deployment_branch_policy is null (any branch or tag can deploy); expected {json.dumps(want_dbp, sort_keys=True)}"))
            continue
        got_dbp = {"protected_branches": dbp.get("protected_branches"), "custom_branch_policies": dbp.get("custom_branch_policies")}
        if got_dbp != want_dbp:
            out.append(finding("environments", f"{name}: deployment_branch_policy = {json.dumps(got_dbp, sort_keys=True)}, expected {json.dumps(want_dbp, sort_keys=True)}"))
        if not want_dbp.get("custom_branch_policies"):
            continue
        if name not in branch_policies:
            out.append(finding("environments", f"{name}: deployment branch policies not fetched (cannot verify)", "unverified"))
            continue
        payload = branch_policies[name]
        got = normalize_branch_policies(payload)
        exp = normalize_branch_policies({"branch_policies": want["branch_policies"]})
        if isinstance(payload, dict) and "total_count" in payload and payload["total_count"] != len(got):
            out.append(finding("environments", f"{name}: branch policy total_count {payload['total_count']} != {len(got)} listed (incomplete page?)", "unverified"))
        if got != exp:
            missing = [p for p in exp if p not in got]
            extra = [p for p in got if p not in exp]
            out.append(finding("environments", f"{name}: deployment branch policies must be exactly {json.dumps(exp)}; missing {json.dumps(missing)}, extra {json.dumps(extra)}"))
    return out


def reviewer_findings(environments: list[dict[str, Any]], policy: dict[str, Any]) -> list[Finding]:
    out: list[Finding] = []
    names = set(policy.get("prevent_self_review_when_reviewers", []))
    for env in environments:
        if env.get("name") not in names:
            continue
        for rule in env.get("protection_rules") or []:
            if rule.get("type") == "required_reviewers" and rule.get("reviewers") and rule.get("prevent_self_review") is not True:
                out.append(finding("environments", f"{env['name']}: required reviewers set without prevent_self_review"))
    return out


def evaluate(environments_payload: Any, branch_policies: dict[str, Any], policy: dict[str, Any]) -> list[Finding]:
    """Pure entry point: API JSON in, findings out."""
    if not isinstance(environments_payload, dict) or not isinstance(environments_payload.get("environments"), list):
        return [finding("environments", "environments payload malformed (expected {'environments': [...]})")]
    envs = environments_payload["environments"]
    out: list[Finding] = []
    if "total_count" in environments_payload and environments_payload["total_count"] != len(envs):
        out.append(finding("environments", f"environments total_count {environments_payload['total_count']} != {len(envs)} listed (incomplete page?)", "unverified"))
    out += bypass_findings(envs, policy)
    out += branch_policy_findings(envs, branch_policies, policy)
    out += reviewer_findings(envs, policy)
    return out


# ─── live fetch (injected) ──────────────────────────────────────────────────

def gh_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def _paginate(fetch: Fetch, url: str, token: str, key: str) -> dict[str, Any]:
    items: list[Any] = []
    total = None
    page = 1
    while True:
        data = fetch(f"{url}?per_page=100&page={page}", gh_headers(token))
        batch = data.get(key, [])
        total = data.get("total_count", total)
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    out: dict[str, Any] = {key: items}
    if total is not None:
        out["total_count"] = total
    return out


def http_json(url: str, headers: dict[str, str]) -> Any:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def fetch_live(fetch: Fetch, token: str, policy: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    repo = policy["repo"]
    envs = _paginate(fetch, f"{GITHUB_API}/repos/{repo}/environments", token, "environments")
    present = {e.get("name") for e in envs["environments"]}
    bps: dict[str, Any] = {}
    for name, want in policy["exact_branch_policies"].items():
        if name in present and want["deployment_branch_policy"].get("custom_branch_policies"):
            q = urllib.parse.quote(name, safe="")
            bps[name] = _paginate(fetch, f"{GITHUB_API}/repos/{repo}/environments/{q}/deployment-branch-policies", token, "branch_policies")
    return envs, bps


def live_findings(fetch: Fetch, token: str | None, policy: dict[str, Any]) -> list[Finding]:
    if not token:
        return [finding("environments", "POLICY_AUDIT_INSTALLATION_TOKEN absent; environments not compared", "unverified")]
    try:
        envs, bps = fetch_live(fetch, token, policy)
    except urllib.error.HTTPError as exc:
        return [finding("environments", f"HTTP {exc.code} from API", "unverified" if exc.code in (401, 403, 404) else "drift")]
    except (urllib.error.URLError, TimeoutError) as exc:
        return [finding("environments", f"network error: {type(exc).__name__}", "unverified")]
    return evaluate(envs, bps, policy)


# ─── CLI ────────────────────────────────────────────────────────────────────

def report(findings: list[Finding], strict: bool) -> tuple[int, dict[str, Any] | None]:
    drift = [f for f in findings if f["severity"] != "unverified" or strict]
    if not drift:
        return 0, None
    canon = json.dumps(sorted(drift, key=lambda d: json.dumps(d, sort_keys=True)), sort_keys=True, separators=(",", ":"))
    return 1, {"policy": "environments", "fingerprint": hashlib.sha256(canon.encode()).hexdigest()[:16], "findings": drift,
               "unverified_hidden": 0 if strict else sum(1 for f in findings if f["severity"] == "unverified")}


def run(argv: list[str], fetch: Fetch | None = None, env: dict[str, str] | None = None) -> tuple[int, dict[str, Any] | None]:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--manifest", type=Path, default=HERE / "manifest.json")
    p.add_argument("--environments-json", type=Path, help="saved GET /repos/{repo}/environments")
    p.add_argument("--branch-policies", action="append", default=[], metavar="ENV=FILE",
                   help="saved GET .../environments/ENV/deployment-branch-policies (repeatable)")
    p.add_argument("--live", action="store_true")
    p.add_argument("--strict-live", action="store_true", help="treat unverified findings as drift")
    args = p.parse_args(argv)
    env = dict(os.environ if env is None else env)
    try:
        manifest = json.loads(args.manifest.read_text()) if args.manifest.is_file() else None
        policy = policy_from_manifest(manifest)
        if args.live:
            token = (env.get("POLICY_AUDIT_INSTALLATION_TOKEN") or "").strip()
            if not token:
                skip_msg = (
                    "POLICY_AUDIT_INSTALLATION_TOKEN not set; live environment drift check skipped "
                    "(configure POLICY_AUDIT_APP_ID / POLICY_AUDIT_APP_PRIVATE_KEY on this repo)"
                )
                print(f"::warning::{skip_msg}")
                summary_path = env.get("GITHUB_STEP_SUMMARY", "").strip()
                if summary_path:
                    with open(summary_path, "a", encoding="utf-8") as summary:
                        summary.write("### MR-11 live env drift skipped\n\n")
                        summary.write(f"{skip_msg}\n")
                if args.strict_live:
                    return 1, None
                return 0, None
            if fetch is None:
                fetch = http_json
            findings = live_findings(fetch, token, policy)
        elif args.environments_json:
            envs = json.loads(args.environments_json.read_text())
            bps = {}
            for item in args.branch_policies:
                name, _, path = item.partition("=")
                if not name or not path:
                    raise ValueError(f"--branch-policies expects ENV=FILE, got {item!r}")
                bps[name] = json.loads(Path(path).read_text())
            findings = evaluate(envs, bps, policy)
        else:
            p.error("give --environments-json or --live")
    except (OSError, ValueError) as exc:
        print(f"env_drift: {exc}", file=sys.stderr)
        return 2, None
    return report(findings, args.strict_live)


def main() -> int:
    code, rep = run(sys.argv[1:])
    if rep is not None:
        print(json.dumps(rep, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
