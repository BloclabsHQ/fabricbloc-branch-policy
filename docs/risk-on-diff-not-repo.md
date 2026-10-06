# Risk on the diff, not the repo

**Council-delegated founder decision:** **DECISIONS #18** (Warden; requested by MadICM; Cris assignment **2026-10-05**).

## Task assignment is the founder yes

When **Cris assigns a task**, that assignment is the **founder yes** to merge PRs **within that task’s scope**. No second Cris yes is required for merge.

**Limits:**

- Does not extend beyond the assigned task scope.
- Does not authorize admin/ruleset bypass.
- Does not replace enforced checks. Where **`agent-denied-paths`** requires the **AG-06** **`owner-approved`** label, the label is still required. Per **DECISIONS #16**, an operator may apply **`owner-approved`** to record Cris’s assignment; it is **head-bound** (a new push clears it).

## Human merge depends on the diff

A **named human merge** (Cris) applies only when the **diff** touches:

- Production config
- Mainnet addresses
- Keys or signers
- IAM
- Secrets
- Deploy workflows
- Funds or custody (**FC-01**, **DECISIONS #15**)
- **Cris-only** paths in pinned **`agent-denied-paths`** (org rulesets, **CODEOWNERS**, gate control files, workflows, engine, etc.)

A repository **risk tier alone never requires a human merge**. Plans, runbooks, and checklists must **not** add a repo-tier human gate.

## Agent merge lane (Sweeper)

**Docs/context-only** diffs in **any** repo merge via the agent lane after:

- Owner ACK (task assignment or **AG-06** where required)
- Shape / policy checks
- **Sentinel** review where **B1/B2** security lines change
- Green required checks

Then **Sweeper** (hygiene auto-merge) or equivalent bot merge — **no** separate human merge step.

## Review of record (**DECISIONS #14**)

Bot **APPROVE** is not review of record. Where a ruleset requires a native GitHub review, the **`fabricbloc-reviewer`** App satisfies it under existing rules. Nothing here creates a reviewer seat, bypass, secret access, or deploy authority.

## Still Cris-only (explicit yes)

Prod infra, IAM, secrets, deletes, irreversible actions, and **org ruleset apply** remain **Cris-only**, not council-delegated.

## Related

- **AG-06:** `docs/owner-approved-agent-gates.md`
- **FC-01:** `docs/FC-01-funds-custody-human-gate.md`
- **PR-D2 / high-risk:** “High-risk” means **diff** or path class, not repository tier — `docs/PR-D2-gov-0033-d1-amendment.md`
