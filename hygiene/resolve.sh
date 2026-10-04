#!/usr/bin/env bash
# Merge origin/main into a hygiene stack branch (MadAgentPM rules).
set -euo pipefail
BR="${1:?branch suffix c2|c3|c4|c5|c6}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BRANCH="agent/session/feat/warden-hygiene-${BR}"

git checkout "$BRANCH"
git fetch origin main

BR_CANON="$(mktemp)"
git show "HEAD:rulesets/canon.json" >"$BR_CANON"
MAIN_CANON="$(mktemp)"
git show "origin/main:rulesets/canon.json" >"$MAIN_CANON"

MERGE_MSG="merge origin/main after C1 squash (#27)"
if ! git merge origin/main -m "$MERGE_MSG"; then
  git checkout --theirs -- .github/workflows/hygiene-pr-ops-notify.yml hygiene/sync_embedded_hygiene.py 2>/dev/null \
    || git checkout origin/main -- .github/workflows/hygiene-pr-ops-notify.yml hygiene/sync_embedded_hygiene.py

  if git diff --name-only --diff-filter=U | grep -q 'hygiene/test_contract.py'; then
    git checkout --ours -- hygiene/test_contract.py
  fi
  if git diff --name-only --diff-filter=U | grep -q 'hygiene/README.md'; then
    git checkout --ours -- hygiene/README.md
  fi

  python3 hygiene/merge_contract_tests.py

  if [ -n "$(git diff --name-only --diff-filter=U)" ]; then
    echo "Unresolved conflicts:" >&2
    git diff --name-only --diff-filter=U >&2
    exit 1
  fi
fi

git checkout origin/main -- .github/workflows/hygiene-pr-ops-notify.yml hygiene/sync_embedded_hygiene.py

python3 hygiene/canon_fix.py "$MAIN_CANON" "$BR_CANON"
python3 hygiene/merge_contract_tests.py
python3 hygiene/sync_embedded_hygiene.py

git add rulesets/canon.json .github/workflows/hygiene-pr-ops-notify.yml hygiene/sync_embedded_hygiene.py hygiene/test_contract.py hygiene/README.md 2>/dev/null || true
git add -u

if [ -f .git/MERGE_HEAD ]; then
  git commit --no-edit
elif ! git diff --cached --quiet; then
  git commit -m "chore(hygiene): apply main C1 workflow and canon pin after merge"
fi

make validate
