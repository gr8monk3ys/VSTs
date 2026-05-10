"""Asserts plugins.json validates against the committed JSON schema."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parents[1]


def test_plugins_json_validates_against_schema() -> None:
    schema = json.loads((REPO / "schemas" / "plugins.schema.json").read_text(encoding="utf-8"))
    data = json.loads((REPO / "plugins.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=data, schema=schema)


def test_schema_rejects_missing_sha256() -> None:
    schema = json.loads((REPO / "schemas" / "plugins.schema.json").read_text(encoding="utf-8"))
    bad = {
        "meta": {
            "name": "x", "version": "0", "description": "x",
            "updated": "2026-05-09", "author": "x", "license": "MIT",
            "platforms": ["macos"],
        },
        "plugins": {"synths": [{
            "name": "x", "description": "x",
            "urls": {"macos": {"url": "https://example.invalid/", "filename": "x"}},
            "version": "0", "formats": ["VST3"], "website": "https://example.invalid/",
            "open_source": False,
        }]},
        "manual_download": [],
    }
    with __import__("pytest").raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_schema_rejects_bad_hash_source() -> None:
    schema = json.loads((REPO / "schemas" / "plugins.schema.json").read_text(encoding="utf-8"))
    bad = {
        "meta": {
            "name": "x", "version": "0", "description": "x",
            "updated": "2026-05-09", "author": "x", "license": "MIT",
            "platforms": ["macos"],
        },
        "plugins": {"synths": [{
            "name": "x", "description": "x",
            "urls": {"macos": {
                "url": "https://example.invalid/", "filename": "x",
                "sha256": "a" * 64, "hash_source": "garbage",
            }},
            "version": "0", "formats": ["VST3"], "website": "https://example.invalid/",
            "open_source": False,
        }]},
        "manual_download": [],
    }
    with __import__("pytest").raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_schema_rejects_malformed_update_strategy() -> None:
    schema = json.loads((REPO / "schemas" / "plugins.schema.json").read_text(encoding="utf-8"))
    bad = {
        "meta": {
            "name": "x", "version": "0", "description": "x",
            "updated": "2026-05-09", "author": "x", "license": "MIT",
            "platforms": ["macos"],
        },
        "plugins": {"synths": [{
            "name": "x", "description": "x",
            "update_strategy": "not-a-valid-format",
            "urls": {"macos": {
                "url": "https://example.invalid/", "filename": "x",
                "sha256": "a" * 64, "hash_source": "self",
            }},
            "version": "0", "formats": ["VST3"], "website": "https://example.invalid/",
            "open_source": False,
        }]},
        "manual_download": [],
    }
    with __import__("pytest").raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_schema_accepts_valid_update_strategy() -> None:
    schema = json.loads((REPO / "schemas" / "plugins.schema.json").read_text(encoding="utf-8"))
    good = {
        "meta": {
            "name": "x", "version": "0", "description": "x",
            "updated": "2026-05-09", "author": "x", "license": "MIT",
            "platforms": ["macos"],
        },
        "plugins": {"synths": [{
            "name": "x", "description": "x",
            "update_strategy": "github:owner/repo",
            "urls": {"macos": {
                "url": "https://example.invalid/", "filename": "x",
                "sha256": "a" * 64, "hash_source": "self",
            }},
            "version": "0", "formats": ["VST3"], "website": "https://example.invalid/",
            "open_source": False,
        }]},
        "manual_download": [],
    }
    jsonschema.validate(instance=good, schema=schema)

    # also accepts the @tag form
    good["plugins"]["synths"][0]["update_strategy"] = "github:owner/repo@TAG_NAME"
    jsonschema.validate(instance=good, schema=schema)


def test_schema_accepts_uhe_strategy() -> None:
    schema = json.loads((REPO / "schemas" / "plugins.schema.json").read_text(encoding="utf-8"))
    good = {
        "meta": {
            "name": "x", "version": "0", "description": "x",
            "updated": "2026-05-09", "author": "x", "license": "MIT",
            "platforms": ["macos"],
        },
        "plugins": {"synths": [{
            "name": "x", "description": "x",
            "update_strategy": "u-he:TyrellN6",
            "urls": {"macos": {
                "url": "https://example.invalid/", "filename": "x",
                "sha256": "a" * 64, "hash_source": "self",
            }},
            "version": "0", "formats": ["VST3"], "website": "https://example.invalid/",
            "open_source": False,
        }]},
        "manual_download": [],
    }
    jsonschema.validate(instance=good, schema=schema)


def test_schema_rejects_uhe_strategy_with_empty_product() -> None:
    schema = json.loads((REPO / "schemas" / "plugins.schema.json").read_text(encoding="utf-8"))
    bad = {
        "meta": {
            "name": "x", "version": "0", "description": "x",
            "updated": "2026-05-09", "author": "x", "license": "MIT",
            "platforms": ["macos"],
        },
        "plugins": {"synths": [{
            "name": "x", "description": "x",
            "update_strategy": "u-he:",
            "urls": {"macos": {
                "url": "https://example.invalid/", "filename": "x",
                "sha256": "a" * 64, "hash_source": "self",
            }},
            "version": "0", "formats": ["VST3"], "website": "https://example.invalid/",
            "open_source": False,
        }]},
        "manual_download": [],
    }
    with __import__("pytest").raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)
