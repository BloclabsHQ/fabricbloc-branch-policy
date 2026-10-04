#!/usr/bin/env python3
"""Validate registry.yaml schema and static SE-* rules (fails CI on error)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from registry_lint import REGISTRY, format_report, static_findings  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "secrets-registry.schema.json"


def main() -> int:
    try:
        import jsonschema
    except ImportError:
        print("jsonschema required (pip install jsonschema)", file=sys.stderr)
        return 1

    data = yaml.safe_load(REGISTRY.read_text())
    schema = json.loads(SCHEMA.read_text())
    v = jsonschema.Draft202012Validator(schema)
    schema_errs = sorted(v.iter_errors(data), key=lambda e: e.path)
    for e in schema_errs:
        print(f"schema: {e.message} at {list(e.path)}")

    findings = static_findings(data)
    static = [f for f in findings if f.rule not in ("SE-06", "SE-11")]
    if static:
        print(format_report(static))

    bad = bool(schema_errs or static)
    if not bad:
        print(f"OK {REGISTRY.relative_to(ROOT)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
