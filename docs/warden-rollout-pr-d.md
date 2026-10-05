# PR-D rollout notes

## In scope (this PR)

- **`canon-agent-gates`:** add **fabric-wallet**, add required workflow **`gate-issue-link.yml`**, re-pin workflow SHAs together after PR-A–C merge.
- **Not in scope:** org `pull_request` **`required_approving_review_count: 1`** — contradicts **GOV-0033 D1 (0)** and is **not approved**. See **`docs/PR-D2-gov-0033-d1-amendment.md`** (needs Cris yes).

Agent PR approval at head remains **`agent-review-of-record`** + **fabricbloc-reviewer** App (PR-C), not a ruleset review-count rule (avoids binding human GOV-0022 PRs).

## Composition with open #47 (`canon-wallet-green-ci`)

| Ruleset | Scope | Purpose |
|---------|--------|---------|
| **canon-agent-gates** (24445414) | `~DEFAULT_BRANCH`, `main`, `release/**`, `prod/**` | F6 agent gates + issue-link (PR-A) on onboarded repos including **fabric-wallet** |
| **canon-wallet-green-ci** (#47) | `refs/heads/dev`, `refs/heads/main` on **fabric-wallet** only | Strict repo CI contexts (`Lint`, `Test`, …) — merge gate |

No conflict: agent gates target default-branch family refs; wallet green CI adds **dev** + **main** status checks. Both can apply to fabric-wallet PRs into `dev`/`main`.

## Apply order (MadAgentPM)

1. Merge **PR-A → PR-B → PR-C** (or stack re-pin branch).
2. Single **re-pin** PR: set `pins.agent_gates_sha` and all `canon-agent-gates` `workflows[].sha` to that squash SHA.
3. Apply org ruleset **24445414** + set `ISSUE_LINK_ENFORCE_AFTER`, **`LEGACY_BRANCH_PR_CREATED_BEFORE`**, reviewer App secrets.
4. Merge **#47** separately when ready; apply `WALLET-GREEN-CI` org ruleset.

Until step 2, PR-D canon pins remain at **`1ddbd5b`** (pre-stack); do not apply gate-issue-link SHA until the file exists on `main`.

## Operational FYI (2026-10-05)

- **fabricbloc-reviewer** App is installed on: **fabricbloc**, **context**, **keyflo-session-issuer**, **fabric-wallet**, **fabricbloc-branch-policy**.
- **Allow auto-merge** is enabled on all five repos.

## Open question for Cris (merge methods)

This PR **does not** change `allowed_merge_methods` on any repo ruleset. Confirm desired merge methods per repo (**context**, **keyflo**, **fabric-wallet**, **fabricbloc-branch-policy** currently allow merge/rebase where configured) before any future ruleset edits.
