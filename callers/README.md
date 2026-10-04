# Thin caller templates (Team-plan fallback)

Use only if the org **does not** offer “Require workflows to pass before merging” on GitHub Team (see `central-policy-tools.md`). Do **not** apply rulesets from this repo via API; Cris upserts JSON manually.

Pin every `uses:` line to a **full 40-char SHA** of `fabricbloc-branch-policy` (replace `POLICY_SHA` below).

## Required status check names (Actions app 15368)

When using callers instead of org required-workflows, add these **plus** the two gate job names to branch protection / ruleset contexts:

| Context | Source |
|---|---|
| `agent-denied-paths` | Caller job (must match workflow job id) |
| `agent-review-of-record` | Caller job |
| `canon-check` | fabricbloc in-repo CI |
| `agent-entry-smoke` | fabricbloc in-repo CI |
| `github-check` | fabricbloc in-repo CI |
| `catalog-code-guard` | fabricbloc in-repo CI |
| `env-op-pattern-check` | fabricbloc in-repo CI |
| `platform-event-publisher-guard` | fabricbloc in-repo CI |
| `guard / guard` | branch-name-guard caller (drop after F6-D6 org pin) |
| `team-canon-check` | fabricbloc in-repo CI |
| `architecture-publication-check` | fabricbloc in-repo CI |

After `canon-branch-name-guard-pinned` is live, remove `guard / guard` (9 contexts + 2 gates = 11 checks, or 9 + org workflows if Team supports required-workflows).
