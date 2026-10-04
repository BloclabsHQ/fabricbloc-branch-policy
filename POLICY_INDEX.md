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
