# 05-secrets

Canonical **names-only** catalog for GitHub org/repo secrets, variables, and selected runtime env names ([CONTRACT.md](./CONTRACT.md)).

Live GitHub App credentials for the five-app end state are registered per **GOV-0034** (FabricBloc GOV ADR: GitHub App creation, custody, and consolidation; adopted 2026-10-04). Inventory and custody notes: Aether consolidation review 2026-10-04. Key moves and rotation remain Sentinel + Cris; this repo records names and metadata only.

**Custody (registry metadata):**

- **Reviewer App (Option B):** `REVIEWER_APP_CLIENT_ID` / `REVIEWER_APP_PRIVATE_KEY` live in GitHub Actions environment `reviewer` on each agent-gated target repo (`fabricbloc`, `context`, `keyflo-session-issuer`), deployment branch **main** only (no `refs/pull/*`). Source of truth remains 1Password `fabricbloc-reviewer`; not repo-level on `fabricbloc-branch-policy`, not org-wide, not on agent boxes.
- **Verdict App:** `VERDICT_APP_*` and runtime alias `FABRICBLOC_VERDICT_PRIVATE_KEY` are **box-only** (`github.scope: box`) on reviewer-bot hosts; no Actions or org secret home.

Verify: `make validate` from repository root.
