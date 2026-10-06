# Risk on the diff, not the repo

**Council-delegated founder decision:** **DECISIONS #18** (Warden; requested by MadICM; Cris assignment **2026-10-05**). **Addendum (Aether via MadICM):** semantics of **“touches”** below.

## Task assignment is the founder yes

When **Cris assigns a task**, that assignment is the **founder yes** to merge PRs **within that task’s scope**. No second Cris yes is required for merge.

**Limits:**

- Does not extend beyond the assigned task scope.
- Does not authorize admin/ruleset bypass.
- Does not replace enforced checks. Where **`agent-denied-paths`** requires the **AG-06** **`owner-approved`** label, the label is still required. Per **DECISIONS #16**, an operator may apply **`owner-approved`** to record Cris’s assignment; it is **head-bound** (a new push clears it).

## Human merge depends on the diff

**“Touches”** means the diff **edits** the protected **files or values themselves**: prod config, mainnet addresses, key/signer config, IAM, secrets, deploy workflows, funds/custody logic, or the Cris-only gate paths (workflows, **CODEOWNERS**, org ruleset bodies, engine control files, etc.).

Docs or context that **only names or points to** a boundary does **not** trigger a named human merge under this policy.

| Case | Example |
|---|---|
| **Named human merge (content edit)** | Diff changes a live mainnet treasury address in `config/mainnet/contracts.json`, or sets `DEPLOYER_KEY` in a prod env file the diff modifies. |
| **Agent lane OK (reference only)** | Diff adds to **`AGENTS.md`**: “Changes to **`DEPLOYER_KEY`** or **`config/prod.yaml`** require **FC-01** / Cris before merge” — without editing those keys or that yaml file. |

A repository **risk tier alone never requires a human merge**. Plans, runbooks, and checklists must **not** add a repo-tier human gate.

**Separate from this prose:** pinned **`agent-denied-paths`** still enforces by **file path**, not by whether the edit changes a secret value. A docs or context file on a **Cris-only path** (for example a comment-only edit to **`rulesets/canon.json`**) still needs **AG-06** **`owner-approved`** (or a human branch) even when the content is purely documentary.

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
