# Policy index

| ID | Domain | Rule (one line) | Enforcer | Test |
|---|---|---|---|---|
| MR-11 | 02-merge-rulesets | fabricbloc deployment envs: no admin bypass; agent-ops deploys from main only; prevent_self_review when reviewers set | Scheduled `policy-env-drift.yml` | domains/02-merge-rulesets/env-drift/tests/test_env_drift.py |
