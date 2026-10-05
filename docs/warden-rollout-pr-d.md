# PR-D rollout notes

## Composition with open #47 (`canon-wallet-green-ci`)

| Ruleset | Scope | Purpose |
|---------|--------|---------|
| **canon-agent-gates** (24445414) | `~DEFAULT_BRANCH`, `main`, `release/**`, `prod/**` | F6 agent gates + issue-link (PR-A) on onboarded repos including **fabric-wallet** |
| **canon-wallet-green-ci** (#47) | `refs/heads/dev`, `refs/heads/main` on **fabric-wallet** only | Strict repo CI contexts (`Lint`, `Test`, …) — merge gate |

No conflict: agent gates target default-branch family refs; wallet green CI adds **dev** + **main** status checks. Both can apply to fabric-wallet PRs into `dev`/`main`.

## Apply order (MadAgentPM)

1. Merge **PR-A → PR-B → PR-C** (or stack re-pin branch).
2. Single **re-pin** PR: set `pins.agent_gates_sha` and all `canon-agent-gates` `workflows[].sha` to that squash SHA.
3. Apply org ruleset **24445414** + set `ISSUE_LINK_ENFORCE_AFTER`, `LEGACY_BRANCH_ACCEPT_UNTIL`, reviewer App secrets.
4. Merge **#47** separately when ready; apply `WALLET-GREEN-CI` org ruleset.

Until step 2, PR-D canon pins remain at **`1ddbd5b`** (pre-stack); do not apply gate-issue-link SHA until the file exists on `main`.
