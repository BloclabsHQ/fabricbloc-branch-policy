# branch-name-guard

Canonical logic: `guard_logic.py` (embedded in `.github/workflows/branch-name-guard.yml` via `sync_embedded.py`).

Bot slugs: `rulesets/bots.json`. New grammar: `agent/<bot>/(chore|feat|fix|test)/<slug>`.

Legacy `agent/session|autonomous/...` remains during dual-accept until `pins.legacy_branch_accept_until` (set org/repo var **`LEGACY_BRANCH_ACCEPT_UNTIL`** to match). After that, legacy names are only accepted when the branch had commits before the cutoff.

Normative ADR text (human-owned): [GOV-0022 branch naming](https://github.com/BloclabsHQ/fabricbloc/blob/main/decisions/GOV-0022-branch-naming-and-provider-agnostic-enforcement.md) — **Aether** owns amendments; this repo implements the executable projection.
