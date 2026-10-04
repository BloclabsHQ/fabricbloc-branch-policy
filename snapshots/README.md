# Policy audit snapshots

The workflow `.github/workflows/fabricbloc-policy-audit.yml` runs daily (and on
`workflow_dispatch`) as the **fabricbloc-policy-audit** GitHub App. It fetches
live org/repo rulesets and org App installations, normalizes the JSON (sorted
keys, volatile fields stripped), and compares the result to the committed files
in this directory.

**This job never pushes commits.** When live GitHub settings change on purpose,
download the `policy-audit-live-snapshot` artifact (or run the workflow once),
split the sections into the files below, and commit them in a human PR.

| File | Contents |
|---|---|
| `organization_rulesets.json` | `GET /orgs/BloclabsHQ/rulesets` (+ per-id detail) |
| `repository_rulesets_fabricbloc.json` | fabricbloc repo rulesets |
| `repository_rulesets_fabric-iac.json` | fabric-iac repo rulesets |
| `repository_rulesets_fabricbloc-branch-policy.json` | this repo's rulesets |
| `org_app_installations.json` | org installations (slug, permissions, events, repo selection) |

Placeholders are empty objects (`{}` or `[]`) until the first successful audit
run populates them. Drift fails the workflow with a unified diff.
