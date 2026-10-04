# FabricBloc branch policy

This public repository owns the canonical executable branch-name guard for
[FabricBloc GOV-0022](https://github.com/BloclabsHQ/fabricbloc/blob/main/decisions/GOV-0022-branch-naming-and-provider-agnostic-enforcement.md).

Consumers call [`.github/workflows/branch-name-guard.yml`](.github/workflows/branch-name-guard.yml)
as a reusable workflow at an immutable commit SHA. The same workflow declares
the pull-request trigger required when it is selected by a GitHub ruleset. It
contains no secrets and the executable grammar is defined in that file only.

Run `bash branch-name-guard/test.sh` to execute the accepted/rejected contract
matrix against the workflow's embedded validator.

---

# F6 enforcement: gates a PR cannot rewrite

**DRAFT ONLY.** Nothing here has been pushed, applied or opened as a PR, and no GitHub setting was changed. No secret values were read.
The tree mirrors `BloclabsHQ/fabricbloc-branch-policy` (pinned workflow SHA `e8a5985`, public, repo id `1349282028`). `fabricbloc-side/` lists what `BloclabsHQ/fabricbloc` PR #1526 must change to match. `rulesets/canon.json` `pins.*` and every `workflows[].sha` match `e8a5985f5ebf7b3795716b29fb3778e9842a3e25` until the next re-pin PR.
Sources read on 2026-10-03 (all times PT): PR #1526 at its newest head `593a281` (pushed 7:54 PM PT, after the 1ab108f revision the review cited), its files, the 4 Codex inline comments, the 1 conversation comment, the 1 review, and the live branch-policy tree and commits.

## Files

| Path | What it is |
|---|---|
| `rulesets/canon.json` | Format v2. Declares every ruleset: 2 **org** rulesets (`canon-agent-gates`, optional `canon-branch-name-guard-pinned`) and 8 **repo** rulesets on fabricbloc (`main-required-ci`, `canon-branch-creation-restricted`, `canon-deploy-branches-human-only`, `canon-agent-branches`, `canon-provider-branches-blocked` Q12, `canon-autonomous-branch-creation` Q16, `canon-push-protected-paths` Q14, plus `policy-main-protected` on this repo). All 10 bodies validate against GitHub's published OpenAPI schema (`agent-gates/validate_canon.py`). |
| `rulesets/README.md` | File format and apply rules |
| `.github/workflows/agent-denied-paths.yml` | Pinned gate. Reads the changed files via `GET /pulls/{n}/files` and the denied list from the **base** commit via the contents API. No checkout, no PR code. |
| `.github/workflows/agent-review-of-record.yml` | Pinned gate. Requires an independent, allowlisted APPROVE at the exact live head. API only. |
| `agent-gates/test.py` | Contract tests against a local fake API (including K7c/K7d Cursor identity cases and ai_reviewer rules), finding (c) base-ref gate tests, canon.json assertions (no bypass on `canon-agent-gates`, Q14 workflow paths, no `~ALL`), the F6 case (agent PR edits the gate to `exit 0` → still fails), byte-identical embedded gate logic, no checkout, and required gate workflows (`agent-denied-paths`, `agent-review-of-record`, `branch-name-guard`) pinned to `runs-on: ubuntu-latest` only (no missing `runs-on`, no `uses:` jobs). |
| `agent-gates/embedded_gate.py` | Canonical gate script; `sync_embedded_gate.py` copies it into both workflow heredocs. |
| `agent-gates/validate_canon.py` | Validates `canon.json` bodies against the GitHub OpenAPI description |
| `fabricbloc-side/.github/workflows/agent-review-rerun.yml` | Optional helper for fabricbloc: re-runs the pinned review check after a review. Convenience only; it can't make the check pass. |
| `fabricbloc-side/CHANGES.md` | Required edits to PR #1526, including 2 bugs found in its newest head |
| `DECISIONS.md` | Decisions for Cris, each with a default |

## Threat model

**Actors:** Cursor cloud agents (attended `agent/session/**` work, and engine `agent/autonomous/**` work dispatched by fabricbloc-agent-ops); any other App or PAT that can push to fabricbloc. **Assets:** `main` of fabricbloc, repo and org Actions secrets, and the gates themselves. **Trusted:** org owners; main of `fabricbloc-branch-policy` *at a pinned SHA*; main of fabricbloc *as base* (already gated).

### Finding (c): retarget gap closed

**Problem:** With `canon-agent-gates` scoped only to `~DEFAULT_BRANCH`, an agent PR **retargeted** to a fresh ungated base branch dropped the pinned org workflows — merge could bypass identity and denied-path checks.

**Layer C (gate + org scope):** On every `TARGET_REPOS` repo, org gates run on `~DEFAULT_BRANCH`, `refs/heads/main`, `refs/heads/release/**`, and `refs/heads/prod/**` (see `canon-agent-gates._post_rollout_ref_include` in `rulesets/canon.json`). Agent PRs may merge only into the repository **default branch** (`github.event.repository.default_branch`, passed as `REPO_DEFAULT_BRANCH`) **or** `main` (so repos whose default is `dev`, e.g. keyflo-session-issuer, gate both `dev` and `main`; repos whose default is `main`, e.g. context, gate `main` only — `dev` stays human-only). The pinned gate fails closed when the PR carries agent identity and `base.ref` is not an allowed merge base (`agent PRs must target main`), including retargets to `release/**` or `prod/**`. **Bootstrap-only exception:** while `canon-agent-gates` targets a test ref (README apply step 4), the gate reads `canon-agent-gates._bootstrap_ref_include` from **this policy repo's** `rulesets/canon.json` at the pinned gate SHA (embedded into `embedded_gate.py` by `sync_embedded_gate.py`, never from the PR's repo or head). An agent PR base counts via an **exact**, case-sensitive match: `refs/heads/` + `base.ref` must equal a list entry (no globs or prefix matching; only `refs/heads/*` entries count). Each run that uses the allowance emits `::warning::` and a job-summary line (`BOOTSTRAP BASE ALLOWANCE ACTIVE …; remove _bootstrap_ref_include before rollout`). At rollout (step 5), clear `_bootstrap_ref_include` and widen ruleset `ref_name.include` to `_post_rollout_ref_include` (`~DEFAULT_BRANCH`, `refs/heads/main`, `refs/heads/release/**`, `refs/heads/prod/**`); `agent-gates/validate_canon.py` **fails** if bootstrap entries remain while `ref_name.include` already contains `~DEFAULT_BRANCH` or `refs/heads/main`, so the allowance cannot survive rollout by mistake. Agent identity includes: **`agent/**` head ref** (regardless of commit author); PR author or any commit author/committer matching the pinned agent list; **`Co-authored-by:`** trailers with agent emails or known agent display names; and for PRs to an **allowed merge base**, any commit whose associated pull requests (`GET /commits/{sha}/pulls`) include an **`agent/**` head** or agent PR author (covers squash merges authored as a human after agent work). A follow-up human PR to an allowed base is **not** exempt merely because squash commits show a human author.

