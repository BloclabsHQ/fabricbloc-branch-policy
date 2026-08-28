# FabricBloc branch policy

This public repository owns the canonical executable branch-name guard for
[FabricBloc GOV-0022](https://github.com/BloclabsHQ/fabricbloc/blob/main/decisions/GOV-0022-branch-naming-and-provider-agnostic-enforcement.md).

Consumers call [`.github/workflows/branch-name-guard.yml`](.github/workflows/branch-name-guard.yml)
as a reusable workflow at an immutable commit SHA. The same workflow declares
the pull-request trigger required when it is selected by a GitHub ruleset. It
contains no secrets and the executable grammar is defined in that file only.

Run `bash branch-name-guard/test.sh` to execute the accepted/rejected contract
matrix against the workflow's embedded validator.
