#!/usr/bin/env python3
"""Report-only SE-* lint for registry.yaml (names only; never values)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

DOMAIN = Path(__file__).resolve().parent
REGISTRY = DOMAIN / "registry.yaml"
SECRETS_MD = DOMAIN / "SECRETS.md"
GRANDFATHER = DOMAIN / "grandfathered_names.txt"
CURSOR_MANIFEST = DOMAIN / "cursor_env_manifest.yaml"
WORKFLOWS = DOMAIN.parents[1] / ".github" / "workflows"

SE01_RE = re.compile(r"^[A-Z][A-Z0-9]*_[A-Z0-9]+(_NEXT)?$")
FORBIDDEN_REF_NAMES = frozenset({"PAT", "BLOC_TOKEN", "FABRIC_TOKEN"})
FORBIDDEN_STORED = frozenset({"AGENT_OPS_APP_PRIVATE_KEY"})


@dataclass(frozen=True)
class Finding:
    rule: str
    message: str
    names: tuple[str, ...] = ()


def _load_lines(path: Path) -> set[str]:
    out: set[str] = set()
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def _registry_names(data: dict) -> set[str]:
    return {e["name"] for e in data.get("entries") or [] if e.get("name")}


def _parse_secrets_md() -> set[str]:
    names: set[str] = set()
    for line in SECRETS_MD.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.replace("_", "").isalnum():
            names.add(line)
    return names


def _scan_workflow_refs() -> list[tuple[str, str, str]]:
    """Return (workflow_file, kind secrets|vars, name)."""
    refs: list[tuple[str, str, str]] = []
    if not WORKFLOWS.is_dir():
        return refs
    pat = re.compile(r"\$\{\{\s*(secrets|vars)\.([A-Za-z0-9_]+)")
    for wf in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        text = wf.read_text()
        for kind, name in pat.findall(text):
            refs.append((wf.name, kind, name))
    return refs


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def lint_all(data: dict) -> list[Finding]:
    findings: list[Finding] = []
    entries = data.get("entries") or []
    names = _registry_names(data)
    grandfather = _load_lines(GRANDFATHER)

    for forbidden in FORBIDDEN_STORED:
        if forbidden in names:
            findings.append(Finding("SE-04", "forbidden stored name", (forbidden,)))

    for entry in entries:
        name = entry.get("name") or ""

        if name not in grandfather and not SE01_RE.match(name):
            findings.append(Finding("SE-01", "name not SCOPE_TYPE[_NEXT] and not grandfathered", (name,)))

        if name.startswith("GH_") or name.startswith("GITHUB_"):
            findings.append(Finding("SE-02", "forbidden GH_/GITHUB_ prefix on stored name", (name,)))
        if name in FORBIDDEN_REF_NAMES:
            findings.append(Finding("SE-02", "forbidden bare token name", (name,)))

        if name.endswith("_INSTALLATION_TOKEN"):
            findings.append(Finding("SE-04", "_INSTALLATION_TOKEN must never be stored", (name,)))
        if name.endswith("_APP_ID") and entry.get("stored_as") != "variable":
            findings.append(Finding("SE-04", "_APP_ID must be stored_as variable", (name,)))
        if name.endswith("_APP_PRIVATE_KEY") and entry.get("stored_as") != "secret":
            findings.append(Finding("SE-04", "_APP_PRIVATE_KEY must be stored_as secret", (name,)))

        if entry.get("kind") == "pat" and entry.get("status") == "active":
            if not entry.get("permissions"):
                findings.append(Finding("SE-05", "active PAT missing permissions (access description)", (name,)))
            if not entry.get("expires"):
                findings.append(Finding("SE-05", "active PAT missing expires", (name,)))
            if not entry.get("replace_with"):
                findings.append(Finding("SE-05", "active PAT missing replace_with", (name,)))

        if entry.get("status") == "active" and not entry.get("onepassword_item"):
            findings.append(Finding("SE-13", "active entry missing onepassword_item", (name,)))

        rot = entry.get("rotation_days")
        last = _parse_date(entry.get("last_rotated"))
        if rot and last:
            age = (date.today() - last).days
            if age > rot * 2:
                findings.append(Finding("SE-10", "rotation overdue fail (2x)", (name,)))
            elif age > rot:
                findings.append(Finding("SE-10", "rotation overdue warn (1x)", (name,)))

        runtime = entry.get("runtime_env")
        if runtime:
            manifest = yaml.safe_load(CURSOR_MANIFEST.read_text())
            allowed = set(manifest.get("allowed") or [])
            forbidden = [re.compile(p) for p in manifest.get("forbidden_patterns") or []]
            if runtime not in allowed:
                findings.append(Finding("SE-09", "runtime_env not on Cursor manifest allowed list", (runtime,)))
            for pat in forbidden:
                if pat.search(runtime):
                    findings.append(Finding("SE-09", "runtime_env matches forbidden pattern", (runtime,)))

        for loc in entry.get("github") or []:
            if loc.get("scope") == "environment" and loc.get("environment"):
                findings.append(
                    Finding(
                        "SE-07",
                        "environment-scoped name (MR-11 check stub: verify agent-ops env policy)",
                        (name,),
                    )
                )

    secrets_md = _parse_secrets_md()
    if secrets_md != names:
        only_reg = names - secrets_md
        only_md = secrets_md - names
        for n in sorted(only_reg):
            findings.append(Finding("SE-12", "in registry but not SECRETS.md", (n,)))
        for n in sorted(only_md):
            findings.append(Finding("SE-12", "in SECRETS.md but not registry", (n,)))

    for wf, kind, ref in _scan_workflow_refs():
        if ref.startswith("GH_") or ref.startswith("GITHUB_"):
            findings.append(Finding("SE-02", f"forbidden {kind} reference in workflow", (ref,)))
        if ref in FORBIDDEN_REF_NAMES:
            findings.append(Finding("SE-02", f"forbidden {kind} reference in workflow", (ref,)))
        if ref not in names:
            findings.append(Finding("SE-03", f"{kind} reference not in registry ({wf})", (ref,)))

    if names & {"GH_READ_TOKEN"}:
        findings.append(
            Finding("SE-02", "B4: GH_READ_TOKEN stored name violates GH_* policy (fabric-nft)", ("GH_READ_TOKEN",))
        )

    findings.append(Finding("SE-06", "SKIP: org visibility/repos vs live GitHub (names-only audit App)", ()))
    findings.append(Finding("SE-08", "SKIP: public-repo read-only + consumer pull_request triggers", ()))
    findings.append(Finding("SE-11", "SKIP: live GitHub names missing from registry (policy-drift issue)", ()))

    for rid in (f"SE-{i:02d}" for i in range(1, 14)):
        if not any(f.rule == rid for f in findings):
            findings.append(Finding(rid, "OK", ()))

    return findings


def format_report(findings: list[Finding]) -> str:
    lines: list[str] = []
    for f in findings:
        suffix = f" names={','.join(f.names)}" if f.names else ""
        lines.append(f"{f.rule}: {f.message}{suffix}")
    return "\n".join(lines)
