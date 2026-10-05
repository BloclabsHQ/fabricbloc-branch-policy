# fabric-wallet: green CI before merge and deploy

**Policy repo only.** This file is documentation for changes in `BloclabsHQ/fabric-wallet` after Cris approves and applies org ruleset `canon-wallet-green-ci` from `rulesets/canon.json`.

## Incident context

PRs **#1433** and **#1435** merged into `dev` while CI was red or still running. **#1433** shipped a GORM regression to the dev ECS environment (~05:46 PT, 2026-10-04). The **Dev CI/CD Pipeline** (`.github/workflows/cicd.yaml`, job `build-and-deploy`) runs on push to `dev` and does not run tests.

## Org ruleset (canon draft)

Org ruleset **`canon-wallet-green-ci`** (founder yes **WALLET-GREEN-CI** recorded 2026-10-05 01:01 PT; apply after policy PR **#47** merges):

| Item | Value |
|---|---|
| Scope | `fabric-wallet` (extend `conditions.repository_name.include`) |
| Branches | `refs/heads/dev`, `refs/heads/main` |
| Merge gate | Pull request required; **0** approving reviews (solo maintainer OK) |
| Strict | Branches must be up to date before merge |
| Bypass | None (consistent with F6-D2; not an agent gate — F6-D3 unchanged) |
| Required checks (GitHub Actions **15368**) | `Lint`, `Security Scan`, `Test`, `Migration Checksum` |

**Docs-only PRs:** `ci.yml` skips heavy jobs via job-level `if:`; skipped jobs report **success**, so merges are not deadlocked. Do not require `Detect changes` (draft PRs skip there).

## Deploy gate (reusable workflow)

Pin `hygiene-deploy-green-gate.yml` at `rulesets/canon.json` → `pins.hygiene_sha` after the policy-repo change merges and is re-pinned.

Before `build-and-deploy`, verify the **merged PR head** had green checks (fail closed if no merged PR or checks missing/failed). Default required checks for deploy: `Lint`, `Security Scan`, `Test` (subset of merge gate).

### Ready-to-paste: `cicd.yaml` caller snippet

Add a job **before** `build-and-deploy` (adjust pin SHA after hygiene re-pin):

```yaml
  verify-ci-green:
    runs-on: ubuntu-latest
    permissions:
      actions: read
      contents: read
      pull-requests: read
    steps:
      - uses: BloclabsHQ/fabricbloc-branch-policy/.github/workflows/hygiene-deploy-green-gate.yml@<pins.hygiene_sha>
        with:
          commit_sha: ${{ github.sha }}
          required_checks: '["Lint","Security Scan","Test"]'

  build-and-deploy:
    needs: verify-ci-green
    # ... existing build-and-deploy job ...
```

Do **not** use `secrets: inherit` on the reusable workflow call.

### Alternative (no reusable workflow)

Run tests in the deploy job itself, e.g. `go test ./...` (and lint/security if not covered), and fail the deploy when tests fail. This does not prove PR CI ran on the same commit graph as the merge, so the reusable gate (or ruleset-only merge blocking) is preferred for “no green test run shipped.”

## Open questions for Cris

- Confirm merge methods on `dev`/`main` (`allowed_merge_methods` allows merge, squash, rebase).
- After apply, re-open or push existing open PRs so required checks register.
- Whether `main` should use the same deploy gate when a production pipeline is added.
