# Repo hygiene (L1 reusable workflows)

Canonical Python lives in `hygiene/*.py`. Reusable workflows embed the same bytes via `hygiene/sync_embedded_hygiene.py` (same pattern as `agent-gates/embedded_gate.py`).

## Caller pin

Reusable workflows (pin each at `rulesets/canon.json` → `pins.hygiene_sha`):

| C | Workflow |
|---|----------|
| C1 | `hygiene-pr-ops-notify.yml` |
| C2 | `hygiene-stale.yml` |
| C3 | `hygiene-auto-merge.yml` |
| C4 | `hygiene-ci-red.yml` |
| C5 | `hygiene-branch-prune.yml` |
| C6 | `hygiene-backlog-lint.yml` |
| C7 | `hygiene-deploy-green-gate.yml` |

Example caller:

```yaml
uses: BloclabsHQ/fabricbloc-branch-policy/.github/workflows/hygiene-pr-ops-notify.yml@<pins.hygiene_sha>
secrets:
  SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
```

Do not use `secrets: inherit`.

## Kill switches

- Org/repo variable `HYGIENE_ENABLED`: set to `false` to stop all hygiene callers.
- Per-component `HYGIENE_<C>_MODE`: `off` | `dry-run` | `live` (defaults per spec when unset).

## TODO(Cris) credentials (not created in this repo)

- **T1** (`fabricbloc-hygiene` GitHub App, numeric App ID **5184966**, installation **167787762** on `fabricbloc`, `context`, `keyflo-session-issuer`): C2 stale close and C3 auto-merge (live). Set org or repo variable **`HYGIENE_APP_CLIENT_ID`** = `Iv23lirH8HiEe4cZj3V8` (GitHub App **Client ID**, not the numeric App ID). Set org or repo secret **`HYGIENE_APP_PRIVATE_KEY`** to the App’s PEM private key (Cris adds in GitHub; **never** commit to the repo). Callers pass `secrets.HYGIENE_APP_PRIVATE_KEY` and `vars.HYGIENE_APP_CLIENT_ID` into the reusable hygiene workflows.
- **T2** `SLACK_BOT_TOKEN`: org secret restricted to selected repos (C1, C5). Sentinel confirms no PR-head execution in hygiene jobs.
