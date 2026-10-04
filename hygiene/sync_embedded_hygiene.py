#!/usr/bin/env python3
"""Embed hygiene/*.py (plus common.py) into reusable workflow heredocs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
HYGIENE = Path(__file__).resolve().parent
INDENT = "          "

# workflow stem -> script module (without .py)
WORKFLOWS = {
    "hygiene-pr-ops-notify": "pr_ops_notify",
    "hygiene-stale": "stale",
    "hygiene-auto-merge": "auto_merge",
    "hygiene-ci-red": "ci_red",
    "hygiene-branch-prune": "branch_prune",
    "hygiene-backlog-lint": "backlog_lint",
}


def embed_body(script_name):
    common = (HYGIENE / "common.py").read_text()
    script = (HYGIENE / f"{script_name}.py").read_text()
    lines = []
    for line in script.splitlines():
        if line.startswith("from common import") or line.startswith("import common"):
            continue
        lines.append(line)
    return common + "\n" + "\n".join(lines) + "\n"


def indent_block(text):
    return "\n".join(INDENT + line if line else line for line in text.splitlines())


def patch(workflow_stem, script_name):
    path = WF / f"{workflow_stem}.yml"
    if not path.exists():
        return False
    body = indent_block(embed_body(script_name))
    mark, endmark = "<<'PY'\n", "\n          PY"
    text = path.read_text()
    if mark not in text:
        return False
    out, i = [], 0
    while True:
        j = text.find(mark, i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i : j + len(mark)])
        k = text.find(endmark, j + len(mark))
        if k < 0:
            raise SystemExit(f"{path}: unclosed PY heredoc")
        out.append(body)
        i = k
    path.write_text("".join(out))
    return True


def main():
    synced = []
    for stem, script in WORKFLOWS.items():
        if patch(stem, script):
            synced.append(stem)
    print("synced", ", ".join(synced) if synced else "(none)")


if __name__ == "__main__":
    main()
