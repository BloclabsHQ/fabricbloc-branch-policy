# gate-issue-link

Reusable org gate workflow (`.github/workflows/gate-issue-link.yml`). Canonical script: `gate_issue_link.py` (embedded via `sync_gate_issue_link.py`).

Enforcement deadline defaults to **`2026-10-07T03:00:00Z`** (embedded from `rulesets/canon.json` → `pins.issue_link_enforce_after`). Optional org/repo var **`ISSUE_LINK_ENFORCE_AFTER`** may only move that deadline **earlier**, never later. Until the effective deadline the job **warns** but exits 0.

Cross-repo **`BloclabsHQ/*`** issues require a closing keyword (`Closes` / `Fixes` / `Resolves`, optional `:`) on same-repo `#N`, `owner/repo#N`, or `https://github.com/BloclabsHQ/.../issues/N`. Private cross-repo verification uses **`HYGIENE_APP_CLIENT_ID`** + **`HYGIENE_APP_PRIVATE_KEY`** (installation token on `CROSS_REPO_GH_TOKEN`).

Exempt: `dependabot[bot]`; PRs labeled `no-issue` only when that label was applied by **`madgeniusblink`** (audited via issue timeline; `labeled` events from anyone else fail immediately).
