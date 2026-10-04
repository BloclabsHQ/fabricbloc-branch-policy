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
| `canon-agent-gates` | org → fabricbloc `~DEFAULT_BRANCH`, `release/**`, `prod/**` (bootstrap: `refs/heads/f6-gate-test`; step 5 widens ref scope in org UI) | Required workflows `agent-denied-paths`, `agent-review-of-record` from this repo @ pinned SHA (F6 + finding c base-ref rule) | none |
| `canon-branch-name-guard-pinned` (F6-D6) | org → fabricbloc `~DEFAULT_BRANCH` | Required workflow `branch-name-guard` @ `e8e6a8e` | none |
| `main-required-ci` | fabricbloc `~DEFAULT_BRANCH` | No delete or force-push, linear history, PR with 0 approvals and squash only, 9 contexts pinned to Actions 15368 | OrganizationAdmin (`pull_request`) |
| `canon-branch-creation-restricted` (finding c B) | fabricbloc `refs/heads/**` minus main, `agent/**`, GOV-0022 handle paths | Blocks branch **creation** for non-exempt names | OrganizationAdmin (`always`; no UI-only mode in API) |
| `canon-deploy-branches-human-only` (finding c) | fabricbloc `release/**`, `prod/**` | Blocks **creation** and **update** except org admin bypass | OrganizationAdmin (`always`) |
| `canon-agent-branches` | fabricbloc `agent/**` | No force-push | none |
| `canon-provider-branches-blocked` (Q12) | fabricbloc `cursor/**` `codex/**` `claude/**` `qwen/**` | Creation blocked | none |
| `canon-autonomous-branch-creation` (Q16, held) | fabricbloc `agent/autonomous/**` | Only fabricbloc-agent-ops and admins create | Integration 5170152, OrganizationAdmin |
| `canon-push-protected-paths` (Q14) | fabricbloc push | Rejects pushes touching workflows, actions, CODEOWNERS, `.cursor`, `.claude/hooks`, `.gitmodules`, engine, gate scripts | OrganizationAdmin |
| `policy-main-protected` | this repo `~DEFAULT_BRANCH` | No delete or force-push, linear history, PR required, only admins may update | OrganizationAdmin (`pull_request`) |

Validate: `python3 agent-gates/validate_canon.py` (checks every body against GitHub's OpenAPI schema). The apply-workflow spec is unchanged from the cursor-env draft: a company App with org `administration: write`, upsert by name, never delete, and dispatch `policy-applied` to fabricbloc. That App is never a bypass actor.
