#!/usr/bin/env python3
"""Report-only secrets registry lint (always exit 0; names only, never values)."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from registry_lint import REGISTRY, format_report, static_findings  # noqa: E402


def main() -> int:
    data = yaml.safe_load(REGISTRY.read_text())
    findings = static_findings(data)
    print(format_report(findings))
    print(f"report-only: {len(findings)} finding(s); exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
