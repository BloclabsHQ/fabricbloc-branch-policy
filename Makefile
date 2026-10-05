.PHONY: validate
validate:
	python3 agent-gates/validate_canon.py
	python3 agent-gates/test.py
	python3 agent-gates/test_reviewer_routing.py
	python3 hygiene/sync_embedded_hygiene.py
	test -z "$$(git diff --name-only .github/workflows/hygiene-*.yml 2>/dev/null)" || git diff --exit-code .github/workflows/hygiene-*.yml
	python3 -m unittest discover -s hygiene -p 'test_*.py'
	python3 domains/04-cursor/validate_cloud_sessions.py
	python3 -m unittest discover -s domains/04-cursor/tests -p 'test_*.py'
	python3 domains/05-secrets/validate_registry.py
	python3 -m unittest discover -s domains/05-secrets/tests -p 'test_*.py'
	python3 scripts/validate_policy_index.py
	python3 -m unittest discover -s scripts -p 'test_*.py'
	python3 -m unittest discover -s domains/02-merge-rulesets/env-drift/tests -p 'test_*.py'
