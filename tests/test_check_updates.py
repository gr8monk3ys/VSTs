"""Tests for --check-updates and its helpers."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "download-plugins.py"
_spec = importlib.util.spec_from_file_location("dlp", SCRIPT)
dlp = importlib.util.module_from_spec(_spec)
sys.modules["dlp"] = dlp
_spec.loader.exec_module(dlp)


def _fake_release(tag: str, asset_names: list[str]) -> bytes:
    """Build a JSON body matching the GitHub API release shape."""
    return json.dumps({
        "tag_name": tag,
        "assets": [
            {"name": n, "browser_download_url": f"https://example.invalid/{n}", "size": 1234}
            for n in asset_names
        ],
    }).encode("utf-8")


def test_detect_latest_for_github_uses_latest_endpoint(mock_server) -> None:
    body = _fake_release("v1.3.5", ["Surge-XT-1.3.5-mac.dmg", "Surge-XT-1.3.5-win.exe"])
    mock_server.add("/repos/surge-synthesizer/releases-xt/releases/latest", body)

    result = dlp.detect_latest_for_github(
        "surge-synthesizer/releases-xt",
        api_base=mock_server.base_url,
    )

    assert result["tag"] == "v1.3.5"
    asset_names = sorted(a["name"] for a in result["assets"])
    assert asset_names == ["Surge-XT-1.3.5-mac.dmg", "Surge-XT-1.3.5-win.exe"]


def test_detect_latest_for_github_uses_tagged_endpoint(mock_server) -> None:
    body = _fake_release("DAWPlugin", ["airwindows-2026-06-15-abc.dmg"])
    mock_server.add("/repos/baconpaul/airwin2rack/releases/tags/DAWPlugin", body)

    result = dlp.detect_latest_for_github(
        "baconpaul/airwin2rack",
        tag="DAWPlugin",
        api_base=mock_server.base_url,
    )

    assert result["tag"] == "DAWPlugin"
    assert len(result["assets"]) == 1
    assert result["assets"][0]["name"] == "airwindows-2026-06-15-abc.dmg"
    assert result["assets"][0]["url"] == "https://example.invalid/airwindows-2026-06-15-abc.dmg"
