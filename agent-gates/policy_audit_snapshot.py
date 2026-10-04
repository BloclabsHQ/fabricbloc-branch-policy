#!/usr/bin/env python3
"""Snapshot org/repo rulesets and App installations; compare to snapshots/*.json.

Used by .github/workflows/fabricbloc-policy-audit.yml (schedule + workflow_dispatch).
Stdlib only. Never pushes commits.
"""
import difflib, json, os, sys, urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAP_DIR = ROOT / "snapshots"
ORG = "BloclabsHQ"
REPOS = ("fabricbloc", "fabric-iac", "fabricbloc-branch-policy")
VOLATILE = frozenset({
    "updated_at", "created_at", "node_id", "last_response", "etag",
    "github_owned", "html_url", "url", "_links",
})


def fail(msg):
    print(f"::error::policy-audit: {msg}", file=sys.stderr)
    sys.exit(1)


def normalize(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in sorted(obj.items()):
            if k in VOLATILE or k.startswith("_"):
                continue
            out[k] = normalize(v)
        return out
    if isinstance(obj, list):
        normed = [normalize(x) for x in obj]
        try:
            return sorted(normed, key=lambda x: json.dumps(x, sort_keys=True))
        except TypeError:
            return sorted(normed, key=str)
    return obj


def api_get(token, path):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "fabricbloc-policy-audit",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        fail(f"GitHub API {exc.code} on {path}")


def paginate(token, path):
    out, page = [], 1
    while True:
        sep = "&" if "?" in path else "?"
        batch = api_get(token, f"{path}{sep}per_page=100&page={page}")
        if not isinstance(batch, list):
            fail(f"unexpected list shape for {path}")
        out.extend(batch)
        if len(batch) < 100:
            return out
        page += 1


def fetch_rulesets(token, scope, repo=None):
    if scope == "org":
        base = f"/orgs/{ORG}/rulesets"
    else:
        base = f"/repos/{ORG}/{repo}/rulesets"
    listed = paginate(token, base)
    detailed = []
    for rs in listed:
        rid = rs.get("id")
        if rid is None:
            continue
        detailed.append(api_get(token, f"{base}/{rid}"))
    return normalize(detailed)


def fetch_installations(token):
    listed = paginate(token, f"/orgs/{ORG}/installations")
    out = []
    for inst in listed:
        iid = inst.get("id")
        if iid is None:
            continue
        detail = api_get(token, f"/orgs/{ORG}/installations/{iid}")
        app = detail.get("app") or {}
        out.append(normalize({
            "id": detail.get("id"),
            "app_id": app.get("id"),
            "app_slug": app.get("slug"),
            "repository_selection": detail.get("repository_selection"),
            "permissions": detail.get("permissions"),
            "events": detail.get("events"),
            "single_file_paths": detail.get("single_file_paths"),
        }))
    return out


def build_snapshot(token):
    return normalize({
        "organization_rulesets": fetch_rulesets(token, "org"),
        "repository_rulesets": {
            repo: fetch_rulesets(token, "repo", repo) for repo in REPOS
        },
        "org_app_installations": fetch_installations(token),
    })


def load_committed(name):
    path = SNAP_DIR / name
    if not path.exists():
        return None
    text = path.read_text().strip()
    if not text or text.startswith("#"):
        return None
    return json.loads(text)


def diff_text(a, b, label):
    a_s = json.dumps(a, indent=2, sort_keys=True) + "\n"
    b_s = json.dumps(b, indent=2, sort_keys=True) + "\n"
    return "".join(difflib.unified_diff(
        a_s.splitlines(keepends=True), b_s.splitlines(keepends=True),
        fromfile=f"committed/{label}", tofile=f"live/{label}"))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--normalize-self-test":
        sample = {"b": 1, "updated_at": "x", "a": [{"z": 1}, {"y": 2}]}
        assert "updated_at" not in normalize(sample)
        print("normalize-self-test ok")
        return
    token = os.environ.get("POLICY_AUDIT_TOKEN", "").strip()
    if not token:
        fail("POLICY_AUDIT_TOKEN is empty")
    fresh = build_snapshot(token)
    out_path = os.environ.get("SNAPSHOT_OUT", str(SNAP_DIR / "live-snapshot.json"))
    Path(out_path).write_text(json.dumps(fresh, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out_path}")

    drift = []
    org_comm = load_committed("organization_rulesets.json")
    if org_comm is None:
        drift.append("organization_rulesets.json is missing or empty placeholder")
    elif org_comm != fresh["organization_rulesets"]:
        drift.append(diff_text(org_comm, fresh["organization_rulesets"], "organization_rulesets.json"))

    inst_comm = load_committed("org_app_installations.json")
    if inst_comm is None:
        drift.append("org_app_installations.json is missing or empty placeholder")
    elif inst_comm != fresh["org_app_installations"]:
        drift.append(diff_text(inst_comm, fresh["org_app_installations"], "org_app_installations.json"))

    for repo in REPOS:
        fname = f"repository_rulesets_{repo}.json"
        comm = load_committed(fname)
        live = fresh["repository_rulesets"][repo]
        if comm is None:
            drift.append(f"{fname} is missing or empty placeholder")
        elif comm != live:
            drift.append(diff_text(comm, live, fname))

    if drift:
        print("::error::Policy audit snapshot drift detected:")
        for block in drift:
            print(block)
        sys.exit(1)
    print("policy-audit: snapshots match live state")


if __name__ == "__main__":
    main()
