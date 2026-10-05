# GOV — bots never count as reviewers (review-of-record)

**Status:** **Approved** — canon prose only; executable gate behavior follows pinned SHAs until a deliberate re-pin.

## Cris approval (record)

- **Decision:** Bot logins do not satisfy independent PR review; review-of-record is the reviewer App or a non-author human.
- **When:** **2026-10-05**
- **Relay:** MadTechBot
- **Class:** **Council-delegated founder decision** (recorded in `DECISIONS.md` item **14**)

## Rule

Fleet automation runs under shared operator identity (**`madgeniusblink`**). Any **bot** or **App** login that is **not** the designated reviewer App must be treated as **agent-side automation**, not as an independent reviewer.

**Do not count toward review-of-record or merge policy “human review”:**

- Any `*[bot]` login used for fleet bots (verdict bots, author bots, hygiene bots, etc.)
- Engine **`ai_reviewers`** entries from `config.yaml`
- **`APPROVE`** reviews submitted by automation acting as **`madgeniusblink`** when that review is standing in for a bot workflow

**Review-of-record** (satisfies pinned **`agent-review-of-record`** and org review-count intent for agent PRs) is exactly one of:

| Identity | Requirement |
|---|---|
| **`fabricbloc-reviewer[bot]`** | GitHub user id **337673700** — login **and** numeric id must match the pinned allowlist |
| **Human** | GitHub **`User`** (not bot) who is **not** the PR author and not treated as agent identity on that PR |

This is **distinct** from **verdict** trust (**fabricbloc-verdict** comment markers) and from **Option B** split workflow facts in `docs/REVIEWER-IDENTITY.md` — those controls stay as documented; this decision clarifies **who counts as a reviewer** for policy and Cris-only gates.

## Cris-only deployment environments

GitHub **environment** protection used for **Cris-only** paths (secrets, prod deploy, irreversible ops) must bind required reviewers to:

- A **human-only** reviewer set (no bot logins), **or**
- Cris Slack user id **U083ZJDP9EC**

**Never** bind Cris-only gates to login **`madgeniusblink`** alone — that login is shared with fleet automation and is not proof of Cris human review.

## Amendment to prior canon

**F6-D10** allowed **`ai_reviewers`** to count as review-of-record approvers. **Item 14** supersedes that clause for **policy prose**. Changing embedded gate allowlists requires a **follow-up PR** that edits `agent-gates/embedded_gate.py`, syncs workflows, and re-pins org rulesets — out of scope for the council-delegated docs-only fix.

## Related

- `DECISIONS.md` items **10**, **11**, **14**
- `docs/REVIEWER-IDENTITY.md`
- `docs/PR-D2-gov-0033-d1-amendment.md` (org `required_approving_review_count: 1` + App **337673700**)
