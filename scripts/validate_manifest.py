#!/usr/bin/env python3
"""Validate plugins.json: well-formed JSON + conforms to the committed schema.

Used by the CI lint job; run locally with:  python scripts/validate_manifest.py
Requires jsonschema (pip install jsonschema).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    manifest_path = REPO / "plugins.json"
    schema_path = REPO / "schemas" / "plugins.schema.json"

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"plugins.json is not valid JSON: {e}")
        return 1

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        print(
            f"plugins.json violates the schema at {list(e.absolute_path)}: {e.message}"
        )
        return 1

    print("plugins.json is valid JSON and conforms to the schema")
    return 0


if __name__ == "__main__":
    sys.exit(main())
