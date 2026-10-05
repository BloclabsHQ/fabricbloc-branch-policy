# Reviewer identity (distinct from agent authors)

## Problem

Agent PRs are authored by **`cursoragent`** (and related agent identities). Any verdict or approval path that trusts the same logins lets an agent **PASS its own PR**. Review-of-record must come from an identity that cannot be the PR author or a commit participant.

**`verdict_approval_enabled`** is **`true`** in `rulesets/reviewers.json`. **`verdict_app`** is pinned to **fabricbloc-verdict[bot]** / **337980250** (App **5193724**); comment trust requires **both** login and numeric id. Verdict posting still needs the App PEM on reviewer bots (pending from Cris). The **fabricbloc-reviewer** App still auto-approves **deterministic** docs/fixtures when allowed.

## Options

### A. Dedicated verdict GitHub App (recommended)

Create **`fabricbloc-verdict`** (separate from **fabricbloc-reviewer**):

- The verdict App posts issue comments containing `<!-- fabricbloc-verdict v1 reviewer=<slug> verdict=PASS|FAIL head=<head> -->` from its bot login only.
- Store the verdict App **private key only** in reviewer bot secrets (MadAgentPM, Sentinel, Aether, Warden) — **not** author bots, **not** Actions for verdict posting.
- Pin **`verdict_app`** `{ login, user_id }` in `rulesets/reviewers.json` (never author/committer logins).
- Keep **fabricbloc-reviewer** in Actions with minimal repo scope; it only submits the GitHub **APPROVE** after the gate validates a verdict (when enabled) or deterministic auto-approve.

**Cris setup:** create App, install on target repos, add bot to `ai_reviewers` in engine config via human PR, add identity to `trusted_verdict_identities`, distribute key to reviewer cloud envs, set `verdict_approval_enabled: true` via human PR + ruleset re-pin.

### B. Signed verdict + public key in canon

Reviewer agents emit a signed payload (head SHA, reviewer slug, timestamp). The gate verifies against a **public key** pinned in `rulesets/canon.json` or `reviewers.json`. No GitHub comment trust. Requires agent-side signing tooling and rotation process.

### C. Human-only APPROVE (status quo extension)

Disable all App automation; require a human **User** approval at head. Simplest trust model; highest latency for solo maintainer unless combined with deterministic auto-approve for low-risk paths only.

## Recommendation

**Option A** — separate **fabricbloc-verdict** App whose key never enters Actions, paired login+id in canon, **`verdict_approval_enabled`** flipped only after Cris validates end-to-end on a probe PR.

Until reviewer bots hold the verdict App PEM, rely on routing labels plus deterministic auto-approve for low-risk paths; verdict-eligible ADRs/engine tests need PEM distribution per `docs/FABRICBLOC-VERDICT-APP-SETUP.md`.
