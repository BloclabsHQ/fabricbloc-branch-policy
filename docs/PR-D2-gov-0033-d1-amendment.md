# PR-D2 — needs Cris yes: GOV-0033 D1 amendment

**Status:** NOT APPROVED — do not apply.

## Proposal

Add org- or repo-level **`required_approving_review_count: 1`** for agent PR merge paths, satisfied by **fabricbloc-reviewer** App auto-approve (PR-C), so GitHub auto-merge can complete.

## Why separated from PR-D

- **GOV-0033 D1** currently requires **0** required human approvals on the governed merge paths.
- Setting **`required_approving_review_count: 1`** on **`canon-agent-gates`** (or repo rulesets) would also affect **human GOV-0022 PRs** unless GitHub adds scoped review rules we do not have in canon today.

PR-D intentionally keeps approval enforcement in **`agent-review-of-record`** + App logic only.

## If Cris approves

- Open **PR-D2** with explicit GOV-0033 D1 amendment text in `DECISIONS.md`.
- Specify which ruleset(s) get the review-count rule and how human PRs stay at 0.
