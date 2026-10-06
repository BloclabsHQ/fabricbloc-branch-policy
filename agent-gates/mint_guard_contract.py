"""Structural contracts for reviewer-app-auto-approve (mint) guards. Used by mutation tests."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows" / "agent-review-of-record.yml"
EMBED = Path(__file__).resolve().parent / "embedded_gate.py"

MINT_TIMEOUT_MINUTES_MAX = 10
MINT_WAIT_BUDGET_DEFAULT = "240"
REVIEWER_APP_USER_ID = 337673700


def load_ror_workflow_text():
    return WF.read_text()


def load_ror_workflow_doc(yaml):
    return yaml.safe_load(load_ror_workflow_text())


def mint_job(doc):
    job = (doc.get("jobs") or {}).get("reviewer-app-auto-approve")
    if not job:
        raise AssertionError("missing reviewer-app-auto-approve job")
    return job


def assert_concurrency_per_pr(doc):
    mint = mint_job(doc)
    conc = mint.get("concurrency") or {}
    if conc.get("cancel-in-progress") is not False:
        raise AssertionError("mint concurrency must set cancel-in-progress: false")
    group = str(conc.get("group") or "")
    if "github.repository" not in group:
        raise AssertionError("mint concurrency group must include github.repository")
    if "github.event.pull_request.number" not in group:
        raise AssertionError("mint concurrency group must include github.event.pull_request.number")
    if "issue.number" in group:
        raise AssertionError("mint concurrency must not key on issue.number")


def assert_mint_timeout_upper_bound(doc):
    mint = mint_job(doc)
    tm = int(mint.get("timeout-minutes") or 0)
    if tm < 1 or tm > MINT_TIMEOUT_MINUTES_MAX:
        raise AssertionError(
            f"mint timeout-minutes must be 1..{MINT_TIMEOUT_MINUTES_MAX}, got {tm!r}"
        )


def assert_mint_permissions_pinned(doc):
    mint = mint_job(doc)
    perms = mint.get("permissions") or {}
    expected = {
        "contents": "read",
        "pull-requests": "read",
        "issues": "write",
        "checks": "read",
    }
    for key, val in expected.items():
        if perms.get(key) != val:
            raise AssertionError(f"mint permissions[{key!r}] must be {val!r}, got {perms.get(key)!r}")
    if perms.get("contents") == "write":
        raise AssertionError("mint must not grant contents: write on GITHUB_TOKEN")


def assert_mint_env_budget_default(doc):
    mint = mint_job(doc)
    steps = mint.get("steps") or []
    mint_step = next(
        (s for s in steps if (s.get("env") or {}).get("ROR_JOB") == "mint"),
        None,
    )
    if mint_step is None:
        raise AssertionError("no mint step with ROR_JOB=mint")
    env = mint_step.get("env") or {}
    if env.get("ROR_MINT_WAIT_BUDGET_SEC") != MINT_WAIT_BUDGET_DEFAULT:
        raise AssertionError(
            f"ROR_MINT_WAIT_BUDGET_SEC must default to {MINT_WAIT_BUDGET_DEFAULT!r}"
        )


def embedded_text():
    return EMBED.read_text()


def assert_main_calls_enforce_mint_pr_eligible(text):
    if "if ror_job == \"mint\":" not in text:
        raise AssertionError("mint branch missing in main()")
    block = text.split('if ror_job == "mint":', 1)[1].split("\n    if ror_job", 1)[0]
    if "enforce_mint_pr_eligible(pr)" not in block:
        raise AssertionError("mint path must call enforce_mint_pr_eligible(pr)")


def assert_head_guard_before_approve(text):
    if "def mint_live_head_or_fail" not in text:
        raise AssertionError("mint_live_head_or_fail missing")
    if "guard_head" not in text or "mint_live_head_or_fail(number, head)" not in text:
        raise AssertionError("submit path must re-check head via mint_live_head_or_fail")


def assert_approve_only_via_if_needed(text):
    calls = [
        i
        for i, line in enumerate(text.splitlines(), 1)
        if "submit_reviewer_app_approve(" in line
        and "def submit_reviewer_app_approve" not in line
    ]
    if len(calls) != 1:
        raise AssertionError(
            f"submit_reviewer_app_approve must be called only from if_needed (found {len(calls)} calls)"
        )
    if "def submit_reviewer_app_approve_if_needed" not in text:
        raise AssertionError("submit_reviewer_app_approve_if_needed missing")


def assert_dedupe_checks_id_and_head(text):
    fn = text.split("def reviewer_app_already_approved_at_head", 1)[1].split("\ndef ", 1)[0]
    if "commit_id" not in fn:
        raise AssertionError("dedupe must match commit_id at head")
    if "and uid == bot_id" not in fn:
        raise AssertionError("dedupe must require numeric App user id, not login alone")


def assert_empty_live_head_fails_during_poll(text):
    if "live PR head SHA empty during mint wait" not in text:
        raise AssertionError("poll must fail closed on empty live head")


def assert_no_ror_combined(text):
    if re.search(r'ror_job not in \("gate", "mint", "combined"\)', text):
        raise AssertionError("combined must be removed from ROR_JOB allowlist")
    if re.search(r'or "combined"\)', text):
        raise AssertionError("ROR_JOB=combined must not be supported")
    if "run_reviewer_automation()" in text.split("if ror_job == \"gate\":", 1)[-1].split("if ror_job == \"mint\":", 1)[0]:
        raise AssertionError("gate path must not fall back to reviewer automation (combined mode)")


def assert_newest_check_run_by_id(text):
    fn = text.split("def _newest_github_actions_agent_denied_paths_run", 1)[1].split("\ndef ", 1)[0]
    if "started_at" in fn.split("sort", 1)[-1]:
        raise AssertionError("newest agent-denied-paths run must be selected by id, not started_at")
    if ".get(\"id\")" not in fn:
        raise AssertionError("newest run sort must use check run id")
