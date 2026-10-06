# Owner-approved agent gate override (AG-06)

## Problem

Agent PRs that touch **Cris-only** denied paths (workflows, `rulesets/`, engine code outside tests, GOV ADRs, etc.) fail **`agent-denied-paths`** by design. **`agent-review-of-record`** may stay red when the **fabricbloc-reviewer** App cannot auto-approve (routing, verdicts, or Cris-only diffs). Org ruleset **`canon-agent-gates`** (id **24445414**) has **no bypass actors**, so every required check must go green on the PR — no admin bypass merge.

## Mechanism

1. Config: **`rulesets/gate-owners.json`** at **`pins.agent_gates_sha`** (never the PR head).  
   - **`gate_owners`**: `{ login, user_id }` pairs (both required).  
   - **`owner_approved_label`**: default **`owner-approved`**.  
   - **`allowed_label_apps`**: when GitHub sets **`performed_via_github_app`** on the label event, the App id/slug must be listed or the label is **rejected**. Shipped config is **`[]`**: labels applied through the **Cursor GitHub App** (id **1210556**) or any other fleet/agent tooling **do not** count, even when the actor login is **madgeniusblink** / **42707764**. **Valid path:** Cris applies **`owner-approved`** himself via the **GitHub web UI** or his own **non-shared** credential (no `performed_via_github_app`, or only Apps explicitly allowlisted in a future Cris-gated change). **Operators must not** apply the label on Cris's behalf; if Cris approved in chat, route the label action to Cris.

2. **Cris** (or another configured owner) applies **`owner-approved`** on the PR after reviewing the **current head**.

3. Both pinned gates re-run on **`labeled`** / **`unlabeled`** (and existing PR events). **`reviewer-app-auto-approve`** (`pull_request_target`) runs on label events **only** when the label is **`owner-approved`** (other labels do not mint App reviews or post fb-routing). Gates pass when:
   - the label is **present** on the PR;
   - the **newest** timeline event for **`owner_approved_label`** is **`labeled`** (not **`unlabeled`**);
   - the **`labeled`** event **actor** is a **`User`** matching a **`gate_owners`** entry (login + user id; not `*[bot]`);
   - if **`performed_via_github_app`** is set, that App must be in **`allowed_label_apps`** (empty shipped list → reject all App-mediated labels);
   - **Staleness (server push time only):** `labeled_at` is **strictly after** the activity **`timestamp`** for the push that produced the current head on **`head_ref`**:
     1. `GET /repos/{repo}/activity?direction=desc&per_page=100&ref=refs/heads/{head_ref}` — first entry whose **`after`** equals head SHA (uses activity **`timestamp`**, not commit author/committer dates);
     2. optional bounded **`Link: rel="next"`** follow (cap **5** pages);
     3. if no matching activity entry: owner override **not satisfied** (**no check-suite fallback**).

4. **Scope:** Clears **Cris-only** **`agent-denied-paths`** failures and satisfies **`agent-review-of-record`** without a GitHub **APPROVE**. **DECISIONS #16** **carves out** decision **#14**: **`madgeniusblink`** label approval counts for ROR **including madgeniusblink-authored PRs** when applied by **Cris through an accepted (non–App-mediated) label path** above. Does **not** override provider-control / projection hard-fails, open **CHANGES_REQUESTED**, or Sentinel security domains. **PR-D2** org **`required_approving_review_count: 1`** is **held** in canon (**`_held_rules`**, not live) until the App-APPROVE + **`owner-approved`** fix — **AG-06** alone does not satisfy a live org review count if that rule were applied.

5. **Logging (audit):** when owner override evaluates the label timeline, the gate prints **`owner-approved label event audit:`** for the **newest** **`labeled`/`unlabeled`** event (sorted by **`created_at`**, not API page order): actor **login**, **id**, and App **id/slug** or **`none`** — on pass and fail.

6. **Missing config:** if **`gate-owners.json`** is absent at the pin, owner override is **not satisfied** (gates keep failing; not a workflow hard-fail).

