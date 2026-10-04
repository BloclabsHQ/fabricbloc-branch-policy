# 05-secrets contract (Sentinel B0)

Job: Canonical **names-only** catalog of FabricBloc GitHub Actions secrets/variables (Aether `secrets-registry-spec` §5). No secret values in git.

IN: `registry.yaml`; vendored workflow name list; static lint rules SE-01, SE-02, SE-04, SE-05, SE-08, SE-12, SE-13.

OUT: Schema-valid registry; `lint_registry.py` report (always exit 0); `validate_registry.py` fails CI on schema/contract breaks.

GATE: Warden PR; **no** new workflow secrets, ruleset changes, or live enforcement in B0.

ESC: Warden → Cris (1Password `onepassword_item` links).

Verify: `make validate` (`validate_registry.py` + `domains/05-secrets/tests/`).

## §5 entry fields

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Canonical GitHub secret or variable name (names only). |
| `status` | yes | `live`, `deprecated`, or `planned`. |
| `github_locations` | yes | Where the name is stored (scope + kind; never values). |
| `onepassword_item` | yes | 1Password item id/title; `null` with `TODO(Cris)` in `notes` until linked. |
| `notes` | yes | Human context; deprecation, N5 duplicates, override semantics. |
| `intentional_duplicate` | no | `true` when the same name is intentionally stored in multiple scopes (N5). |
| `duplicate_policy` | no | e.g. `N5` when `intentional_duplicate` is set. |

### `github_locations[]`

| Field | Required | Meaning |
|---|---|---|
| `scope` | yes | `org`, `repo`, or `environment`. |
| `repo` | if `scope` is `repo` | `Owner/name` repository. |
| `visibility` | if `scope` is `org` | `all` or `private`. |
| `kind` | no (default `actions_secret`) | `actions_secret`, `actions_variable`, or `environment_secret`. |
| `overrides_org` | no | Repo copy overrides org default (same name). |

## Lint rules (B0)

| ID | B0 mode | Summary |
|---|---|---|
| SE-01 | static | Unique `name` per entry. |
| SE-02 | static | Names match `^[A-Z][A-Z0-9_]+$`. |
| SE-04 | static | `repo` scope requires `repo`; `org` requires `visibility`; repo secrets are not `environment_secret`. |
| SE-05 | static | `status` is valid; `deprecated`/`planned` entries include non-empty `notes`. |
| SE-06 | **stub** | Live GitHub names match registry (needs names-only audit App). |
| SE-08 | static | Org locations declare `visibility`. |
| SE-11 | **stub** | Undeclared cross-scope duplicates (needs names-only audit App). |
| SE-12 | static | Vendored workflow secret names ⊆ registry names. |
| SE-13 | static | `onepassword_item: null` ⇒ `notes` contains `TODO(Cris)`. |

`lint_registry.py` is **report-only** (always exit 0; prints rule id + names). `validate_registry.py` enforces schema and the same static checks with non-zero exit.
