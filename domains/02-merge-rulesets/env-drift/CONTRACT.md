# 02-merge-rulesets / env-drift contract

Job: Detect drift in BloclabsHQ/fabricbloc GitHub **deployment environments** (R4 agent-ops hardening).

IN: `manifest.json`; live GitHub REST (environments + deployment-branch-policies).

OUT: Scheduled `policy-env-drift` workflow; exit 1 + JSON report on drift.

GATE: Warden PR; token needs repository **Environments: read** on fabricbloc.

Verify: `python3 -m unittest discover -s domains/02-merge-rulesets/env-drift/tests`.
