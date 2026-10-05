# Reviewer routing and App auto-approve (PR-C)

Canon: `rulesets/reviewers.json` loaded from `fabricbloc-branch-policy` at **`pins.agent_gates_sha`** (never the PR head). See `docs/REVIEWER-IDENTITY.md`.

## Auto-approve (today)

**`verdict_approval_enabled`** is **`false`**. Verdict comments do not trigger App approval.

**fabricbloc-reviewer** (App **5185203**, bot **337673700**) may submit APPROVE only when:

- `agent-denied-paths` is **success** on the head commit,
- **every** changed path (new **and** `previous_filename` on renames) passes **deny → route → allow** (case-insensitive): not on **`deterministic_auto_approve_exclusions`**, not matching any **reviewer route**, not on **agent-denied-paths** floor/manifest, and on the small **`deterministic_auto_approve_allowlist`** (`docs/**`, `**/fixtures/**`, `**/testdata/**` only),
- no **cris_required** route on the PR set, and
- `REVIEWER_APP_TOKEN` is minted (requires org/repo **`REVIEWER_APP_CLIENT_ID`** var + **`REVIEWER_APP_PRIVATE_KEY`** secret). If the key is missing, the workflow **skips** token mint with a notice (no fail solely for missing key).

## Routing (priority)

Highest **`priority`** route wins: cris (prod/IAM/secrets) → sentinel (auth/crypto, `src/auth`, fabric-wallet) → warden (policy/workflows) → aether (iac/infra) → default **madagentpm**.

## Verdict markers (when enabled)

Trusted identities are **`(login, user_id)`** pairs in `trusted_verdict_identities` — never PR author or commit participants. Marker must match routed reviewer and head SHA; edited comments and fenced code blocks are ignored.

```html
<!-- fb-verdict: PASS reviewer=madagentpm sha=<40-char PR head SHA> -->
```

Human GOV-0022 PRs still skip agent gates (F6-D2/D3).
