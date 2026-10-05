# Rulesets

This directory holds the declared branch-protection ruleset for each repository
class defined in
[FabricBloc GOV-0032](https://github.com/BloclabsHQ/fabricbloc/blob/main/decisions/GOV-0032-merge-and-branch-permissions.md)
(canon, infrastructure, service, tool) as one `rulesets/<class>.json` file per
class, applied to every repository in scope by a workflow using the GitHub
rulesets API — never edited by hand in the GitHub UI.

Under **GOV-0033 decision 4**, a ruleset exists only as a file here.

## Format (schema 2)

`canon.json` holds `{schema, class, organization, policy_repo, pins, organization_rulesets[], repository_rulesets[]}`.
- `organization_rulesets[]` items are bodies for `POST /orgs/BloclabsHQ/rulesets`, or `PUT …/rulesets/{id}` matched by `name`. Only org rulesets can carry the `workflows` (required workflows) rule.
- `repository_rulesets[]` items name their repo in `_repository` and are bodies for `POST /repos/BloclabsHQ/<_repository>/rulesets`.
- Keys starting with `_` are stripped before apply. An item with `_founder_decision` is skipped until that decision is recorded yes. `_apply_after` names the step in `../README.md` "Apply order".
- Every `workflows[].sha` must equal a value in `pins`. Re-pinning takes a human PR to this file plus an org-owner apply.

| Ruleset | Scope | Enforces | Bypass |
|---|---|---|---|
| `canon-agent-gates` | org → `fabricbloc`, `context`, `keyflo-session-issuer`, **fabric-wallet**; `ref_name.include`: `~DEFAULT_BRANCH`, `refs/heads/main`, `refs/heads/release/**`, `refs/heads/prod/**` (live retarget 2026-10-04 PT, ruleset **24445414**) | Required workflows `agent-denied-paths`, `agent-review-of-record`, **`gate-issue-link`** @ pin; **`pull_request`** with **1** approving review (PR-D2 — App **337673700** for agent PRs). Org apply: re-pin to post–#51 squash SHA (includes wallet in `TARGET_REPOS`). See `docs/PR-D2-gov-0033-d1-amendment.md`, `docs/warden-rollout-pr-d.md`. | none |
| `canon-wallet-green-ci` | org → `fabric-wallet`; `ref_name.include`: `refs/heads/dev`, `refs/heads/main` | PR required; strict status checks `Lint`, `Security Scan`, `Test`, `Migration Checksum` @ Actions **15368**; 0 reviews (live **24489464**) | none |
| `canon-branch-name-guard-pinned` (F6-D6) | org → fabricbloc `~DEFAULT_BRANCH` | Required workflow `branch-name-guard` @ pin (`pins.branch_name_guard_sha`) | none |
| `main-required-ci` | fabricbloc `~DEFAULT_BRANCH` | No delete or force-push, linear history, PR with 0 approvals and squash only, 9 contexts pinned to Actions 15368 | OrganizationAdmin (`pull_request`) |
| `canon-branch-creation-restricted` (finding c B) | fabricbloc `refs/heads/**` minus main, `agent/**`, explicit GOV-0022 handle paths (`dependabot/**` blocked until configured); excludes must not cover all branches (`refs/heads/**`, `~ALL`, etc.) | Blocks branch **creation** for non-exempt names | none (disable ruleset) |
| `canon-branch-creation-restricted` | context — same exempt set as fabricbloc (default **main**) | Blocks branch **creation** outside main, `agent/**`, and GOV-0022 handle paths | none (disable ruleset) |
| `canon-branch-creation-restricted` | keyflo-session-issuer — fabricbloc set plus **`dev`** (repo default) | Blocks branch **creation** outside dev, main, `agent/**`, and handle paths | none (disable ruleset) |
| `canon-deploy-branches-human-only` (finding c) | fabricbloc `release/**`, `prod/**` | Blocks **creation** and **update** | none (disable ruleset) |
| `canon-agent-branches` | fabricbloc `agent/**` | No force-push | none |
| `canon-provider-branches-blocked` (Q12) | fabricbloc `cursor/**` `codex/**` `claude/**` `qwen/**` | Creation blocked | none |
| `canon-autonomous-branch-creation` (Q16, held) | fabricbloc `agent/autonomous/**` | Only fabricbloc-agent-ops and admins create | Integration 5170152, OrganizationAdmin |
| `canon-push-protected-paths` (Q14) | fabricbloc push | Rejects pushes touching workflows, actions, CODEOWNERS, `.cursor`, `.claude/hooks`, `.gitmodules`, engine, gate scripts | OrganizationAdmin |
| `policy-main-protected` | this repo `~DEFAULT_BRANCH` | No delete or force-push, linear history, PR required, only admins may update | OrganizationAdmin (`pull_request`) |

The orphan `ledger` branch on fabricbloc (harvest/retention workflows, `agent-run-ledger`, review-lane scripts) already exists; creation-restricted does not block **updates** to it. No `ledger` exclude — if the branch is deleted, disable this ruleset to recreate it, then re-enable (drift flags the disabled interval).

Validate: `python3 agent-gates/validate_canon.py` (checks every body against GitHub's OpenAPI schema). The apply-workflow spec is unchanged from the cursor-env draft: a company App with org `administration: write`, upsert by name, never delete, and dispatch `policy-applied` to fabricbloc. That App is never a bypass actor.

## Ruleset drift (live GitHub vs this file)

Recorded deltas so cursor-env / manual audits do not treat intentional live state as surprise drift:

| Live ruleset | ID | Note |
|---|---|---|
| `canon-agent-gates` (org) | 24445414 | **Active**, no bypass. Repos: `fabricbloc`, `context`, `keyflo-session-issuer`. `ref_name.include` matches canon (four entries). Live workflow refs @ `1ddbd5bc04e4d7afa69be602aceede299774624d` until org ruleset **24445414** is updated to `ed19bddc0c79cd96349ec88a317a80b6743e61cf` (canon after #57 / post–#57 re-pin PR). Retarget applied **2026-10-04 PT** (MadAgentPM). |
| `main-required-ci` (fabricbloc) | 20436874 | **Require branches to be up to date before merging** is **OFF**, matching `canon.json` `strict_required_status_checks_policy: false`. The **six** required status check contexts are unchanged from the pre-toggle set. **Merge queue** is not available on GitHub Team for private repos (documented limitation; not in canon). |

**Policy ownership:** Changes to org gate targeting (`TARGET_REPOS` in `agent-gates/embedded_gate.py`, `canon-agent-gates` `repository_name` in `canon.json`) are owned by **Warden** (FabricBloc tech-policy owner bot). Human CODEOWNERS review stays unchanged.
