#!/usr/bin/env python3
"""Static SE-* checks for domains/05-secrets/registry.yaml (names only)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")
ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).resolve().parent / "registry.yaml"
VENDORED = Path(__file__).resolve().parent / "vendored_workflow_secret_names.txt"


@dataclass(frozen=True)
class Finding:
    rule: str
    message: str
    names: tuple[str, ...] = ()


def load_vendored_names() -> set[str]:
    names: set[str] = set()
    if not VENDORED.is_file():
        return names
    for line in VENDORED.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.add(line)
    return names


def static_findings(data: dict) -> list[Finding]:
    findings: list[Finding] = []
    entries = data.get("entries") or []
    seen: dict[str, int] = {}

    for entry in entries:
        name = entry.get("name") or ""
        # SE-02
        if not NAME_RE.match(name):
            findings.append(Finding("SE-02", "invalid secret name", (name,)))

        # SE-01
        seen[name] = seen.get(name, 0) + 1

        status = entry.get("status")
        notes = (entry.get("notes") or "").strip()

        # SE-05
        if status in ("deprecated", "planned") and not notes:
            findings.append(Finding("SE-05", f"{status} entry missing notes", (name,)))

        # SE-13
        if entry.get("onepassword_item") is None and "TODO(Cris)" not in notes:
            findings.append(Finding("SE-13", "null onepassword_item requires TODO(Cris) in notes", (name,)))

        locations = entry.get("github_locations") or []
        org_count = sum(1 for loc in locations if loc.get("scope") == "org")
        repo_count = sum(1 for loc in locations if loc.get("scope") == "repo")
        if len(locations) > 1 and org_count and repo_count:
            if not entry.get("intentional_duplicate") and not any(
                loc.get("overrides_org") for loc in locations if loc.get("scope") == "repo"
            ):
                findings.append(
                    Finding(
                        "SE-04",
                        "multi-scope entry needs intentional_duplicate or overrides_org",
                        (name,),
                    )
                )

        for loc in locations:
            scope = loc.get("scope")
            kind = loc.get("kind") or "actions_secret"
            # SE-04
            if scope == "repo" and not loc.get("repo"):
                findings.append(Finding("SE-04", "repo scope missing repo", (name,)))
            if scope == "org" and loc.get("visibility") not in ("all", "private"):
                findings.append(Finding("SE-08", "org scope missing visibility", (name,)))
            if scope == "repo" and kind == "environment_secret" and name == "CURSOR_API_KEY":
                findings.append(
                    Finding("SE-04", "CURSOR_API_KEY must not be environment secret", (name,))
                )

        if entry.get("intentional_duplicate") and entry.get("duplicate_policy") != "N5":
            if org_count and repo_count and not any(loc.get("overrides_org") for loc in locations):
                findings.append(Finding("SE-04", "intentional_duplicate requires duplicate_policy N5", (name,)))

    dupes = [n for n, c in seen.items() if c > 1]
    for n in dupes:
        findings.append(Finding("SE-01", "duplicate registry name", (n,)))

    registry_names = {e.get("name") for e in entries if e.get("name")}
    for vend in load_vendored_names():
        if vend not in registry_names:
            findings.append(Finding("SE-12", "vendored workflow secret missing from registry", (vend,)))

    # SE-06 / SE-11 stubs (documented; no live API in B0)
    findings.append(
        Finding("SE-06", "SKIP: live GitHub name audit requires names-only audit App (B0 stub)", ())
    )
    findings.append(
        Finding("SE-11", "SKIP: cross-scope duplicate audit requires names-only audit App (B0 stub)", ())
    )
    return findings


def format_report(findings: list[Finding]) -> str:
    lines: list[str] = []
    for f in findings:
        suffix = f" names={','.join(f.names)}" if f.names else ""
        lines.append(f"{f.rule}: {f.message}{suffix}")
    return "\n".join(lines)