**Layer B (`canon-branch-creation-restricted`):** Repo ruleset on fabricbloc blocks **creation** of branches outside `main`, `agent/**`, and explicit GOV-0022 paths `refs/heads/<handle>/<type>/**` for each handle in `GOV_HUMAN_HANDLES` in `embedded_gate.py` (sourced from fabricbloc manifest `operators.members_expected` / GOV-0022 — today **`madgeniusblink`** only, not `refs/heads/*/<type>/**`). `dependabot/**` is **blocked** until fabricbloc has a `dependabot.yml` and a ruling adds the exemption back. Scoped with `refs/heads/**` plus excludes (this policy file never uses `~ALL`, and excludes must never cover all branches — contract test forbids patterns such as `refs/heads/**` in `exclude`). **No standing bypass** — break-glass: an org owner sets the ruleset to **Disabled** (audit log).

**Orphan `ledger` branch:** fabricbloc already has a long-lived orphan branch named `ledger`, pushed by harvest/retention workflows (`agent-run-ledger`) and review-lane scripts. It predates `canon-branch-creation-restricted`; the ruleset only governs **creation**, so routine **updates** to the existing `ledger` ref are unaffected. There is deliberately **no** ruleset exclude for `ledger` (smaller attack surface). If `ledger` is ever deleted, Cris must temporarily set `canon-branch-creation-restricted` to **Disabled**, recreate the orphan branch, re-enable the ruleset, and accept that fabricbloc `cursor-env` drift will flag the disabled window.

