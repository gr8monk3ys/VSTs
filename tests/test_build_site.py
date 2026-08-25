"""Tests for the static catalog site generator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / "scripts" / "build_site.py"


def test_build_site_renders_every_plugin_and_escapes_html(tmp_path) -> None:
    manifest = {
        "meta": {"description": "Test catalog", "updated": "2026-08-25"},
        "plugins": {
            "synths": [
                {
                    "name": "Fake<Synth>",
                    "description": 'Has "quotes" & angle brackets',
                    "version": "1.0",
                    "formats": ["VST3"],
                    "open_source": True,
                    "website": "https://example.invalid/",
                    "urls": {
                        "macos": {
                            "url": "https://example.invalid/f.dmg",
                            "filename": "f.dmg",
                            "sha256": "a" * 64,
                            "hash_source": "self",
                        }
                    },
                }
            ]
        },
        "manual_download": [
            {
                "name": "ManualThing",
                "description": "grab it yourself",
                "website": "https://example.invalid/manual",
                "platforms": ["macos", "linux"],
            }
        ],
    }
    manifest_path = tmp_path / "plugins.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    out = tmp_path / "site"
    result = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--manifest",
            str(manifest_path),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    page = (out / "index.html").read_text(encoding="utf-8")
    assert "Fake&lt;Synth&gt;" in page  # escaped, not raw
    assert "<Fake" not in page
    assert "ManualThing" in page
    assert "sha256 ✓" in page
    assert "open source" in page
    assert "2026-08-25" in page


def test_build_site_renders_real_manifest(tmp_path) -> None:
    out = tmp_path / "site"
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--out", str(out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    page = (out / "index.html").read_text(encoding="utf-8")
    for expected in ("Surge XT", "Valhalla Supermassive", "Airwindows Consolidated"):
        assert expected in page
