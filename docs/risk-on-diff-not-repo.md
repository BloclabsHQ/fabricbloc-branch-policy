# Risk on the diff, not the repo

**Council-delegated founder decision:** **DECISIONS #18** (Warden; requested by MadICM; Cris assignment **2026-10-05**). **Addendum (Aether via MadICM):** semantics of **“touches”** below.

## Task assignment is the founder yes

When **Cris assigns a task**, that assignment is the **founder yes** to merge PRs **within that task’s written scope** at the time of assignment, for heads whose diff stays inside that scope. No second Cris yes is required for those merges **only while** every enforced gate at the **current head SHA** is satisfied.

**A new push that widens scope** (new paths, new risk class, or repairs outside the assignment) **requires fresh review** — the assignment does not carry forward (same class as fabricbloc **#1600** F1/F2).

**Limits:**

- Does not extend beyond the assigned task scope.
- Does not authorize admin/ruleset bypass.
- Does not replace enforced checks on the PR at head.

Where pinned **`agent-denied-paths`** requires the **AG-06** **`owner-approved`** label, **Cris applies it himself** via the **GitHub web UI** or his **non-shared** credential (shipped **`allowed_label_apps`: `[]`** after **#79** — no Cursor App / fleet tooling label path). **Operators** (including anyone acting as login **`madgeniusblink`**, fleet bots, cloud agents, or shared owner browser sessions) **must not** apply **`owner-approved`** on Cris’s behalf. Task assignment does **not** authorize an agent or operator to apply the label. The label is **head-bound** (a new push clears it).

### Task assignment never satisfies or replaces

Task assignment is **not** any of the following:

- **Review-of-record** — a green **`agent-review-of-record`** or **`fabricbloc-reviewer`** **APPROVE** at head
- The **`owner-approved`** label (Cris-only application per above)
- Clearing an open **CHANGES_REQUESTED** review at head
- Clearing an open **FAIL** fabricbloc-verdict at head
- A **named human merge** where this policy or **FC-01** requires one
- The **FC-01** funds/custody gate
- Any **Cris-only** action: prod infra, IAM, secrets, deletes, irreversible actions, **org ruleset apply**
- Approval of **changed heads** or **out-of-scope repairs** beyond the assignment

## Human merge depends on the diff

**“Touches”** means the diff **edits** the protected **files or values themselves** (not merely names or cites them):

- Production config (non-dev runtime targets, prod env files, prod feature flags)
- Mainnet addresses and live network identifiers
- Key or signer config (`DEPLOYER_KEY`, `OPERATOR_KEY`, keystores, HSM config)
- IAM (roles, policies, trust relationships, cloud identity bindings)
- Secrets (values, rotation, registry entries, GitHub/org/repo secret and variable **definitions**)
- **Deploy workflows** — any workflow (or reusable workflow entry) that: deploys to a **non-dev** environment; references a **protected** GitHub **environment**; consumes **environment secrets**; or sets **`permissions.id-token: write`** (or equivalent) for cloud OIDC/deploy roles
- Funds or custody logic (**FC-01**, **DECISIONS #15**)
- Deletes and other **irreversible** repository or infra actions
- Policy control files and pins: **`rulesets/`**, **`pins.*` / `canon.json`**, **`gate-owners.json`**, **`reviewers.json`**, **`bots.json`**, pinned **canon workflows** (`.github/workflows/agent-*.yml`, `branch-name-guard.yml`, `gate-issue-link.yml`, hygiene pins), **`agent-gates/`** executable gate code
- Branch protection and **rulesets** (org or repo) bodies and targeting
- **GitHub App** permissions, installations, and allowlists that affect merge or gate behavior
- **GitHub environments** and their **protection rules** (required reviewers, wait timers, deployment branches)
- **Cris-only gate paths** enforced by pinned **`agent-denied-paths`** (workflows, **CODEOWNERS**, org ruleset control files, engine control files outside tests, GOV ADRs, and related denied globs)

Docs or context that **only names or points to** a boundary does **not** trigger a named human merge under this policy.

| Case | Example |
|---|---|
| **Named human merge (content edit)** | Diff changes a live mainnet treasury address in `config/mainnet/contracts.json`, or sets `DEPLOYER_KEY` in a prod env file the diff modifies. |
| **Agent lane OK (reference only)** | Diff adds to **`AGENTS.md`**: “Changes to **`DEPLOYER_KEY`** or **`config/prod.yaml`** require **FC-01** / Cris before merge” — without editing those keys or that yaml file. |

A repository **risk tier alone never requires a human merge**. Plans, runbooks, and checklists must **not** add a repo-tier human gate.

**Separate from this prose:** pinned **`agent-denied-paths`** still enforces by **file path**, not by whether the edit changes a secret value. A docs or context file on a **Cris-only path** (for example a comment-only edit to **`rulesets/canon.json`**) still needs **`owner-approved`** from **Cris** (web UI / non-shared credential) or a **human GOV-0022 branch**, even when the content is purely documentary.

## Agent merge lane (Sweeper)

**Docs/context-only** diffs may merge via **Sweeper** (hygiene auto-merge) **only** in repos **outside** the carve-out below, and **only** after:

- **Cris task assignment** covers the PR scope **and** the head has not widened scope (see above)
- Where **`agent-denied-paths`** requires it: **`owner-approved`** at head from **Cris** (not operators)
- Shape / policy checks (**`guard`**, branch grammar, etc.)
- **Sentinel** review when the diff is **security-sensitive** per **DECISIONS #13** and `docs/GOV-council-delegated-founder-decisions.md` (secrets, IAM, workflows, gate logic, or changes to approval / merge / authority text — routed in **`rulesets/reviewers.json`**)
- Green required checks at head, with **no** open **FAIL** verdict or **CHANGES_REQUESTED** review at head

Then Sweeper may merge — **no** separate named human merge step **for that diff class**.

**Sweeper carve-out (never bot-merge):**

- **`BloclabsHQ/fabricbloc-branch-policy`** — **`main`** is **`policy-main-protected`**; only org-admin merge path applies. Sweeper merge here would be operator automation using that bypass (**DECISIONS #14**). **Cris merges this repo’s `main`.**
- Any repo where the PR would change **`rulesets/`**, **`canon.json` / `pins.*`**, **`gate-owners.json`**, **`reviewers.json`**, pinned org **gate workflows**, or **`agent-gates/`** code on the merge target.

## Review of record (**DECISIONS #14**)

Bot **APPROVE** is not review of record. Where a ruleset requires a native GitHub review, only the configured **`fabricbloc-reviewer`** App (**337673700**) may satisfy it — **only** at the **exact head SHA**, and **only** when **no** open **FAIL** fabricbloc-verdict and **no** open **CHANGES_REQUESTED** review apply at that head. Nothing here creates a reviewer seat, bypass, secret access, or deploy authority.

## Still Cris-only (explicit yes)

Prod infra, IAM, secrets, deletes, irreversible actions, and **org ruleset apply** remain **Cris-only**, not council-delegated.

## Related

- **AG-06:** `docs/owner-approved-agent-gates.md` (**#79** — empty **`allowed_label_apps`**)
- **FC-01:** `docs/FC-01-funds-custody-human-gate.md`
- **Council Sentinel trigger:** `docs/GOV-council-delegated-founder-decisions.md`, **`rulesets/reviewers.json`**
- **PR-D2 / high-risk:** “High-risk” means **diff** or path class, not repository tier — `docs/PR-D2-gov-0033-d1-amendment.md`
