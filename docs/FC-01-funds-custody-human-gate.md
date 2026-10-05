# FC-01 — funds/custody named human gate

**Status:** **Approved** — council-delegated founder decision (**2026-10-05**); process/cite until a later hook or CI enforcer.

## Rule (FC-01)

Default to **testnet/fork**. Changes to **mainnet** config, **live signer keys** (`DEPLOYER_KEY` / `OPERATOR_KEY` or equivalents), **treasury** / live contract addresses, or **production deploy** paths require **named human** approval (**Cris**) before merge or apply. Agents must not perform those changes unilaterally.

## Named human

**Cris** (founder). Council delegation covers publishing this policy ID; it does **not** remove Cris approval for live keys, prod infra, IAM, secrets, or irreversible acts.

## Who should cite FC-01

After this policy merges, consumer repos may cite **FC-01** by ID in `AGENTS.md` / runbooks (do not copy full rule prose):

- fabric-platform
- fabric-wallet
- fabric-contracts
- fabric-tss
- fabric-auth
- Peer services with mainnet, treasury, prod deploy paths, or live deployer/operator key boundaries

## Enforcement today

This repo records **FC-01** in [POLICY_INDEX.md](../POLICY_INDEX.md) and [domains/06-funds-custody/](../domains/06-funds-custody/). There is **no** org ruleset, IAM, or secrets-registry change in the FC-01 publication PR. Automated enforcement may follow in a later change.

## Record

- **Decision:** [DECISIONS.md](../DECISIONS.md) item **15**
- **Domain contract:** [domains/06-funds-custody/CONTRACT.md](../domains/06-funds-custody/CONTRACT.md)
- **Class:** Council-delegated founder decision (Fleet Council canon gap — Aether Wave C **B1**)
