# fabricbloc-branch-policy router

Policy-as-code for FabricBloc org gates and fleet rules. **Cite rule IDs from [POLICY_INDEX.md](POLICY_INDEX.md); never copy rule text into consumers.**

## Domains

| Domain | Path | IDs |
|---|---|---|
| Branches | `domains/01-branches/` | BR-* |
| Merge rulesets | `domains/02-merge-rulesets/` | MR-* |
| Agent gates | `domains/03-agent-gates/` | AG-* |
| Cursor cloud | `domains/04-cursor/` | CU-* |

## Validate

```bash
make validate
```

Harnesses and session economy code consume pinned SHAs of this repo; they do not fork rule prose.
