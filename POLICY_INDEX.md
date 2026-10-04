# Policy index

One row per enforced rule. Consumers pin this repo at a release SHA and cite IDs only.

| ID | Domain | Rule (one line) | Enforcer | Test |
|---|---|---|---|---|
| CU-01 | 04-cursor | One agent per PR: `find_by_pr` then `reply`; never relaunch on existing agent | Harness / session registry | domains/04-cursor/tests/test_cloud_sessions.py |
| CU-02 | 04-cursor | Branch names match `session_branch_regex` (GOV-0022 agent grammar) | Harness launch + BR guard | domains/04-cursor/tests/test_cloud_sessions.py |
| CU-03 | 04-cursor | Caps: 4 running, 2 per bot, 2 per repo, 6 launches/h | Harness registry | domains/04-cursor/tests/test_cloud_sessions.py |
| CU-04 | 04-cursor | One slot reserved for MadEngineer product hotfixes | Harness registry | domains/04-cursor/tests/test_cloud_sessions.py |
| CU-05 | 04-cursor | Re-check registry and claim immediately before launch; dedupe after launch | Harness registry | domains/04-cursor/tests/test_cloud_sessions.py |
| CU-06 | 04-cursor | No in-agent sleep or CI poll wait over 120s | Harness / stop hooks | domains/04-cursor/tests/test_cloud_sessions.py |
| CU-07 | 04-cursor | Archive when idle ≥24h or PR merged/closed/accepted no-change report | Harness archive job | domains/04-cursor/tests/test_cloud_sessions.py |
| CU-08 | 04-cursor | Agent/harness tickets: label → MadAgentPM → Loom | Process routing | domains/04-cursor/tests/test_cloud_sessions.py |
| CU-09 | 04-cursor | Loom never reviews its own PRs | Review-of-record + routing | domains/04-cursor/tests/test_cloud_sessions.py |
| CU-10 | 04-cursor | Phase-in: new sessions only; grandfather MadEngineer in-flight + `agent/autonomous/**` | Harness | domains/04-cursor/tests/test_cloud_sessions.py |
| AG-04 | 03-agent-gates | Deny agent PR edits under floor paths; `.cursor/**` and `.claude/**` warn-first (`PROVIDER_CONTROL_ENFORCE`) | Pinned `agent-denied-paths` | agent-gates/test.py |
| AG-05 | 03-agent-gates | Projection must be URL or pinned SHA/release asset, not parent checkout/submodule | Pinned `agent-denied-paths` (`PROJECTION_ENFORCE`) | agent-gates/test.py |
| SE-01 | 05-secrets | Name matches `<SCOPE>_<TYPE>[_NEXT]` or grandfather list | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
| SE-02 | 05-secrets | No `GH_*`/`GITHUB_*` refs; not `PAT`, `BLOC_TOKEN`, `FABRIC_TOKEN` | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
| SE-03 | 05-secrets | Workflow `secrets.*` / `vars.*` resolve to registry names | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
| SE-04 | 05-secrets | `_APP_ID` variable; `_APP_PRIVATE_KEY` secret; never `_INSTALLATION_TOKEN` | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
| SE-05 | 05-secrets | Active PATs declare access, `expires`, and `replace_with` | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
| SE-06 | 05-secrets | Org visibility/repos match live GitHub | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
| SE-07 | 05-secrets | Environment-scoped names pass MR-11 | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
| SE-08 | 05-secrets | Public-repo secrets read-only; no `pull_request*` consumer triggers | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
| SE-09 | 05-secrets | Cursor `runtime_env` on allow list; not `forbidden_patterns` | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
| SE-10 | 05-secrets | Rotation overdue warn 1× / fail 2× `rotation_days` | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
| SE-11 | 05-secrets | Live GitHub names missing from registry → policy-drift | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
| SE-12 | 05-secrets | Registry name set equals `SECRETS.md` | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
| SE-13 | 05-secrets | Every `active` entry has `onepassword_item` | `lint_registry.py` (report-only) | domains/05-secrets/tests/test_secrets_registry.py |
