# 05-secrets contract (Sentinel B0)

Job: Canonical **names-only** catalog (Aether `secrets-registry-spec` **§5**). No secret values in git.

IN: `registry.yaml`, `SECRETS.md`, `lint_registry.py` (SE-01…SE-13 report-only).

OUT: Schema-valid registry (`validate_registry.py`); lint report always exit 0.

GATE: Warden PR; **no** workflow secret enforcement, ruleset changes, or live drift jobs in B0.

Verify: `make validate`.

## §5 entry fields

| Field | Type | Notes |
|---|---|---|
| `name` | string | Canonical GitHub / runtime name (names only). |
| `type` | string \| null | Scope/type label when known; `null` if unknown. |
| `kind` | enum \| null | `app`, `pat`, `slack`, `oauth`, `api_key`, `op_sa`, `mac`, or `null`. |
| `stored_as` | enum | `secret`, `variable`, or `runtime_env`. |
| `github` | array | One object per storage location (N5 duplicates → multiple elements). |
| `onepassword_item` | string \| null | Cris-named 1Password item; `null` = TODO. |
| `runtime_env` | string \| null | Agent/runtime env var name when not GitHub-stored. |
| `permissions` | string \| null | PAT access description (SE-05). |
| `owner_role` | string \| null | |
| `custodian` | string \| null | |
| `rotation_days` | int \| null | |
| `last_rotated` | ISO date string \| null | |
| `status` | enum | `planned`, `active`, `deprecated(until)`, `removed`, `superseded`. |
| `replaces` | string \| null | Prior registry name when rotating. |
| `expires` | string \| null | PAT expiry (SE-05). |
| `replace_with` | string \| null | Successor name (SE-05). |

### `github[]` object

| Field | Type |
|---|---|
| `scope` | `org`, `repo`, `environment`, or `box` (no GitHub secret/variable home) |
| `repos` | string[] \| null (required for `repo` scope) |
| `environment` | string \| null (for `environment` scope) |
| `visibility` | `all`, `private`, or null |

## Lint rules (all report-only, exit 0)

| ID | Summary |
|---|---|
| SE-01 | Name matches `<SCOPE>_<TYPE>[_NEXT]` or is grandfathered. |
| SE-02 | No `GH_*` / `GITHUB_*` stored names or workflow refs; not `PAT`, `BLOC_TOKEN`, `FABRIC_TOKEN`. |
| SE-03 | Every `secrets.*` / `vars.*` in vendored workflows resolves to a registry name. |
| SE-04 | `_APP_ID` → variable; `_APP_PRIVATE_KEY` → secret; never store `_INSTALLATION_TOKEN`. |
| SE-05 | Active PATs declare access (`permissions`), `expires`, and `replace_with`. |
| SE-06 | Org visibility/repos match live GitHub (audit App stub). |
| SE-07 | Environment-scoped names satisfy MR-11 (stub/warn). |
| SE-08 | Public-repo secrets read-only; consumers lack `pull_request*` triggers (stub). |
| SE-09 | Cursor `runtime_env` on manifest allow list; not matching `forbidden_patterns`. |
| SE-10 | Rotation overdue warns at 1×, fails at 2× `rotation_days` (report severity only). |
| SE-11 | Live names missing from registry → policy-drift issue (audit App stub). |
| SE-12 | Registry name set equals `SECRETS.md`. |
| SE-13 | Every `active` entry has `onepassword_item`. |

**B4 note:** `GH_READ_TOKEN` (fabric-nft) is catalogued with an SE-02 finding for remediation. **`AGENT_OPS_APP_PRIVATE_KEY` must not appear** as a stored name.
