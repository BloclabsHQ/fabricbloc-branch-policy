#!/usr/bin/env bash
# M6 probe (finding c): read-only checks after org ruleset + gate changes land.
# Expected:
#   (i) An agent creating a fresh branch outside main, agent/**, or GOV-0022
#       handle/<type>/<slug> is rejected by repo ruleset canon-branch-creation-restricted
#       (manual push probe; this script does not push).
#   (ii) An agent/** PR with base refs/heads/release/** (or prod/**) still runs the
#        pinned org gates and stays red (or fails with "agent PRs must target main"
#        once the gate SHA is re-pinned).
set -euo pipefail

ORG="${ORG:-BloclabsHQ}"
REPO="${REPO:-fabricbloc}"
PR="${PR:?set PR to the agent PR number to inspect}"
RULESET_ID="${RULESET_ID:-24445414}"

echo "M6 probe (finding c): PR #${PR} on ${ORG}/${REPO} (org ruleset ${RULESET_ID})"
echo ""
echo "Manual (i): as an attended agent, try to push a new branch such as"
echo "  probe/ungated-base-$(date +%s)  (not main, not agent/**, not <handle>/<type>/<slug>)."
echo "  Expect: push rejected by canon-branch-creation-restricted (ruleset B)."
echo ""

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

if [[ "${base_ref}" == "main" ]]; then
  echo "warn: base is main; for (ii) retarget the PR to release/** or prod/** first" >&2
elif [[ "${base_ref}" =~ ^release/ ]] || [[ "${base_ref}" =~ ^prod/ ]]; then
  echo "base matches release/** or prod/** — checking pinned gate checks (ii)"
else
  echo "warn: base ${base_ref} is not release/** or prod/**; org canon-agent-gates may not apply until scope includes this ref" >&2
fi

checks="$(gh api "/repos/${ORG}/${REPO}/commits/${head_sha}/check-runs" --paginate \
  -q '.check_runs[] | select(.name=="agent-review-of-record" or .name=="agent-denied-paths") | "\(.name)\t\(.conclusion)\t\(.status)\t\(.output.title // "")\t\(.details_url)"')"

if [[ -z "${checks}" ]]; then
  echo "error: no agent-denied-paths or agent-review-of-record check runs on head commit (retarget gap or missing re-pin)" >&2
  exit 1
fi

echo "required gate check runs:"
echo "${checks}"

failed=0
while IFS=$'\t' read -r name conclusion status title url; do
  if [[ "${conclusion}" == "success" ]]; then
    echo "error: ${name} is green (${url}); M6 (ii) expects agent PR to stay red on gated base" >&2
    failed=1
  fi
  if [[ "${conclusion}" == "failure" && "${title}" == *"agent PRs must target main"* ]]; then
    echo "ok: ${name} failed closed with base!=main gate rule"
  fi
done <<<"${checks}"

if [[ "${failed}" -ne 0 ]]; then
  exit 1
fi

echo "M6 probe (ii) passed: agent gate checks are not success on head ${head_sha:0:12}"