**Deploy branches (`canon-deploy-branches-human-only`):** `refs/heads/release/**` and `refs/heads/prod/**` **creation** and **update** are blocked with **no standing bypass** (same break-glass: disable the ruleset).

**Break-glass (rulesets B and deploy, and org gates):** There is **no** standing bypass on `canon-agent-gates`, `canon-branch-creation-restricted`, or `canon-deploy-branches-human-only`. An org owner sets the relevant ruleset to **Disabled** (org audit log). While `canon-agent-gates` is disabled, fabricbloc `cursor-env` drift should open an issue.

**Residual risk:** Deliberate human merge of agent work outside the detection above (for example rewriting history without linked PR metadata) remains a human accountability path, mitigated by PR template and org audit.

**Branch prefix policy (fabricbloc, finding c inventory):**

| Prefix / pattern | Creation | Rationale |
|---|---|---|
| `agent/**` | Allowed (exempt from creation-restricted) | Canonical agent work; gated by org workflows on merge targets |
| `madgeniusblink/<type>/**` | Allowed | GOV-0022 human handle(s) from manifest / GOV-0022 |
| `dependabot/**` | Blocked (creation-restricted) | No `dependabot.yml` in fabricbloc yet; any actor could spoof the prefix — re-allow via ruleset exclude after Dependabot is configured |
| `cursor/**`, `codex/**`, `claude/**`, `qwen/**` | Blocked (`canon-provider-branches-blocked`, Q12) | Agents use `agent/**`, not provider-default prefixes |
| `workboard/<hash>` | Blocked (creation-restricted) | Ephemeral workboard heads from automation; not a human handle or `agent/**` — use `agent/**` or a GOV-0022 handle branch |
| `chore/index-regen-*` (legacy) | Blocked unless renamed | fabricbloc `index-regen.yml` must push `agent/autonomous/chore/index-regen-<run_id>` instead (see PR body; not edited here if workflow lives only in fabricbloc) |

**M6 step (ii) retarget stale green:** Pinned gate workflows now declare `pull_request` type **`edited`** so changing the PR base re-runs the gate (contract test `test_gate_workflows_rerun_on_pull_request_edited`). After re-pin, retargeting an agent PR from `main` to `release/**` should re-run and stay red.

**Reviewer App key:** The `fabricbloc-reviewer` GitHub App private key rotates every **180 days** (1Password); re-pin the gate SHA after any `REVIEWER_APP_BOTS` change.

| # | Attack | Status before this draft |
|---|---|---|
| T1 | **F6.** Agent PR edits `.github/workflows/agent-denied-paths.yml` / `agent-review-of-record.yml` to `exit 0`. `pull_request` runs the workflow file from the PR merge commit, so the edited file runs. Reading the policy "from base" doesn't help, because the step that reads base is in the edited file. | open |
| T2 | Agent PR *adds* any job named `agent-denied-paths`. A `required_status_checks` context is satisfied by any GitHub Actions (15368) check run with that name, so pinning the integration doesn't help. | open |
| T3 | Agent avoids the gate's scope with a non-`agent/` branch name. | partly open (see `fabricbloc-side/CHANGES.md`) |
| T4 | Agent pushes a new workflow (`on: push` or `pull_request`) to its own branch. It runs with fabricbloc's Actions secrets **before any merge gate**. | open. Not fixable by any required check. |
| T5 | The same edit-to-pass trick against the other 9 required checks (canon-check, github-check, guard…) or the scripts they run | open |
| T6 | Agent edits the source of the gates (`fabricbloc-branch-policy`) | the Cursor App should not be installed here (manifest `never_allowlist`), but nothing enforces that |
| T7 | Cursor acts with an org admin's **user** token, so every OrganizationAdmin bypass applies to it. Evidence: PR #1526 was opened by `Madgeniusblink`; its commits are authored by the `cursoragent` user. Who pushed is not visible. | unknown |

## Options compared

