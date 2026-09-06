# Rulesets

This directory will hold the declared branch-protection ruleset for each
repository class defined in
[FabricBloc GOV-0032](https://github.com/BloclabsHQ/fabricbloc/blob/main/decisions/GOV-0032-merge-and-branch-permissions.md)
(canon, infrastructure, service, tool) as one `rulesets/<class>.json` file per
class, applied to every repository in scope by a workflow using the GitHub
rulesets API — never edited by hand in the GitHub UI.

The ruleset files, the apply workflow, and the weekly drift check are a later
task's content; this directory is a placeholder until that task lands.
