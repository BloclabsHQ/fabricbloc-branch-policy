# 03-agent-gates contract

Job: Pinned org workflows enforce agent PR boundaries (denied paths, review-of-record, projection).

IN: `embedded_gate.py`; fabricbloc base manifest; GOV-0006 / ARCH-0048.

OUT: `agent-denied-paths` and `agent-review-of-record` @ pinned SHA in `rulesets/canon.json`; optional owner override via `rulesets/gate-owners.json` (AG-06, `docs/owner-approved-agent-gates.md`).

GATE: Re-pin org `canon-agent-gates` after every gate change (P3).

Verify: `python3 agent-gates/test.py`.

Funds/custody human gate → **FC-01** (`domains/06-funds-custody/`).
