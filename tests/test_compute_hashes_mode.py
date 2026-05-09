"""Integration test for the --compute-hashes CLI mode."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "download-plugins.py"


def _write_fixture(template_path: Path, dest_path: Path, base_url: str) -> None:
    text = template_path.read_text(encoding="utf-8").replace("MOCKURL", base_url)
    dest_path.write_text(text, encoding="utf-8")


def test_compute_hashes_in_place_populates_sha256_and_source(mock_server, fixtures_dir, tmp_path) -> None:
    mac_body = b"fake-mac-installer"
    win_body = b"fake-windows-installer"
    mock_server.add("/fakesynth-mac.dmg", mac_body)
    mock_server.add("/fakesynth-win.exe", win_body)

    json_path = tmp_path / "plugins.json"
    _write_fixture(fixtures_dir / "plugins-empty-hashes.json", json_path, mock_server.base_url)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--compute-hashes", "--in-place", "--plugins-json", str(json_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr

    data = json.loads(json_path.read_text(encoding="utf-8"))
    mac = data["plugins"]["synths"][0]["urls"]["macos"]
    win = data["plugins"]["synths"][0]["urls"]["windows"]

    assert mac["sha256"] == mock_server.sha256_of("/fakesynth-mac.dmg")
    assert mac["hash_source"] == "self"
    assert win["sha256"] == mock_server.sha256_of("/fakesynth-win.exe")
    assert win["hash_source"] == "self"


def test_compute_hashes_does_not_overwrite_existing_without_force(mock_server, fixtures_dir, tmp_path) -> None:
    mock_server.add("/fakesynth-mac.dmg", b"fake-mac")
    mock_server.add("/fakesynth-win.exe", b"fake-win")

    json_path = tmp_path / "plugins.json"
    _write_fixture(fixtures_dir / "plugins-empty-hashes.json", json_path, mock_server.base_url)

    # Pre-populate macos with a "publisher" hash that the test pretends a maintainer added.
    data = json.loads(json_path.read_text(encoding="utf-8"))
    data["plugins"]["synths"][0]["urls"]["macos"]["sha256"] = "0" * 64
    data["plugins"]["synths"][0]["urls"]["macos"]["hash_source"] = "publisher"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--compute-hashes", "--in-place", "--plugins-json", str(json_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr

    data = json.loads(json_path.read_text(encoding="utf-8"))
    mac = data["plugins"]["synths"][0]["urls"]["macos"]
    win = data["plugins"]["synths"][0]["urls"]["windows"]
    # macos preserved (publisher hash + manually set value)
    assert mac["sha256"] == "0" * 64
    assert mac["hash_source"] == "publisher"
    # windows newly populated (was missing)
    assert "sha256" in win
    assert win["hash_source"] == "self"