### Future option (needs Cris)

If **chat approvals** must programmatically count as **`owner-approved`**, introduce a dedicated **approval-relay** GitHub App gated on Cris's Slack user **U083ZJDP9EC**, allowlist **only** that App's id in **`allowed_label_apps`**, and install/configure secrets under Cris control. That is a **separate** founder-gated change — not part of clearing gates via Cursor or shared fleet tokens.

### Residual risk (live gate; identity — needs Cris)

Org **`canon-agent-gates`** (**24445414**) @ policy pin **`093f61db`** is **already live** (saved **2026-10-05 ~5:55 PM PT**). This PR tightens **`allowed_label_apps`** to **`[]`** via re-pin after merge. **`[]`** blocks **Cursor App / GitHub API** labels (`performed_via_github_app` set) that any cloud agent can trigger.

It does **not** block an agent driving a **browser** already signed in as **madgeniusblink** (no App marker on the label event). Prior **`owner-approved`** uses on fabricbloc (**#1586**, **#1600**, **#1594**, **#1577**, **#1572**, **#1542**, **#1541**, **#1517**, **#1531**) followed Cris's explicit chat approval per MadAgentPM; audit logs should be used to confirm **`performed_via_github_app=none`** vs App going forward.

**Durable fix (out of scope):** identity separation — move fleet bots to a **machine user**; keep **madgeniusblink** sessions off bot/cloud-agent machines (**Cris credential / workstation policy**).

### ESC / edge cases

- **Fork PRs** or repos where **repository activity** for `refs/heads/{head_ref}` does not expose a push with **`after == head`**: owner override cannot clear gates until activity is observable (re-label after push appears in activity, or merge from a human branch). Cross-branch check-suite timestamps do **not** substitute.
- **Shared `madgeniusblink` PAT, `gh` OAuth, or browser session:** app-less labels pass the allowlist check; fleet must hold **no** owner PAT/OAuth on cloud-agent hosts and must not drive Cris browser sessions for **`owner-approved`**.

## Operator steps (fabricbloc example)

1. Confirm MadAgentPM / verdict comments as usual.  
2. Review the diff at the current head SHA.  
3. **Cris** adds label **`owner-approved`** (web UI or personal credential — not Cursor/cloud agent label APIs).  
4. Wait for **`agent-denied-paths`** and **`agent-review-of-record`** to re-run green.  
5. After any new push, repeat from step 2 (re-apply **`owner-approved`** only **after** the push so label time is strictly after server push time).

## Re-pin after merge (GATE: Cris)

**Live warning (until pin bump):** Org **`canon-agent-gates`** (**24445414**) loads **`gate-owners.json`** from policy pin **`093f61db`**, which still has **`allowed_label_apps: [1210556]`** — Cursor App labels satisfy AG-06 on fleet repos until **`pins.agent_gates_sha`** on policy **`main`** moves to **#79** **`ee4e57d`** (or later commit with **`[]`**).

**JSON config (`gate-owners.json`, `reviewers.json`):** set **`pins.agent_gates_sha`** on policy **`main`** to the commit containing **`allowed_label_apps: []`** (e.g. **#79** **`ee4e57d`**) — **`[]`** is live for fleet gates **immediately** — **no org apply**. Merging JSON without moving the pin changes nothing live.

**Embedded gate script** (audit log format, timeline sort, etc.): update **`canon-agent-gates`** `workflows[].sha` in **`rulesets/canon.json`** to the merge SHA and **org apply** ruleset **24445414** — **Cris GATE** — so required workflows run the new embedded Python.

1. Human PR: bump **`pins.agent_gates_sha`** when JSON or script changes land; keep workflow SHAs in **`canon.json`** aligned with that commit for org apply.  
2. **Org apply** only when workflow SHAs change (not for JSON-only pin bumps already on **`main`**).

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

Recorded as **DECISIONS.md** entry **16** (Warden; amended **2026-10-06** — empty **`allowed_label_apps`**, no Cursor App). **#15** = FC-01; **#17** = held PR-D2 canon.
