# fabricbloc-branch-policy router

Policy-as-code for FabricBloc org gates and fleet rules. **Cite rule IDs from [POLICY_INDEX.md](POLICY_INDEX.md); never copy rule text into consumers.**

## Domains

| Domain | Path | IDs |
|---|---|---|
| Branches | `domains/01-branch-rules/` | BR-* |
| Merge rulesets | `domains/02-merge-rulesets/` | MR-* |
| Agent gates | `domains/03-agent-gates/` | AG-* |
| Cursor cloud | `domains/04-cursor/` | CU-* |
| Secrets | `domains/05-secrets/` | SE-* |
| Funds/custody | `domains/06-funds-custody/` | FC-* |

## Validate

```bash
make validate
```

Harnesses and session economy code consume pinned SHAs of this repo; they do not fork rule prose.

## Agent instructions

Public policy repo for FabricBloc branch naming (GOV-0022) and pinned enforcement workflows. Consumers call reusable workflows at immutable SHAs declared in `rulesets/canon.json`; pushing to this repo’s `main` does not change what runs until an org owner re-pins and applies rulesets.

## What this repo is

- **Branch-name guard:** canonical GOV-0022 grammar (`branch-name-guard/`, `.github/workflows/branch-name-guard.yml`).
- **Agent gates:** default-deny paths and review-of-record (`agent-gates/`, pinned workflows).
- **Rulesets:** declared org/repo protection bodies (`rulesets/canon.json`, `rulesets/bots.json`).
- **Domains:** cursor cloud sessions, secrets registry, env-drift checks under `domains/`.

No secrets, tokens, or production credentials belong in this tree. Do not commit or log secret values.

## Layout (edit here first)

| Area | Source of truth | Sync |
|---|---|---|
| Branch guard logic | `branch-name-guard/guard_logic.py` | `python3 branch-name-guard/sync_embedded.py` → workflow heredoc |
| Agent gates | `agent-gates/embedded_gate.py` | `python3 agent-gates/sync_embedded_gate.py` |
| Branch regex (BR-01 / BR-04) | `scripts/branch-name-policy.py` | keep aligned with guard logic |
| Canon pins | `rulesets/canon.json` `pins.*` | every `workflows[].sha` must match a pin |

## Validation

From repo root:

```bash
make validate
```

Runs canon schema checks, embedded sync drift checks, branch-name contract tests, agent-gates tests, hygiene/domain validators, and `scripts/validate_policy_index.py`. Fix sync drift by editing source files and re-running the sync scripts — never hand-edit embedded heredocs.

## Branch naming (this repo)

**Primary (agent):** `agent/<bot>/<type>/<scope>-<slug>`

- `<bot>`: lowercase role ID from `rulesets/bots.json` (not `session`, `autonomous`, or provider names).
- `<type>`: one of the eleven GOV-0022 types (`feat`, `fix`, `chore`, `docs`, …).
- `<scope>-<slug>`: lowercase hyphenated segments (slug requires at least one hyphen).

**Legacy dual-accept (grace):** `agent/(session|autonomous)/<type>/<scope>-<slug>` remains valid until **`pins.legacy_branch_pr_created_before`** (`2026-10-19T00:00:00Z` in `canon.json`). After that cutoff, legacy grammar is allowed only when the pull request `created_at` is earlier.

**Human branches:** `<handle>/<type>/<slug>` per GOV-0022 (see fabricbloc ADR).

**Blocked:** provider prefixes (`cursor/`, `codex/`, …) and `agent/<provider>/…`.

Use branches under `agent/warden/…` or other registered bots for agent work in this repo.

## Pins and re-pins

`pins.branch_name_guard_sha`, embedded `CANON_BOTS_JSON_SHA` in `guard_logic.py`, and `canon-branch-name-guard-pinned` in `canon.json` must share the **same full 40-char commit** whose `branch-name-guard.yml` includes `bot_agent_re` and `LEGACY_AGENT_RE`.

Current branch-name guard pin (see `rulesets/canon.json`): **`80ee4b19ad84f4cdb5dc1e923e19f54fc54a2c6a`**.

Re-pin steps:

1. Merge policy changes to `main`.
2. Human PR: set `pins.branch_name_guard_sha` to that main tip; update embedded `CANON_BOTS_JSON_SHA`; run `sync_embedded.py`; update ruleset workflow SHA entries.
3. Org-owner apply of `canon.json` (if rulesets change).
4. **Separate fabricbloc PR:** bump thin `branch-name-guard` caller and org/repo var `BRANCH_NAME_GUARD_SHA` to the same SHA.

Do not pin to obsolete session-only SHAs (`e8a5985`, pre-bot-format tips).

## Agent gates pin

`pins.agent_gates_sha` governs `agent-denied-paths` and `agent-review-of-record`. Re-pin both workflow SHAs in `canon-agent-gates` together with the pin field.

## Docs map

- `branch-name-guard/README.md` — guard grammars and phase-in.
- `rulesets/README.md` — ruleset apply order and scope.
- `POLICY_INDEX.md` — rule IDs (BR-*, AG-*, …) and test columns.
- `DECISIONS.md` — founder decisions (F6-D*).

## GOV-0006 (Pattern A)

`CONTEXT.md` is the local instruction body for this repository. `AGENTS.md` is the pointer-only entry file. Provider compatibility files, when present, also carry only a pointer. Submodule consumers pin this repository at an immutable commit and load the instruction body through those pointers.

When changing enforcement behavior, prefer minimal diffs, run `make validate`, and document pin bumps in the PR body for MadAgentPM / fabricbloc thin-caller follow-ups.
