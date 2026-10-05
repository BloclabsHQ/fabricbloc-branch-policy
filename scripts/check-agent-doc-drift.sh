#!/usr/bin/env bash
# Drift guard: GOV-0022 / AGENT_RUNTIME literals stay aligned across pinned consumers.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

need() {
  local file="$1"
  shift
  local text
  text="$(cat "$file")"
  for literal in "$@"; do
    if [[ "$text" != *"$literal"* ]]; then
      echo "check-agent-doc-drift: missing ${literal@Q} in $file" >&2
      exit 1
    fi
  done
}

need "README.md" "GOV-0022" "branch-name-guard"
need "branch-name-guard/README.md" "GOV-0022" "BR-01"
need "scripts/branch-name-policy.py" "GOV-0022" "agent/(session|autonomous)"

for wf in branch-name-guard agent-denied-paths agent-review-of-record gate-issue-link hygiene-auto-merge hygiene-branch-prune; do
  path=".github/workflows/${wf}.yml"
  if [[ -f "$path" ]]; then
    need "$path" "runs-on: ubuntu-latest"
  fi
done

if [[ -f domains/04-cursor/cloud-sessions.yaml ]]; then
  need "domains/04-cursor/cloud-sessions.yaml" "session_branch_regex" "bot_branch_regex"
fi

echo "check-agent-doc-drift: OK"
