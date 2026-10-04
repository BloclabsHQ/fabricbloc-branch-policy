.PHONY: validate
validate:
	python3 agent-gates/validate_canon.py
	python3 agent-gates/test.py
	python3 -m unittest discover -s domains/02-merge-rulesets/env-drift/tests -p 'test_*.py'
	python3 scripts/validate_policy_index.py
