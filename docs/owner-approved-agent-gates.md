# Owner-approved agent gate override (AG-06)

## Problem

Agent PRs that touch **Cris-only** denied paths (workflows, `rulesets/`, engine code outside tests, GOV ADRs, etc.) fail **`agent-denied-paths`** by design. **`agent-review-of-record`** may stay red when the **fabricbloc-reviewer** App cannot auto-approve (routing, verdicts, or Cris-only diffs). Org ruleset **`canon-agent-gates`** (id **24445414**) has **no bypass actors**, so every required check must go green on the PR — no admin bypass merge.

## Mechanism

1. Config: **`rulesets/gate-owners.json`** at **`pins.agent_gates_sha`** (never the PR head).  
   - **`gate_owners`**: `{ login, user_id }` pairs (both required).  
   - **`owner_approved_label`**: default **`owner-approved`**.

2. **Cris** (or another configured owner) applies **`owner-approved`** on the PR after reviewing the **current head**.

3. Both pinned gates re-run on **`labeled`** / **`unlabeled`** (and existing PR events). They pass when:
   - the label is **present** on the PR;
   - the **newest** timeline event for that label is **`labeled`** (not **`unlabeled`**);
   - the **`labeled`** event **actor** matches a **`gate_owners`** entry (login + user id);
   - the label event **`created_at`** is **≥** the current **head commit** committer timestamp (new push invalidates until re-label).

4. **Scope:** Clears **Cris-only** **`agent-denied-paths`** failures and satisfies **`agent-review-of-record`** without a GitHub **APPROVE**. Does **not** override provider-control / projection hard-fails, open **CHANGES_REQUESTED**, or Sentinel security domains — intentional owner override, not a silent weaken.

## Operator steps (fabricbloc example)

1. Confirm MadAgentPM / verdict comments as usual.  
2. Review the diff at the current head SHA.  
3. Add label **`owner-approved`**.  
4. Wait for **`agent-denied-paths`** and **`agent-review-of-record`** to re-run green.  
5. After any new push, repeat from step 2 (label must be re-applied after the new head exists).

## Re-pin after merge (GATE: Cris)

When this policy lands on **`fabricbloc-branch-policy`** `main`:

1. Human PR on this repo: set **`pins.agent_gates_sha`** to the squash merge SHA; update both **`canon-agent-gates`** `workflows[].sha` entries in **`rulesets/canon.json`** to the same SHA (workflows **`.github/workflows/agent-denied-paths.yml`** and **`agent-review-of-record.yml`** @ that commit).  
2. **Org apply:** MadGeniusBot / Cris updates live org ruleset **24445414** from **`canon.json`** — **requires Cris yes** (same as every agent-gates re-pin).  
3. Until re-pinned, fabricbloc still runs the previous gate SHA.

## Proposal: relax Q14 push lock (not applied in this PR)

**Problem:** Org repo ruleset **`canon-push-protected-paths`** (id **24485995**) blocks **pushes** to paths such as **`scripts/branch-name-policy*`** even after a human has reviewed an agent PR. That can block **follow-up pushes** on already-reviewed branches without weakening the **PR** gate layer.

**Draft change** (for a future founder PR + org apply — **do not apply silently**):

Remove or narrow these **`restricted_file_paths`** entries on **`canon-push-protected-paths`** so agent follow-up pushes to policy **scripts** are allowed while **PR-required** gates still enforce denied paths:

- `scripts/branch-name-policy*`
- `scripts/repair-decision*`
- `scripts/canon-entry-budget.py`
- `scripts/x64-toolchain-inventory.json`

Keep **workflows**, **engine**, **`.cursor`**, **CODEOWNERS**, and **`.gitmodules`** under push restriction. Optional **`canon.json`** sketch:

```json
{
  "_repository": "fabricbloc",
  "name": "canon-push-protected-paths",
  "_proposal_only": "AG-06 follow-up; org ruleset 24485995; Cris GATE before apply",
  "rules": [
    {
      "type": "file_path_restriction",
      "parameters": {
        "restricted_file_paths": [
          ".github/workflows/**/*",
          ".github/actions/**/*",
          ".github/CODEOWNERS",
          "CODEOWNERS",
          "docs/CODEOWNERS",
          ".cursor/**/*",
          ".claude/hooks/**/*",
          ".gitmodules",
          "agents/runtime/engine/**/*",
          "agents/agents.yaml",
          "scripts/github-check.sh"
        ]
      }
    }
  ]
}
```

**GATE:** Cris approval before MadGeniusBot applies any change to ruleset **24485995**.

## Decision

Recorded as **DECISIONS.md** entry **15** (Warden / council-delegated policy).