| | (a) Org ruleset `workflows` rule, pinned SHA | (b) Push ruleset on paths | (c) `pull_request_target` check from base |
|---|---|---|---|
| Available on Team, private repos | **Yes.** Org rulesets reached Team on 2025-06-16, and the changelog names "requiring GitHub Actions workflows" [C1][C2]. The rule exists only at org level [C3]. **No Evaluate mode on Team**: the free/Team docs list only Active and Disabled [C4], so bootstrap uses a test branch. | **Yes.** Push rulesets are for private/internal repos on Team [C4][C5]. They don't exist for public repos, so they can't protect the public branch-policy repo. | Yes (plain Actions) |
| Stops T1 / T2 | **Yes.** What runs comes from the source repo at `sha`. The PR's copy and same-named jobs don't satisfy the rule (M2 verified in F6 round 1: org-required run failed while the decoy went green). | T1 only for non-bypass pushers. T2 the same. | T1 yes, because it runs from the default branch [C6]. **T2 no:** a PR-added `pull_request` job with the same name still satisfies the context. |
| Depends on pusher identity | **No.** No bypass actors. | **Yes.** With OrganizationAdmin bypass, it does nothing if Cursor pushes with an admin's token (T7). | No |
| Stops T4 (secrets via agent-added workflow) | No | **Yes**, for non-bypass pushers | No |
| Constraints | The source must be visible to the target: a public workflow runs on any repo in the org, private only on private [C3][C7]. It must declare `pull_request`/`pull_request_target`/`merge_group`. Filters are ignored and it runs only on `opened`/`synchronize`/`reopened`, so **a review does not re-trigger it** [C3]. It blocks direct pushes to the targeted branch, so only target PR-only branches [C3]. Rulesets created while a PR is open don't run on that PR until a new push or reopen [C8]. | 200 entries, fnmatch [C4]. Applies to the whole fork network. Bypass mode is effectively always. | Gets a write token and secrets by default. Checking out or running head code is the "pwn request" class (cache poisoning, secret theft) [C6][C9]. Runs as base context. |

**Recommendation: layer both, in order. (a) first, (b) second.**
- (a) `canon-agent-gates` is the actual F6 fix. It holds whoever pushes, and it is the only option that closes T2.
- (b) `canon-push-protected-paths` (Q14) is the only control for T4 and T5. Ship it only after stage 1 proves Cursor pushes as the App (T7). Otherwise it does nothing against Cursor.
- (c) is not recommended. It fixes T1 but not T2, and it adds secret exposure. Use it only as a fallback if the org turns out not to be on Team or Enterprise.

## What each layer stops

