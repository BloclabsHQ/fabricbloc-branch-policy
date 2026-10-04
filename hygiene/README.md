# Repo hygiene (L1 reusable workflows)

Canonical Python lives in `hygiene/*.py`. Reusable workflows embed the same bytes via `hygiene/sync_embedded_hygiene.py` (same pattern as `agent-gates/embedded_gate.py`).

## Caller pin

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

- **T1** (`fabricbloc-hygiene` GitHub App): C3 merge only. Callers pass `secrets.HYGIENE_APP_PRIVATE_KEY` and `vars.HYGIENE_APP_ID`.
- **T2** `SLACK_BOT_TOKEN`: org secret restricted to selected repos (C1, C5). Sentinel confirms no PR-head execution in hygiene jobs.
