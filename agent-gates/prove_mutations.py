#!/usr/bin/env python3
"""One-shot proof that canon/gate mutations fail contract tests. Run from repo root."""
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent-gates"))
import test as t  # noqa: E402

CANON_PATH = ROOT / "rulesets" / "canon.json"
GATE_PATH = ROOT / "agent-gates" / "embedded_gate.py"
VALIDATE_CANON_PATH = ROOT / "agent-gates" / "validate_canon.py"


def creation_restricted(c):
    return next(r for r in c["repository_rulesets"] if r["name"] == "canon-branch-creation-restricted")


def deploy_human_only(c):
    return next(r for r in c["repository_rulesets"] if r["name"] == "canon-deploy-branches-human-only")


def run_tests(pattern):
    p = subprocess.run(
        [sys.executable, str(ROOT / "agent-gates" / "test.py"), "-k", pattern],
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stdout + p.stderr


def main():
    rows = []
    orig_canon = CANON_PATH.read_text()
    orig_gate = GATE_PATH.read_text()

    def check_creation(c):
        t.assert_creation_restricted_shape(c)

    def check_deploy(c):
        t.assert_deploy_human_only_shape(c)

    mutations = [
        ("Add refs/heads/** to creation-restricted exclude",
         lambda c: creation_restricted(c)["conditions"]["ref_name"]["exclude"].append("refs/heads/**"),
         check_creation,
         "test_mutation_creation_restricted_exclude_refs_heads_glob"),
        ("Remove refs/heads/** from creation-restricted include",
         lambda c: creation_restricted(c)["conditions"]["ref_name"]["include"].remove("refs/heads/**"),
         check_creation,
         "test_mutation_creation_restricted_without_include_all_heads"),
        ("Replace creation-restricted include with main only",
         lambda c: creation_restricted(c)["conditions"]["ref_name"].__setitem__(
             "include", ["refs/heads/main"]),
         check_creation,
         "test_mutation_creation_restricted_without_include_all_heads"),
        ("Set creation-restricted enforcement to disabled",
         lambda c: creation_restricted(c).__setitem__("enforcement", "disabled"),
         check_creation,
         "test_mutation_creation_restricted_enforcement_disabled"),
        ("Drop deploy ruleset update rule",
         lambda c: deploy_human_only(c).__setitem__("rules", [{"type": "creation"}]),
         check_deploy,
         "test_mutation_deploy_drops_update_rule"),
        ("Delete deploy ruleset",
         lambda c: c.__setitem__(
             "repository_rulesets",
             [r for r in c["repository_rulesets"] if r["name"] != "canon-deploy-branches-human-only"],
         ),
         check_deploy,
         "test_mutation_deploy_ruleset_missing_fails_shape"),
        ("Add OrganizationAdmin bypass to creation-restricted",
         lambda c: creation_restricted(c).__setitem__(
             "bypass_actors",
             [{"actor_id": 1, "actor_type": "OrganizationAdmin", "bypass_mode": "always"}],
         ),
         check_creation,
         "test_mutation_creation_bypass_actor_added"),
    ]

    for label, mut, check, test_name in mutations:
        c = copy.deepcopy(json.loads(orig_canon))
        mut(c)
        CANON_PATH.write_text(json.dumps(c, indent=2) + "\n")
        try:
            check(c)
            rows.append((label, test_name, "ERROR: shape check passed"))
        except (AssertionError, StopIteration):
            rows.append((label, test_name, "fail"))
        finally:
            CANON_PATH.write_text(orig_canon)

    gate_mutations = [
        ("Base check uses startswith('main') instead of exact main",
         lambda s: s.replace(
             "    if base_ref == DEFAULT_BASE_REF:\n        return True",
             "    if base_ref.startswith(\"main\"):\n        return True",
         ),
         "test_mutation_base_check_startswith_main_would_miss_release"),
        ("Remove PR author leg from agent_identity_reasons",
         lambda s: re.sub(
             r'    if author_type == "Bot" or is_agent\(login=author, user_id=author_id\):\n'
             r'        why.append\(f"agent PR author \{author\}"\)\n',
             "",
             s,
             count=1,
         ),
         "test_mutation_removing_author_leg_misses_base_rule"),
        ("Lineage ignores PRs whose author type is Bot",
         lambda s: s.replace(') or user.get("type") == "Bot"', ")", 1),
         "test_mutation_lineage_ignores_bot_author_type"),
        ("Commits/pulls skips fail-closed on bad API shape",
         lambda s: s.replace(
             "    pulls = paginate(path, MAX_COMMIT_PULLS, fail_at_cap=True)",
             "    pulls = call(path)\n    if not isinstance(pulls, list):\n        return False",
             1,
         ).replace(
             "    for p in pulls:\n"
             "        if not isinstance(p, dict):\n"
             "            fail(f\"unexpected API shape for commits/{commit_sha[:12]}/pulls entry\")\n"
             "        head = p.get(\"head\")\n"
             "        if not isinstance(head, dict) or \"ref\" not in head:\n"
             "            fail(f\"commits/{commit_sha[:12]}/pulls entry missing head.ref; failing closed\")\n",
             "",
             1,
         ),
         "test_mutation_commit_pulls_bad_shape_passes_human_skip"),
        ("Co-authored-by match is case-sensitive on trailer prefix",
         lambda s: s.replace(
             'COAUTHOR_TRAILER_RE = re.compile(r"^Co-authored-by:\\s*(.+)$", re.MULTILINE | re.IGNORECASE)',
             'COAUTHOR_TRAILER_RE = re.compile(r"^Co-authored-by:\\s*(.+)$", re.MULTILINE)',
             1,
         ),
         "test_mutation_coauthor_case_sensitive_trailer"),
        ("Only the first Co-authored-by trailer is scanned",
         lambda s: s.replace(
             "    for trailer in COAUTHOR_TRAILER_RE.findall(message):\n"
             "        if _coauthor_trailer_agent(trailer):\n"
             "            return True\n"
             "    return False",
             "    m = COAUTHOR_TRAILER_RE.search(message)\n"
             "    return bool(m and _coauthor_trailer_agent(m.group(1)))",
             1,
         ),
         "test_mutation_coauthor_only_first_trailer"),
        ("Lineage continues at commits/pulls pagination cap",
         lambda s: s.replace(
             "pulls = paginate(path, MAX_COMMIT_PULLS, fail_at_cap=True)",
             "pulls = paginate(path, MAX_COMMIT_PULLS)",
             1,
         ),
         "test_mutation_commit_pulls_continues_at_cap_passes_human_skip"),
    ]
    for label, mut, test_name in gate_mutations:
        GATE_PATH.write_text(mut(orig_gate))
        subprocess.run([sys.executable, str(ROOT / "agent-gates" / "sync_embedded_gate.py")], check=True)
        code, _ = run_tests(test_name)
        rows.append((label, test_name, "fail" if code != 0 else "ERROR: test passed"))
        GATE_PATH.write_text(orig_gate)
        subprocess.run([sys.executable, str(ROOT / "agent-gates" / "sync_embedded_gate.py")], check=True)

    orig_validate = VALIDATE_CANON_PATH.read_text()
    validate_mutations = [
        ("Live ref include check loosened to subset only",
         lambda s: s.replace(
             '        if list(inc) != list(LIVE_REF_INCLUDE):',
             '        if set(LIVE_REF_INCLUDE) - set(inc):',
         ),
         "test_mutation_validate_canon_live_ref_loosened"),
    ]
    for label, mut, test_name in validate_mutations:
        VALIDATE_CANON_PATH.write_text(mut(orig_validate))
        code, _ = run_tests(test_name)
        rows.append((label, test_name, "fail" if code != 0 else "ERROR: test passed"))
        VALIDATE_CANON_PATH.write_text(orig_validate)

    print("| Mutation | Contract test | Result |")
    print("|---|---|---|")
    for label, test_name, result in rows:
        print(f"| {label} | `{test_name}` | {result} |")


if __name__ == "__main__":
    main()
