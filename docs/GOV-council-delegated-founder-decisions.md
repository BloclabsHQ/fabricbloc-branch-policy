# GOV — council-delegated founder decisions (Fleet Council canon gaps)

**Status:** **Approved** — canon prose only; no org apply from this file alone.

## Cris approval (record)

- **Decision:** Fleet Council closes canon gaps immediately under delegated founder authority; discussion is FYI only.
- **When:** **2026-10-05 ~01:05 PT**
- **Relay:** MadGeniusBot
- **Class:** **Council-delegated founder decision** (recorded in `DECISIONS.md` item **13**)

## Rule

When the Fleet Council identifies a **canon gap** (missing or wrong ADR, GOV text, decision log entry, executable rule, or fleet context), the **owning bot** applies the fix as a **PR right away**. Council chat and async discussion are **informational** — they do not block the owning bot from opening and landing policy text within merge rules.

| Gap type | Owner bot | Primary repo |
|---|---|---|
| Rules / branch policy / pins prose | **Warden** | `BloclabsHQ/fabricbloc-branch-policy` |
| ADR / architecture | **Aether** | `BloclabsHQ/fabricbloc` (decisions/) |
| Context / ICM structure | **MadICM** | `BloclabsHQ/context` |
| Tools / ATLAS | **MadTechBot** | per ATLAS ownership |

## Recording and merge

- Tag each landed fix in **`DECISIONS.md`** (this repo) or the owning repo’s decision log as a **council-delegated founder decision**, with approver, date, and relay bot when applicable.
- **Merge** within existing GitHub policy (required checks, review-of-record, rulesets). **Sentinel** reviews **security-sensitive** diffs before merge when the change touches secrets, IAM, workflows, or gate logic.
- **Escalation:** if a council finding has **no PR within 24 hours**, **MadGeniusBot** escalates to Cris.

## Still Cris-only (not council-delegated)

These remain **founder approval** only — typically batched in the **morning approvals** run:

- Production infrastructure changes
- IAM and credential moves
- Secrets creation, rotation, or exposure
- Deletes and other **irreversible** actions

## Operational log (reference)

MadGeniusBot maintains a running fix log at **`/home/box/shared/council/fix-log.md`** on the fleet box. That path is **operational reference only** — it is **not** mirrored as a file in this repository.

## Related

- `DECISIONS.md` item **13**
- Upload / council fix log entries (e.g. branch-policy #47, fabricbloc #1580)
