#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workflow="$root/.github/workflows/branch-name-guard.yml"
validator="$(mktemp)"
trap 'rm -f "$validator"' EXIT

ruby -ryaml -e '
  workflow = YAML.safe_load(File.read(ARGV.fetch(0)), aliases: true)
  script = workflow.dig("jobs", "guard", "steps", 0, "run")
  abort "branch-name-guard: validator run block not found" unless script
  puts script
' "$workflow" > "$validator"

run_case() {
  local expected="$1"
  local branch="$2"
  local output status

  set +e
  output="$(BRANCH="$branch" BASE_BRANCHES="main,dev,master" bash "$validator" 2>&1)"
  status=$?
  set -e

  if [[ "$expected" == pass && $status -ne 0 ]]; then
    printf 'expected PASS for %s, got %s\n%s\n' "$branch" "$status" "$output" >&2
    return 1
  fi
  if [[ "$expected" == fail && $status -eq 0 ]]; then
    printf 'expected FAIL for %s\n%s\n' "$branch" "$output" >&2
    return 1
  fi
}

accepted=(
  "main"
  "debu99/feat/identity-alignment"
  "agent/session/docs/658-branch-identity-patterns"
  "agent/autonomous/ci/fleet-branch-guard"
)

rejected=(
  "agent/atlas/docs/658-branch-identity-patterns"
  "agent/codex/docs/658-branch-identity-patterns"
  "agent/session/docs/identity"
  "codex/docs/branch-identity"
  "claude/fix/branch-identity"
  "qwen/test/branch-identity"
  "fix/branch-identity"
  "feat/658-branch-identity-patterns"
)

for branch in "${accepted[@]}"; do
  run_case pass "$branch"
done
for branch in "${rejected[@]}"; do
  run_case fail "$branch"
done

printf 'branch-name-guard contract: %d accepted, %d rejected\n' \
  "${#accepted[@]}" "${#rejected[@]}"
