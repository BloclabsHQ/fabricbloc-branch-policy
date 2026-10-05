# gate-issue-link

Reusable org gate workflow (`.github/workflows/gate-issue-link.yml`). Canonical script: `gate_issue_link.py` (embedded via `sync_gate_issue_link.py`).

Before org apply, set org/repo variable **`ISSUE_LINK_ENFORCE_AFTER`** to match `rulesets/canon.json` → `pins.issue_link_enforce_after`. Until that instant the job **warns** but exits 0.

Exempt: `dependabot[bot]`; PRs labeled `no-issue` only when that label was applied by **`madgeniusblink`** (audited via issue timeline; `labeled` events from anyone else fail immediately).
