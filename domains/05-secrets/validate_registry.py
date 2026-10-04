#!/usr/bin/env python3
"""Validate registry.yaml against §5 JSON Schema only (CI gate)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).resolve().parent / "registry.yaml"
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
    if schema_errs:
        return 1
    print(f"OK {REGISTRY.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
