# 06-funds-custody contract

Job: Citeable **funds/custody human gate** for fabric-platform, fabric-wallet, fabric-contracts, fabric-tss, fabric-auth, and peers.

IN: Aether Wave C **B1** boundary (mainnet / live signer keys / treasury prose with no POLICY_INDEX ID).

OUT: **FC-01** in [POLICY_INDEX.md](../../POLICY_INDEX.md); consumer doc [docs/FC-01-funds-custody-human-gate.md](../../docs/FC-01-funds-custody-human-gate.md).

GATE: **Warden** owns policy text; **Sentinel** reviews security-sensitive diffs; **Cris** still approves live key and production infra acts (not delegated to council).

ESC: Warden → Cris for prod infra, IAM, secrets, or irreversible actions.

Verify: `make validate`.
