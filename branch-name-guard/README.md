# branch-name-guard

Canonical logic: `guard_logic.py` (embedded in `.github/workflows/branch-name-guard.yml` via `sync_embedded.py`). Shared regex: `scripts/branch-name-policy.py` (BR-01 / BR-04).

## Grammars

- **Legacy (interactive):** `agent/(session|autonomous)/<type>/<scope>-<slug>` — all 11 `<type>` values; slug requires at least one hyphen segment.
- **Bot (new):** `agent/<bot>/<type>/<scope>-<slug>` — `<bot>` from `rulesets/bots.json` (never `session`, `autonomous`, or provider names).
- **Autonomous engine** stays `agent/autonomous/...` (canon ruleset / engine template / hygiene unchanged).

## Phase-in

Legacy phase-in defaults to **`2026-10-19T00:00:00Z`** (embedded from `pins.legacy_branch_pr_created_before`). Optional var **`LEGACY_BRANCH_PR_CREATED_BEFORE`** may only move that cutoff **earlier**, never later. After the effective cutoff, legacy grammar is allowed only when **pull request `created_at`** is earlier.

`rulesets/bots.json` is loaded from the org pin SHA (`POLICY_BOTS_JSON_SHA` / `pins.branch_name_guard_sha`) or `main` — **never PR head**. If absent at those refs, embedded `SYNCED_BOT_SLUGS` (from `sync_embedded.py`) is used until main carries `bots.json`.

`attributed_bot` in the run summary is a **routing hint only** — not authority (GOV-0033 D5).

Normative ADR (**BR-01**, human-owned): [GOV-0022 branch naming](https://github.com/BloclabsHQ/fabricbloc/blob/main/decisions/GOV-0022-branch-naming-and-provider-agnostic-enforcement.md) — **Aether** owns amendments.