| Layer | T1 | T2 | T3 | T4 | T5 | T6 | T7 |
|---|---|---|---|---|---|---|---|
| (a) `canon-agent-gates` (org, no bypass, pinned SHA, default-deny scope) | ✅ | ✅ | ✅ unless Cursor commits under a human's identity | ❌ | ❌ (✅ for `guard / guard` with optional `canon-branch-name-guard-pinned`) | ✅ (pin) | ✅ |
| `policy-main-protected` (branch-policy main: PR-only, admin-only update) | | | | | | ✅ | |
| (b) Q14 `canon-push-protected-paths` | ✅ for non-admin pushers | ✅ same | | ✅ same | ✅ for listed scripts | | ❌ if Cursor acts as an admin |
| Cursor App without `workflows` permission (native GitHub refusal) | ✅ for workflow files | ✅ | | ✅ | ❌ scripts | | ✅ (a user token from an App is capped by the App's permissions) |
| Q12 provider prefixes blocked | | | hygiene | | | | |
| Q16 autonomous-branch creation | | | provenance only | | | | |

Residual risk with everything applied: if Cursor writes commits under Cris's own identity on a GOV-0022 human branch, nothing can tell it apart from Cris. Today Cursor commits as `cursoragent`, which the gate detects. The other 9 required checks still run PR-head code for anything outside the Q14 list (for example `Makefile`). Moving them into pinned org workflows is the follow-up.

## Apply order (bootstrap without locking anyone out)

No step needs a bypass, and no step can block the PR that applies the next one.
0. **Read-only checks by Cris:** the plan is Team (Org → Settings → Billing and plans). Then the Cursor App permissions (section below). Then Cursor's push identity: on `https://github.com/BloclabsHQ/fabricbloc/activity?ref=agent/session/ci/cursor-env-policy`, see who pushed. Last, list existing org and repo rulesets. The branch-policy README says branch-name-guard is "selected by a GitHub ruleset", which suggests an org ruleset may already exist.
1. **fabricbloc PR #1526**: apply `fabricbloc-side/CHANGES.md`, merge it, and run its live drift check after step 6. The gate goes live on main only at step 5, and #1526 touches `.github/workflows/`, so the order matters.
2. **Repo admin**: apply `policy-main-protected` to fabricbloc-branch-policy. Cris stays able to merge via PR (OrganizationAdmin bypass in `pull_request` mode, 0 approvals). TODO-VERIFY that the merge box offers the bypass under the `update` rule.
3. **Human PR from Cris** (branch `madgeniusblink/ci/f6-agent-gates`, merged as PR #4 → squash `04a7d3a91aa7a1376ef0a5ae0cf9dcf80ca2df33`) added `.github/workflows/agent-*.yml`, `agent-gates/`, `rulesets/`, and this README. Run `python3 agent-gates/test.py`. On its own repo the gates exit 0 by design (`SELF_REPO`). **S** = that SHA; `canon.json` `pins.agent_gates_sha` and both `workflows[].sha` are pinned to **S** in PR on `agent/session/ci/pin-agent-gates-sha`.
4. **Org owner** creates branch `f6-gate-test` in fabricbloc from main. Then create `canon-agent-gates` with `conditions.ref_name.include = ["refs/heads/f6-gate-test"]` (the `_bootstrap_ref_include`), via Org → Settings → Rules → Rulesets → Import, or `gh api -X POST orgs/BloclabsHQ/rulesets --input body.json`. Nothing that targets main is affected.
5. Run the **malicious test** below against `f6-gate-test`. When it passes, change `ref_name.include` to `_post_rollout_ref_include` (`~DEFAULT_BRANCH`, `refs/heads/main`, `refs/heads/release/**`, `refs/heads/prod/**` in `rulesets/canon.json`; **Cris applies** in the org ruleset UI). Ask authors of open PRs to push or reopen [C8]. Break-glass if the gate can't start (for example, runner trouble blocks all PRs to main): an org owner sets the ruleset to Disabled, which is audit-logged.
6. Apply `main-required-ci` with **9** contexts. `agent-denied-paths` and `agent-review-of-record` are no longer status-check contexts. Remove or align classic branch protection on main.
7. Optional, D6: `canon-branch-name-guard-pinned`, then drop `guard / guard` from `main-required-ci`.
8. **Q12** at any time after confirming Cursor's branch-prefix setting. **Q14** only after the stage-1 identity test below. **Q16** only after submodule-bump moves off the PAT. **Finding (c):** apply `canon-branch-creation-restricted` and `canon-deploy-branches-human-only` on fabricbloc; widen `canon-agent-gates` ref scope and re-pin gate SHA with the `base != main` rule (stacked PR on #7).
9. Set the manifest `enforcement_boundary.required_workflow_ruleset.git_ref = S` (human PR), then run `cursor-env-drift` with `strict_live=true`. It must open no issue.

The apply workflow comes later. It lives in branch-policy and calls the API with a company App that has org `administration: write`. It doesn't push, so `policy-main-protected` and Q14 never block it. That App must not be a bypass actor anywhere. The first apply is by hand (steps 2, 4, 6), because that App doesn't exist yet.

## Verify: the malicious test PR (must fail)

All against base `f6-gate-test` (step 5). Then repeat M1 once against `main` after the switch. Record the run URLs in the delivery issue.

| # | PR | Expect |
|---|---|---|
| M1 | Head `agent/autonomous/test/f6-exit0-i0-probe`, attended Cursor. Replace fabricbloc's `.github/workflows/agent-denied-paths.yml` and `agent-review-of-record.yml` (add them if absent) with jobs of the **same names** that run `exit 0`. | The in-repo jobs go green. The ruleset's `agent-denied-paths` (source `fabricbloc-branch-policy@S`) goes **red** with `denied path … .github/workflows/agent-denied-paths.yml`. `agent-review-of-record` is red (no approval). Merge is blocked, including for an org owner. Neither `gh pr merge --admin` nor auto-merge succeeds. |
| M2 | Same, but change only `docs/` and add one workflow with a job named `agent-denied-paths: exit 0` | The ruleset's denied-paths still fails (`.github/workflows/` is in the diff). This proves the T2 spoof doesn't satisfy the rule. |
| M3 | Head `madgeniusblink/test/f6-spoof`, opened by Cris, with ≥1 commit from Cursor (`cursoragent`) touching `.github/workflows/` | Red (agent commit identity). |
| M4 | Agent head, docs-only | denied-paths green, review red. Cris approves, then re-run (or the helper re-runs it): green. Push one more commit: red again. |
| M5 | Cris's own human PR touching `.github/workflows/` | Both green ("not gated"). This is the no-lockout check. |

`python3 agent-gates/test.py` encodes the same logic offline. Review allowlist includes `ai_reviewers`; they never qualify for the human attended-skip on GOV-0022 handle branches.

**Q14 identity test (before applying Q14 to main):** apply `canon-push-protected-paths` and have an attended Cursor agent push a one-line workflow edit to a scratch `agent/session/test/q14-probe-x` branch. **Rejected** means Cursor pushes as the App: keep Q14. **Accepted** means it pushed with an admin user token: set Q14 aside (it does nothing against Cursor) and rely on (a). Raise T7 with Cursor or move work to a service account.

## Q12 / Q14 / Q16 interplay

| | Depends on | Needed for F6? | Order |
|---|---|---|---|
| **Q12** block `cursor/` `codex/` `claude/` `qwen/` | Cursor's branch-prefix setting not being `cursor/`. #1526 used `agent/session/…`, so it looks customised, but confirm in the dashboard. | **No.** Before this draft the gates' scope keyed off the branch name. The pinned gates are default-deny, so Q12 is now hygiene. | Any time |
| **Q14** push ruleset on workflow/engine/.cursor/CODEOWNERS/gate-script paths | Stage 1 proving Cursor pushes as the Cursor App, not with an admin's token. Its OrganizationAdmin bypass exempts admins. | **Now required to finish F6** (layer b). It is the only control for T4 (agent-added workflows read secrets) and T5 (other checks' scripts). It is *not* required for gate integrity: (a) holds without it. | After (a) is live and the Q14 identity test is rejected |
| **Q16** only fabricbloc-agent-ops creates `agent/autonomous/**` | submodule-bump moving off the `FABRICBLOC_ACTION_AUTOMATION` PAT, or that PAT's owner being an org admin (TODO-VERIFY) | **No.** It was a scope concern only while the gates trusted branch names. It stays a provenance control. | Last, still held |

Safe order: **(a) → main-required-ci 9 contexts → Q12 → Q14 (after the identity test) → Q16 (after the PAT migration).** Q14 and Q16 both rely on the identity question. If Cursor acts as an admin, Q14 is inert and Q16's admin bypass exempts it too. Only (a) has no bypass.

## Cursor App `workflows` permission check (Cris, GitHub settings, read-only)

1. Open `https://github.com/organizations/BloclabsHQ/settings/installations/161289381` (Org → Settings → GitHub Apps → Installed GitHub Apps → Cursor → Configure).
2. Under **Permissions**, write down the exact level for **Workflows**, **Actions**, **Administration**, **Contents**, **Pull requests**, **Checks**, **Commit statuses** and **Secrets**. Under **Repository access**, note All vs Only select (Q1 wants select: fabricbloc).
3. If a permission update request is pending, don't accept it without reading the diff.
4. How to read it:
   - Cursor's docs say the App requests "Actions and workflows" and "Administration" [C10], so expect `workflows: write` to be present.
     - If present, a Cursor token can push workflow files, and only (a) plus Q14 stop the result.
     - If absent, GitHub refuses App-token pushes touching `.github/workflows/` [C11]. That also covers user tokens minted by the App, which can't exceed the App's own permissions.
   - Vendor permissions can't be reduced per org. The manifest's `permissions_must_not_include: [workflows, administration, actions]` will then always report drift. Record it as an accepted exception, with (a) and Q14 as the compensating controls, rather than leaving a permanent drift issue.
5. While there, also confirm the Cursor App is **not** installed on `fabricbloc-branch-policy` (T6).

## Doc citations

- [C1] https://github.blog/changelog/2025-06-16-organization-rulesets-now-available-for-github-team-plans/ ("Team plan customers… requiring GitHub Actions workflows")
- [C2] https://docs.github.com/en/organizations/managing-organization-settings/creating-rulesets-for-repositories-in-your-organization ("For customers on GitHub Team or GitHub Enterprise plans…")
- [C3] https://docs.github.com/en/enterprise-cloud@latest/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-workflows-to-pass-before-merging (org-level only. Covers source visibility, supported events, filters ignored and default types only, and blocking direct pushes.) The free/Team version of this page doesn't list the rule. It points to org rulesets instead.
- [C4] https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets (push rulesets for private/internal. Enforcement statuses Active/Disabled. Restrict file paths: fnmatch, 200 entries.)
- [C5] https://github.blog/changelog/2024-09-10-push-rules-are-now-generally-available-and-updates-to-custom-properties/ ("Push rules are available on GitHub Team plans for private repositories")
- [C6] https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request_target (runs from the default branch, and `pull_request` runs from the merge commit)
- [C7] https://docs.github.com/en/enterprise-cloud@latest/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/troubleshooting-rules (source repository privacy settings)
- [C8] the same troubleshooting page: "If you create a rule while a pull request is open, the required workflow will not run automatically"
- [C9] https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target and https://securitylab.github.com/research/github-actions-preventing-pwn-requests
- [C10] https://cursor.com/docs/integrations/github (permission table)
- [C11] https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps#repository-permissions-for-workflows
- REST schema for the `workflows` rule (`repository_id`, `path`, `ref`, `sha`, `do_not_enforce_on_create`): https://docs.github.com/en/rest/orgs/rules

## Runbook: required workflows vs decoy checks

Org ruleset `canon-agent-gates` (org ruleset id **24445414**) enforces `agent-denied-paths` and `agent-review-of-record` from **this** repo at a **pinned commit SHA** (`rulesets/canon.json` → `workflows[].sha`), not from the PR branch. Onboarded target repositories are listed in `TARGET_REPOS` (`agent-gates/embedded_gate.py`) and mirrored in `canon-agent-gates` → `conditions.repository_name.include` (`fabricbloc`, `context`, `keyflo-session-issuer`). Org gate `ref_name` targets `~DEFAULT_BRANCH` and `refs/heads/main` on each (no per-repo branch lists). Agent merge bases use `REPO_DEFAULT_BRANCH` from the event plus `main`. Optional org ruleset `canon-branch-name-guard-pinned` pins the same way for `branch-name-guard` (fabricbloc only).

**Decoy checks.** A PR can add a repo-local workflow job with the same display name that exits 0. That green row is **not** the gate. The authoritative run is the one whose check details link to  
`https://github.com/BloclabsHQ/fabricbloc/actions/required_workflows/<ruleset-workflow-id>`  
(or the equivalent URL on the policy repo when debugging), **not**  
`.../actions/workflows/<workflow-file-id>`. When judging merge readiness, use the PR **mergeable** state or the checks GitHub marks **Required** — never “a green job with the right name.”

**Runner trust.** Pinned required workflows (`agent-denied-paths`, `agent-review-of-record`, and `branch-name-guard` when ruleset-pinned) must declare `runs-on: ubuntu-latest` on every job (no org self-hosted fleet, no `uses:` reusable-workflow jobs that hide runner choice). `agent-gates/test.py` fails CI if any listed workflow drifts.

**GitHub-hosted billing.** Commit `1e8d669` added a `runner` input because a cross-org caller's vars did not reach this workflow and FabricBloc billing rejected hosted runners. This PR removes that input and pins all required gates to `ubuntu-latest`. This repository is **public** (hosted minutes are free here). Private BloclabsHQ repos must still be able to start GitHub-hosted jobs when rulesets pin these workflows; org Actions billing is not readable with the automation token (`GET /orgs/BloclabsHQ/settings/billing/actions` → **403**).

**After changing any pinned gate workflow on `main`:** Cris must re-pin org ruleset **24445414** (`canon-agent-gates`) so both `workflows[].sha` and `pins.agent_gates_sha` in `rulesets/canon.json` match **this PR's squash SHA** on `main`, then apply/update the org ruleset. Until re-pinned, fabricbloc still runs the old SHA.

**Post re-pin check (hosted runners):** On branch `f6-gate-test`, open one PR and confirm each org-required workflow run shows a GitHub-hosted runner (`runner_name` like `GitHub Actions …`, labels including `ubuntu-latest`) and completes (not stuck queued). If runs stay queued, revert the pin to `04a7d3a` and investigate billing/runner policy before retrying.

**M6 probe (retarget gap, finding (c)):** After Cris re-pins org ruleset **24445414** to a gate SHA that includes the default-branch / `main` merge-base rule and widens `ref_name.include` to `~DEFAULT_BRANCH` + `refs/heads/main`:

1. **(i) Ruleset B:** Manually verify an attended agent **cannot push** a new branch such as `probe/ungated-base` (not `main`, not `agent/**`, not `<handle>/<type>/<slug>`). Expect rejection from `canon-branch-creation-restricted`.
2. **(ii) Retarget check:** Open or retarget an **agent/** PR so its base is `release/<name>` (or `prod/<name>`). Expect pinned `agent-denied-paths` / `agent-review-of-record` to run and **not** succeed (failure or missing checks before re-pin).
3. Run `agent-gates/probes/m6_retarget.sh` with `PR=<number>`. The script only reads check runs via `gh`; it **never merges**, pushes, or creates branches.

## Reviewer GitHub App (`fabricbloc-reviewer`)

The pinned gate treats every `[bot]` login as an agent for approvals, except entries in the **pinned constant** `REVIEWER_APP_BOTS` in `agent-gates/embedded_gate.py` (synced into both gate workflows). Each entry is `(login, numeric_user_id)` from `GET /users/fabricbloc-reviewer%5Bbot%5D`. Until Cris creates the App and re-pins, the set is **empty** (fail closed: no App approval can count).

An App approval counts only when:

- `state == APPROVED` and `commit_id` equals the live PR head SHA;
- the login is on the base allowlist and not excluded as a participant;
- `(login, review.user.id)` is in `REVIEWER_APP_BOTS` (login alone is not enough); and
- the review body contains the **full 40-character head SHA** and a line matching `approval-ref: (slack:<ts>|cli:<token>)`.

The App never qualifies for the `gate_applies` human skip. `is_agent()` is unchanged elsewhere.

## Apps to create

Create the App in the BloclabsHQ org settings. It must not appear on any ruleset bypass list.

### `fabricbloc-reviewer`

| Setting | Value |
|---|---|
| Webhook | **Inactive** (no webhook) |
| Repository permissions | **Pull requests:** Read and write; **Contents:** Read; **Metadata:** Read |
| Organization permissions | none |
| Where can this GitHub App be installed? | **Only on this account** |
| Installation | **fabricbloc only** — never install on `fabricbloc-branch-policy` |

**Private key (hard rule):** The reviewer App private key is **never** stored as a GitHub Actions secret — not in this repo, not in org secrets, and not in environment secrets. It lives only in **Cris's personal 1Password vault** and is used through his **local CLI** when posting reviews.

**After creation:**

1. Note the bot's numeric user id (`GET /users/fabricbloc-reviewer%5Bbot%5D`).
2. Add `("fabricbloc-reviewer[bot]", <id>)` to `REVIEWER_APP_BOTS` in `embedded_gate.py`, run `python3 agent-gates/sync_embedded_gate.py`, merge, and **re-pin** org ruleset **24445414** once to the new gate SHA.
3. Add the bot login to `ai_reviewers` in fabricbloc `agents/runtime/engine/config.yaml` via a **human PR only** — that path is denied for agent PRs (`agent-denied-paths`).
4. Run **M6** (`agent-gates/probes/m6_retarget.sh`) on an agent PR retargeted to `release/**` and record outcomes for (i) and (ii).

**Private key rotation:** Rotate the reviewer App key every **180 days**; update 1Password only (never Actions secrets). Re-pin org ruleset **24445414** after any gate constant change.

## Unverified (TODO-VERIFY)

- That BloclabsHQ is actually on Team (assumed from the task). Also that the org-ruleset UI on Team offers "Require workflows to pass". The changelog says yes, but the Team docs page for available rules doesn't list it.
- That `agent-review-rerun.yml` can find the ruleset run by name and re-run it with `GITHUB_TOKEN` (`actions: write`). The fallback is a manual "Re-run failed jobs".
- Cursor App permission levels, and who actually pushes Cursor commits (App installation vs Cris's user token).
- The bot login `fabricbloc-agent-ops[bot]`. The gate also catches any `[bot]` login or a `Bot` author type, so a wrong slug only matters for the review exclusion list.
- That fnmatch patterns `dir/**/*` match files directly under `dir/` in push rulesets (Q14 identity test covers it).
- Which files submodule-bump touches, and who owns the PAT (Q16, and whether Q14 blocks `.gitmodules` edits by it).
- Existing live org and repo rulesets and classic protection. The connector has no rulesets endpoint.
- Whether the `update` rule plus `pull_request`-mode admin bypass lets Cris merge on branch-policy without extra clicks.
