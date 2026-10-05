# Reviewer identity (distinct from agent authors)

## Problem

Agent PRs are authored by **`cursoragent`** (and related agent identities). Any verdict or approval path that trusts the same logins lets an agent **PASS its own PR**. Review-of-record must come from an identity that cannot be the PR author or a commit participant.

Today **`verdict_approval_enabled`** is **`false`** in `rulesets/reviewers.json`. The **fabricbloc-reviewer** App may auto-approve only the **deterministic** case: `agent-denied-paths` green, default **`madagentpm`** route, no sensitive/cris class. Everything else is routed and labeled for human or specialist review.

## Options

### A. Dedicated verdict GitHub App (recommended)

Create **`fabricbloc-verdict`** (separate from **fabricbloc-reviewer**):

- The verdict App posts issue comments containing `<!-- fb-verdict: PASS reviewer=<slug> sha=<head> -->` from its bot login only.
- Store the verdict App **private key only** in the **Cursor cloud environments** of reviewer agents (Sentinel, Warden, Aether, MadAgentPM) — **not** in GitHub Actions secrets.
- Pin **`trusted_verdict_identities`** to the verdict App bot **`(login, user_id)`** pair in `rulesets/reviewers.json` (never author/committer logins).
- Keep **fabricbloc-reviewer** in Actions with minimal repo scope; it only submits the GitHub **APPROVE** after the gate validates a verdict (when enabled) or deterministic auto-approve.

**Cris setup:** create App, install on target repos, add bot to `ai_reviewers` in engine config via human PR, add identity to `trusted_verdict_identities`, distribute key to reviewer cloud envs, set `verdict_approval_enabled: true` via human PR + ruleset re-pin.

### B. Signed verdict + public key in canon

Reviewer agents emit a signed payload (head SHA, reviewer slug, timestamp). The gate verifies against a **public key** pinned in `rulesets/canon.json` or `reviewers.json`. No GitHub comment trust. Requires agent-side signing tooling and rotation process.

### C. Human-only APPROVE (status quo extension)

Disable all App automation; require a human **User** approval at head. Simplest trust model; highest latency for solo maintainer unless combined with deterministic auto-approve for low-risk paths only.

## Recommendation

**Option A** — separate **fabricbloc-verdict** App whose key never enters Actions, paired login+id in canon, **`verdict_approval_enabled`** flipped only after Cris validates end-to-end on a probe PR.

Until then, leave **`verdict_approval_enabled: false`** and rely on routing labels plus deterministic auto-approve for default-route agent PRs with green denied-paths.
