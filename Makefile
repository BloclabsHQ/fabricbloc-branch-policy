.PHONY: validate
validate:
	python3 agent-gates/validate_canon.py
	python3 agent-gates/sync_gate_issue_link.py
	test -z "$$(git diff --name-only .github/workflows/gate-issue-link.yml 2>/dev/null)" || git diff --exit-code .github/workflows/gate-issue-link.yml
	python3 branch-name-guard/sync_embedded.py
	test -z "$$(git diff --name-only .github/workflows/branch-name-guard.yml 2>/dev/null)" || git diff --exit-code .github/workflows/branch-name-guard.yml
	bash branch-name-guard/test.sh
	python3 scripts/test_branch_name_policy.py
	bash scripts/check-agent-doc-drift.sh
	python3 agent-gates/sync_embedded_gate.py
	test -z "$$(git diff --name-only .github/workflows/agent-denied-paths.yml .github/workflows/agent-review-of-record.yml 2>/dev/null)" || git diff --exit-code .github/workflows/agent-denied-paths.yml .github/workflows/agent-review-of-record.yml
	python3 agent-gates/test.py
	python3 agent-gates/test_reviewer_routing.py
	python3 agent-gates/test_issue_link.py
	python3 hygiene/sync_embedded_hygiene.py
	test -z "$$(git diff --name-only .github/workflows/hygiene-*.yml 2>/dev/null)" || git diff --exit-code .github/workflows/hygiene-*.yml
	python3 -m unittest discover -s hygiene -p 'test_*.py'
	python3 domains/04-cursor/validate_cloud_sessions.py
	python3 -m unittest discover -s domains/04-cursor/tests -p 'test_*.py'
	python3 domains/05-secrets/validate_registry.py
	python3 -m unittest discover -s domains/05-secrets/tests -p 'test_*.py'
	python3 -m unittest discover -s domains/06-funds-custody/tests -p 'test_*.py'
	python3 scripts/validate_policy_index.py
	python3 -m unittest discover -s scripts -p 'test_*.py'
	python3 -m unittest discover -s domains/02-merge-rulesets/env-drift/tests -p 'test_*.py'
