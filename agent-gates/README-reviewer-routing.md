# Reviewer routing and App auto-approve (PR-C)

Canon: `rulesets/reviewers.json` loaded from `fabricbloc-branch-policy` at **`pins.agent_gates_sha`** (never the PR head). See `docs/REVIEWER-IDENTITY.md`.

## Auto-approve

**fabricbloc-verdict** posts PR **comments** (Issues API). **fabricbloc-reviewer** (App **5185203**, bot **337673700**) submits the GitHub **APPROVE** after the gate validates verdicts or deterministic allowlist rules.

**Two-tier agent-denied-paths**

- **Cris-only** — check **fails** (workflows, engine code/manifests/approval_relay, GOV-* ADRs, rulesets, canon files, floor/manifest entries, unsafe paths).
- **Verdict-eligible** — check **passes** with a notice; **review-of-record** needs PASS markers from **fabricbloc-verdict[bot]** for every required reviewer slug.

**fabricbloc-reviewer** may submit APPROVE when:

- Newest **`agent-denied-paths`** run from GitHub Actions **app id 15368** is **success** on head,
- No **Cris-only** paths in the diff (including `previous_filename` on renames),
- **Verdict path** (`verdict_approval_enabled: true`): every required reviewer has an unedited, unfenced PASS at head from **`verdict_app`** (**fabricbloc-verdict[bot]** / **337980250**; both must match). Any slug FAIL at head blocks approval. **`user_id: 0` fails closed** if ever reintroduced,
- **Deterministic** path (unchanged): pure allowlisted docs/fixtures under pinned extension policy, no routes/exclusions/Cris-only/verdict-eligible paths,
- No **cris_required** route, and
- `REVIEWER_APP_TOKEN` minted when submitting APPROVE (missing key → skip with notice).

## Routing (priority)

Highest **`priority`** route wins: cris (prod/IAM/secrets) → sentinel (auth/crypto, `src/auth`, fabric-wallet) → warden (policy/workflows) → aether (iac/infra) → default **madagentpm**.

## Verdict markers

Only **fabricbloc-verdict[bot]** (pinned in **`verdict_app`**) may post markers. Reviewer slug must be one of **`madagentpm`**, **`sentinel`**, **`aether`**, **`warden`**. **`head`** must equal the PR head SHA (40 hex). Edited comments and fenced code blocks are ignored.

```html
<!-- fabricbloc-verdict v1 reviewer=madagentpm verdict=PASS head=<40-char PR head SHA> -->
```

Required slugs: **`madagentpm`** always; route reviewer from `reviewers.json`; plus **`aether`** (+ **`sentinel`** when sensitive) for non-GOV ADRs; **`sentinel`** for verdict-eligible engine tests/docs.

Human GOV-0022 PRs still skip agent gates (F6-D2/D3).
