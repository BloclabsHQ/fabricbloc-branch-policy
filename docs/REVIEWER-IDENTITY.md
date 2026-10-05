# Reviewer identity (distinct from agent authors)

## Problem

Agent PRs are authored by **`cursoragent`** (and related agent identities). Any verdict or approval path that trusts the same logins lets an agent **PASS its own PR**. Review-of-record must come from an identity that cannot be the PR author or a commit participant.

**`verdict_approval_enabled`** is **`true`** in `rulesets/reviewers.json`. **`verdict_app`** is pinned to **fabricbloc-verdict[bot]** / **337980250** (App **5193724**); comment trust requires **both** login and numeric id. Verdict posting still needs the App PEM on reviewer bots (pending from Cris). The **fabricbloc-reviewer** App still auto-approves **deterministic** docs/fixtures when allowed.

## fabricbloc-reviewer PEM in Actions (split design, 2026-10-05)

Org ruleset **`canon-agent-gates`** requires the pinned **`agent-review-of-record`** workflow. That workflow is **split**:

| Job | Trigger | Secrets / environment | Role |
|---|---|---|---|
| **`agent-review-of-record`** | **`pull_request`** | **None** — no `environment:`, no PEM | Exact-head allowlisted **APPROVE** check (API only). This is the required check. |
| **`reviewer-app-auto-approve`** | **`pull_request_target`** | **`environment: reviewer`** only | Mint App token; submit **APPROVE** when verdict/deterministic path allows (API + issue comments only). |

**Why `pull_request_target` for mint:** runs in the **base repo context** with **`GITHUB_REF`** on the **base branch** (e.g. `refs/heads/main`), so the PEM can live in environment **`reviewer`** with **main-only** deployment rules.

**MadAgentPM — environment `reviewer` on each gated repo (`fabricbloc`, `context`, `keyflo-session-issuer`):**

| Setting | Value |
|---|---|
| Secrets | `REVIEWER_APP_PRIVATE_KEY` (PEM) — **environment only** |
| Variables | `REVIEWER_APP_CLIENT_ID` — **environment only** |
| Deployment branch rules | **`main` only** (branch name `main`) |

**Hard rule — no environment deployment rule may match `refs/pull/*` or `refs/pull/*/merge`.** Allowing pull refs would let a malicious workflow on `pull_request` reach the PEM when merge refs are permitted.

**Q14 is live:** **`canon-push-protected-paths`** blocks non-admin pushes to workflow paths, but **cursor[bot] pushes** under the Cursor App installation — do **not** treat Q14 as sufficient to stop an agent from adding `environment: reviewer` on a `pull_request` job. The split + main-only env rules are the control.

**Invariants:**

- **No checkout** and **no execution** of PR head code in either job.
- **No** repo-level, org-level, or 1Password-in-Actions fallback for the reviewer PEM; unset env → mint skipped (notice only).
- Both jobs run only when the PR targets **`main`**.
- App id **5185203** stays hardcoded in the mint job.

After merge, **re-pin** org ruleset **24445414** to the new workflow SHA (required workflow must include **`pull_request_target`** for the mint job path).

## Options (verdict trust)

### A. Dedicated verdict GitHub App (recommended)

Create **`fabricbloc-verdict`** (separate from **fabricbloc-reviewer**):

- The verdict App posts issue comments containing `<!-- fabricbloc-verdict v1 reviewer=<slug> verdict=PASS|FAIL head=<head> -->` from its bot login only.
- Store the verdict App **private key only** in reviewer bot secrets (MadAgentPM, Sentinel, Aether, Warden) — **not** author bots, **not** Actions for verdict posting.
- Pin **`verdict_app`** `{ login, user_id }` in `rulesets/reviewers.json`.
- **fabricbloc-reviewer** mint/approve stays in **`reviewer-app-auto-approve`** only.

### B. Signed verdict + public key in canon

Reviewer agents emit a signed payload. Gate verifies against a pinned public key. No GitHub comment trust.

### C. Human-only APPROVE

Disable App automation; require human **User** approval at head.

## Recommendation

**Option A** for verdict trust; **split workflow + environment reviewer** for reviewer App PEM custody.

Until reviewer bots hold the verdict App PEM, rely on routing labels plus deterministic auto-approve for low-risk paths; verdict-eligible paths need PEM per `docs/FABRICBLOC-VERDICT-APP-SETUP.md`.
