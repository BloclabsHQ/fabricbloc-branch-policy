# PR-D2 — GOV-0033 D1 amendment (agent App approval)

**Status:** **Approved** — founder decision **#11** (Cris 2026-10-04 7:56 PM PT) stands.

## Status: HELD (2026-10-05)

The **`pull_request`** rule with **`required_approving_review_count: 1`** is **not applied live** on org ruleset **24445414** (workflows-only). In **`rulesets/canon.json`**, the rule body lives under **`canon-agent-gates`** **`_held_rules`** (stripped before apply), not in **`rules`**, so a full-body org apply matches live and does not introduce the rule.

**Why held:** Owner-only agent PRs (author **madgeniusblink**, Cris-only paths) would **deadlock** if org count 1 were enforced: **AG-06** **`owner-approved`** clears **`agent-denied-paths`** and **`agent-review-of-record`**, but the author cannot self-approve, and **`reviewer-app-auto-approve`** refuses Cris-only diffs — no native **APPROVE** counts toward the org review requirement.

**Re-enable when:** (a) **fabricbloc-reviewer** App submits **APPROVE** when a valid **AG-06** **`owner-approved`** label is present at head, and (b) **Cris** confirms. See **DECISIONS #17** and **`docs/owner-approved-agent-gates.md`**.

## Cris approval (record)

- **Decision:** Approved proposal item **5** — agent reviewers approve through the **fabricbloc-reviewer** GitHub App so only high-risk PRs reach Cris.
- **When:** **2026-10-04, 7:56 PM PT**
- **Relay:** MadAgentPM

This amends **GOV-0033 D1** from “0 required approving reviews on governed merge paths” to “**1** required GitHub approving review on merge bases covered by **`canon-agent-gates`**, satisfied by the reviewer App for agent PRs.”

## Canon change

**`canon-agent-gates`** (org ruleset **24445414**) gains a **`pull_request`** rule:

- **`required_approving_review_count: 1`**
- **`dismiss_stale_reviews_on_push: true`**
- No bypass actors (unchanged **F6-D2**)
- **Merge methods:** not specified here (unchanged per repo rulesets)

## GitHub limitation (agent-only review count)

Org branch rulesets cannot express “only PRs whose head is `agent/**` need N reviews.” The **`pull_request`** rule applies to every PR into the targeted **base** refs (`~DEFAULT_BRANCH`, `main`, `release/**`, `prod/**`) on onboarded repos.

**How agent PRs are enforced (defense in depth):**

| Layer | Agent PR | Human GOV-0022 PR (F6-D2 / F6-D3) |
|--------|----------|-------------------------------------|
| **`agent-review-of-record`** (required workflow) | Fail closed until allowlisted **APPROVE** at head (App or human) | **Skipped** — “not gated; human merge authority applies” |
| **`agent-denied-paths`** | Denied paths enforced | **Skipped** when human skip applies |
| **Org `pull_request` count 1** | Satisfied by **`fabricbloc-reviewer[bot]`** (`337673700`) after PR-C trusted verdict + App review body contract | Satisfied by **any eligible human** approving review (not agent-review-of-record, not Cris-only) |
| **Repo `main-required-ci` / peers** | **`required_approving_review_count: 0`** on repo ruleset blocks (unchanged) | Same |

**Ruleset count stays consistent with the gate:** agent PRs cannot merge on green CI alone — they need both **`agent-review-of-record`** success and a GitHub **APPROVE** that counts toward **`required_approving_review_count: 1`** (the App for routine agent work).

## fabric-wallet legacy repo review rule (#1437)

**Problem:** A **repo-level** rule on **`BloclabsHQ/fabric-wallet`** (ruleset or classic branch protection) requires **non-author** approval. That stalled agent PR **#1437** (author cannot satisfy “someone else approved” until the reviewer App exists).

**API read (2026-10-05, cloud agent):** `GET /repos/BloclabsHQ/fabric-wallet/rulesets` and branch protection returned **404 Not Found** — private repo / token not granted `contents` or `administration` on fabric-wallet. **Do not apply or delete anything from this PR.**

**Intent model (canon, until live id is captured by org owner):**

| Field | Value |
|--------|--------|
| **Superseded by** | Org **`canon-agent-gates`** (after PR-D adds **fabric-wallet** to `repository_name.include` and org apply) + this PR-D2 **`pull_request`** rule + PR-C App auto-approve |
| **Agent PR approval** | **`fabricbloc-reviewer[bot]`** user id **337673700** — non-author App review |
| **Human / solo maintainer** | **`canon-wallet-green-ci`** (PR #47) keeps **`required_approving_review_count: 0`** on its org ruleset block for `dev`/`main` CI gate — distinct from agent identity gates |

**Rollout (MadAgentPM / Cris — not this agent):**

1. Merge PR-D2 + prior stack; org-apply updated **`canon-agent-gates`** (includes fabric-wallet when PR-D is merged).
2. Confirm **#1437-class** agent PRs merge with App approval + green gates.
3. **Only then**, with **Cris yes**, remove the **fabric-wallet repo-level** non-author / duplicate review rule (record deleted ruleset id + name in `rulesets/README.md` drift table).
4. Do **not** remove the repo rule before org canon is live (would widen the gap).

**Org-owner capture command (paste into PR / drift table before apply):**

```bash
gh api repos/BloclabsHQ/fabric-wallet/rulesets --jq '.[] | {id, name, enforcement, source}'
gh api repos/BloclabsHQ/fabric-wallet/rulesets/<ID> --jq .
# or classic:
gh api repos/BloclabsHQ/fabric-wallet/branches/main/protection
```

## Apply order

1. Merge PR-D2 (canon only).
2. Org-owner **PUT** ruleset **24445414** from `rulesets/canon.json` (no live apply from agents).
3. After PR-D onboarded **fabric-wallet**, re-apply same org body so wallet picks up workflows + review count.
4. Execute fabric-wallet repo-rule removal per rollout above.

## Related

- PR-C: reviewer App routing + verdict auto-approve
- PR-D: fabric-wallet on `canon-agent-gates` + issue-link workflow
- PR #47: `canon-wallet-green-ci` (CI contexts, 0 review count on that ruleset)
