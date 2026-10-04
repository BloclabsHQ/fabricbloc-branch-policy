.PHONY: validate
validate:
	python3 agent-gates/validate_canon.py
	python3 agent-gates/test.py
	python3 domains/04-cursor/validate_cloud_sessions.py
	python3 -m unittest discover -s domains/04-cursor/tests -p 'test_*.py'
	python3 scripts/validate_policy_index.py
