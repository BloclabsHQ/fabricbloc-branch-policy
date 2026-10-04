#!/usr/bin/env bash
# M6 post re-pin probe: an agent PR retargeted to a fresh branch must stay red.
# Read-only checks via gh; never merges or pushes.
set -euo pipefail

ORG="${ORG:-BloclabsHQ}"
REPO="${REPO:-fabricbloc}"
PR="${PR:?set PR to the agent PR number to inspect}"
RULESET_ID="${RULESET_ID:-24445414}"

echo "M6 probe: PR #${PR} on ${ORG}/${REPO} (ruleset ${RULESET_ID})"

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh CLI required" >&2
  exit 1
fi

pr_json="$(gh api "/repos/${ORG}/${REPO}/pulls/${PR}")"
head_ref="$(jq -r '.head.ref' <<<"$pr_json")"
base_ref="$(jq -r '.base.ref' <<<"$pr_json")"
head_sha="$(jq -r '.head.sha' <<<"$pr_json")"

echo "head ref: ${head_ref}"
echo "base ref: ${base_ref}"
echo "head sha: ${head_sha}"

if [[ ! "${head_ref}" =~ ^agent/ ]]; then
  echo "error: expected agent/** head ref; got ${head_ref}" >&2
  exit 1
fi

checks="$(gh api "/repos/${ORG}/${REPO}/commits/${head_sha}/check-runs" --paginate \
  -q '.check_runs[] | select(.name=="agent-review-of-record" or .name=="agent-denied-paths") | "\(.name)\t\(.conclusion)\t\(.details_url)"')"

if [[ -z "${checks}" ]]; then
  echo "error: no agent-denied-paths or agent-review-of-record check runs on head commit" >&2
  exit 1
fi

echo "required gate check runs:"
echo "${checks}"

failed=0
while IFS=$'\t' read -r name conclusion url; do
  if [[ "${conclusion}" == "success" ]]; then
    echo "error: ${name} is green (${url}); M6 expects agent PR to stay red on gated base" >&2
    failed=1
  fi
done <<<"${checks}"

if [[ "${failed}" -ne 0 ]]; then
  exit 1
fi

echo "M6 probe passed: agent gate checks are not success on head ${head_sha:0:12}"
