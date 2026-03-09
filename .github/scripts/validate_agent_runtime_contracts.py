#!/usr/bin/env python3
"""Validate agent runtime example fixtures against JSON schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = ROOT / "docs" / "specs" / "technical" / "agent-runtime" / "examples"
MANIFEST_PATH = EXAMPLES_DIR / "manifest.json"


def load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    manifest = load_json(MANIFEST_PATH)
    if not isinstance(manifest, list):
        print(f"Manifest must be a list: {MANIFEST_PATH}")
        return 1

    failures = 0

    for entry in manifest:
        fixture_path = EXAMPLES_DIR / entry["file"]
        schema_path = EXAMPLES_DIR / entry["schema"]
        expected_valid = entry["valid"]

        fixture = load_json(fixture_path)
        schema = load_json(schema_path)

        validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
        errors = sorted(validator.iter_errors(fixture), key=lambda e: list(e.path))
        actual_valid = len(errors) == 0

        if actual_valid == expected_valid:
            print(f"[PASS] {entry['file']} (expected valid={expected_valid})")
            continue

        failures += 1
        print(f"[FAIL] {entry['file']} (expected valid={expected_valid}, actual valid={actual_valid})")
        for err in errors[:5]:
            location = "/".join(str(p) for p in err.path) or "<root>"
            print(f"  - {location}: {err.message}")

    if failures:
        print(f"\nValidation failed for {failures} fixture(s).")
        return 1

    print("\nAll agent runtime fixtures matched expected validation outcomes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
