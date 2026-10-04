# 02-merge-rulesets / env-drift contract

Job: Detect drift in BloclabsHQ/fabricbloc GitHub **deployment environments** (R4 agent-ops hardening).

IN: `manifest.json`; live GitHub REST (environments + deployment-branch-policies).

OUT: Scheduled `policy-env-drift` workflow; exit 1 + JSON report on drift.

GATE: Warden PR; live runs mint a read-only installation token via the fabricbloc-policy-audit GitHub App (see Credentials).

Verify: `python3 -m unittest discover -s domains/02-merge-rulesets/env-drift/tests`.

## Credentials

- **Purpose:** Read-only access to BloclabsHQ/fabricbloc deployment environments and deployment-branch-policies for the MR-11 drift audit.
- **Credential:** GitHub App `fabricbloc-policy-audit`. Store the App ID in the Actions variable `POLICY_AUDIT_APP_ID` and the private key in the Actions secret `POLICY_AUDIT_APP_PRIVATE_KEY`, both on `fabricbloc-branch-policy`. Each scheduled run mints a short-lived installation token passed to the drift step as `POLICY_AUDIT_INSTALLATION_TOKEN`.
- **Permissions:** Repository **Actions: read** plus **Metadata: read**, installed on `fabricbloc` only. The environments and deployment-branch-policies REST endpoints are satisfied by Actions read (not a separate Environments OAuth scope).
- **Read-only:** The audit never writes repository or environment settings.
- **Value storage:** Cris to fill: 1Password item
