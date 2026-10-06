# PR-D rollout notes

## In scope (this PR)

- **`canon-agent-gates`:** add **fabric-wallet**, add required workflow **`gate-issue-link.yml`**, re-pin workflow SHAs together after PR-A–C merge.
- **PR-D2 merged on main (canon):** org **`pull_request`** **`required_approving_review_count: 1`** is **HELD** in **`_held_rules`**, not live (**DECISIONS #17**; founder yes Cris 2026-10-04). When applied, agent PRs would satisfy via **fabricbloc-reviewer** App; human GOV-0022 PRs via normal human APPROVE. See **`docs/PR-D2-gov-0033-d1-amendment.md`**.

Agent PR approval at head remains **`agent-review-of-record`** + **fabricbloc-reviewer** App (PR-C). Org review count 1 is **HELD** until App-APPROVE + **`owner-approved`** fix and Cris confirm.

## Composition with open #47 (`canon-wallet-green-ci`)

| Ruleset | Scope | Purpose |
|---------|--------|---------|
| **canon-agent-gates** (24445414) | `~DEFAULT_BRANCH`, `main`, `release/**`, `prod/**` | F6 agent gates + issue-link (PR-A) on onboarded repos including **fabric-wallet** |
| **canon-wallet-green-ci** (#47) | `refs/heads/dev`, `refs/heads/main` on **fabric-wallet** only | Strict repo CI contexts (`Lint`, `Test`, …) — merge gate |

No conflict: agent gates target default-branch family refs; wallet green CI adds **dev** + **main** status checks. Both can apply to fabric-wallet PRs into `dev`/`main`.

## Apply order (MadAgentPM)

1. Merge **#51** (this PR) to `main`.
2. **Re-pin** `pins.agent_gates_sha` and all `canon-agent-gates` `workflows[].sha` to the **#51 squash SHA** on `main` (must include **`fabric-wallet`** in `TARGET_REPOS` and **`gate-issue-link.yml`** at that SHA — live **`ed19bdd`** alone is insufficient for wallet). Batch with any **#59** SHA per Madgeniusblink hold note.
3. Org-owner apply ruleset **24445414** from updated canon.
4. **#47 / WALLET-GREEN-CI** applied (**24489464**); no longer blocked on this PR.

## Operational FYI (2026-10-05)

- **fabricbloc-reviewer** App is installed on: **fabricbloc**, **context**, **keyflo-session-issuer**, **fabric-wallet**, **fabricbloc-branch-policy**.
- **Allow auto-merge** is enabled on all five repos.

## Open question for Cris (merge methods)

This PR **does not** change `allowed_merge_methods` on any repo ruleset. Confirm desired merge methods per repo (**context**, **keyflo**, **fabric-wallet**, **fabricbloc-branch-policy** currently allow merge/rebase where configured) before any future ruleset edits.
