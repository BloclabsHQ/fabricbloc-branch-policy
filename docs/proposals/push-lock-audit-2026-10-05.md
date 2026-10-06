# Push / update lock audit (2026-10-05)

**Source:** MadAgentPM desktop read **2026-10-05**. **Scope:** `rulesets/canon.json` only (org + declared repo rulesets). Proposal — no live apply from this document except where noted in sibling PR canon edits.

## Summary

| Ruleset | ID (live) | Rule | Blocks | Recommendation |
|---|---|---|---|---|
| `canon-push-protected-paths` | **24485995** (fabricbloc, push) | `file_path_restriction` (14 paths) | **Direct pushes** to control paths on any branch for non–org-admin pushers; does **not** block PR merge to `main` when the diff is allowed | **Keep** (canon updated: engine glob removed to match Cris save) |
| `policy-main-protected` | **24445012** (branch-policy, branch) | `update` (restrict updates) | **PR merges** to `main` for non-bypass actors even when checks are green | **Remove** restrict-updates (canon PR drops `update`; pending Cris Save) |
| `canon-deploy-branches-human-only` | *(canon only; live id not captured here)* | `creation` + `update` on `release/**`, `prod/**` | Direct branch create/update on deploy refs | **Keep** — deploy refs stay human-only; PR merges into `main`/`dev` unaffected |

## `file_path_restriction` (push rulesets)

Only **`canon-push-protected-paths`** in canon. Push rulesets evaluate on **push**, not on merge-button merge of a PR (merge creates a merge commit via GitHub, not a non-admin push to protected paths in the same way agents use for follow-up commits). They **do** block agent **follow-up pushes** on a PR branch when the commit touches listed paths — intentional for workflows/CODEOWNERS; **engine** was removed from the list so engine-only agent iterations can push after review.

**Recommendation:** Keep path lock; keep engine **off** push list (merge gate only).

## `update` (restrict updates)

| Location | Recommendation | Reason |
|---|---|---|
| `policy-main-protected` | **Remove** (canon change + Cris save) | Blocks Sweeper / bot UI merge on green agent PRs to policy `main` |
| `canon-deploy-branches-human-only` | **Keep** | Protects `release/**` and `prod/**` ref updates, not routine default-branch PR flow |

## Not in canon (FYI)

- **Classic branch protection** on fabricbloc `main` (**79877078**) — modeled in `_live_drift_notes`; PR required, 0 approvals; does not duplicate push path locks.
- **Org rulesets** in canon (`canon-agent-gates`, `canon-wallet-green-ci`, draft branch-name guard) — no `update` or `file_path_restriction` rules.

## Follow-ups (proposal only)

- Narrow **`canon-push-protected-paths`** script globs per `docs/owner-approved-agent-gates.md` (AG-06 follow-up; Cris GATE before org apply).
- Capture live ruleset id for **`canon-deploy-branches-human-only`** on next org-owner audit.
