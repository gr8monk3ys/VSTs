"""Integration tests for the verifying download_file() and main() flow."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "download-plugins.py"
_spec = importlib.util.spec_from_file_location("dlp", SCRIPT)
dlp = importlib.util.module_from_spec(_spec)
sys.modules["dlp"] = dlp
_spec.loader.exec_module(dlp)


def _write_fixture(template: Path, dest: Path, base_url: str, mac_hash: str) -> None:
    text = (
        template.read_text(encoding="utf-8")
        .replace("MOCKURL", base_url)
        .replace("MAC_HASH", mac_hash)
    )
    dest.write_text(text, encoding="utf-8")


def test_download_file_verifies_correct_hash(mock_server, tmp_path) -> None:
    body = b"a-real-installer"
    url = mock_server.add("/fakesynth-mac.dmg", body)
    expected = mock_server.sha256_of("/fakesynth-mac.dmg")

    out_path = tmp_path / "fakesynth.dmg"
    ok = dlp.download_file(url, out_path, "FakeSynth", expected, "self")

    assert ok is True
    assert out_path.read_bytes() == body


def test_download_file_aborts_and_unlinks_on_mismatch(mock_server, tmp_path) -> None:
    mock_server.add("/fakesynth-mac.dmg", b"actual-content")
    bad_expected = "f" * 64

    out_path = tmp_path / "fakesynth.dmg"
    with pytest.raises(dlp.ChecksumMismatch):
        dlp.download_file(
            mock_server.url_for("/fakesynth-mac.dmg"),
            out_path,
            "FakeSynth",
            bad_expected,
            "self",
        )

    assert not out_path.exists(), "partial/bad file must be removed on mismatch"


def test_download_file_reverifies_cached_file(mock_server, tmp_path) -> None:
    body = b"a-real-installer"
    url = mock_server.add("/fakesynth-mac.dmg", body)
    expected = mock_server.sha256_of("/fakesynth-mac.dmg")

    out_path = tmp_path / "fakesynth.dmg"
    out_path.write_bytes(b"corrupted-cached-bytes")  # wrong content already on disk

    ok = dlp.download_file(url, out_path, "FakeSynth", expected, "self")

    assert ok is True
    assert out_path.read_bytes() == body, "cached bad file should have been redownloaded"


def test_main_exits_nonzero_when_any_download_mismatches(mock_server, fixtures_dir, tmp_path, monkeypatch) -> None:
    mock_server.add("/fakesynth-mac.dmg", b"actual")
    fake_plugins = tmp_path / "plugins.json"
    _write_fixture(
        fixtures_dir / "plugins-with-hashes.json",
        fake_plugins,
        mock_server.base_url,
        "f" * 64,  # deliberately wrong
    )

    download_dir = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", [
        "download-plugins.py",
        "--platform", "macos",
        "--dir", str(download_dir),
        "--plugins-json", str(fake_plugins),
        "--synths",
    ])

    with pytest.raises(SystemExit) as exc:
        dlp.main()
    assert exc.value.code != 0
    # The bad file must have been deleted.
    assert not (download_dir / "fakesynth-mac.dmg").exists()
