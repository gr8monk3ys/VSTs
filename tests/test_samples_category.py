"""The opt-in `samples` category: skipped by a plain run, fetched with --samples."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from free_vst_plugins import cli as dlp


def _manifest(base_url: str, synth_hash: str, lib_hash: str) -> dict:
    def entry(name: str, digest: str) -> dict:
        return {
            "url": f"{base_url}/{name}",
            "filename": name,
            "sha256": digest,
            "hash_source": "self",
        }

    return {
        "meta": {
            "name": "Test Fixture",
            "version": "0.0.0",
            "description": "synth + sample library",
            "updated": "2026-10-01",
            "author": "test",
            "license": "MIT",
            "platforms": ["macos", "windows", "linux"],
        },
        "plugins": {
            "synths": [
                {
                    "name": "FakeSynth",
                    "urls": {"macos": entry("fakesynth-mac.dmg", synth_hash)},
                }
            ],
            "samples": [
                {
                    "name": "FakeOrchestra",
                    "formats": ["SFZ"],
                    "urls": {
                        plat: entry("fakeorchestra.7z", lib_hash)
                        for plat in ("macos", "windows", "linux")
                    },
                }
            ],
        },
        "manual_download": [],
    }


@pytest.fixture
def served(mock_server, tmp_path):
    mock_server.add("/fakesynth-mac.dmg", b"synth-bytes")
    mock_server.add("/fakeorchestra.7z", b"sample-library-bytes")
    manifest = _manifest(
        mock_server.base_url,
        mock_server.sha256_of("/fakesynth-mac.dmg"),
        mock_server.sha256_of("/fakeorchestra.7z"),
    )
    path = tmp_path / "plugins.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _run(monkeypatch, plugins_json: Path, out: Path, *extra: str) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "download-plugins.py",
            "--platform",
            "macos",
            "--dir",
            str(out),
            "--plugins-json",
            str(plugins_json),
            *extra,
        ],
    )
    dlp.main()


def test_plain_run_skips_sample_libraries(served, tmp_path, monkeypatch) -> None:
    out = tmp_path / "out"
    _run(monkeypatch, served, out)
    assert (out / "fakesynth-mac.dmg").exists()
    assert not (out / "fakeorchestra.7z").exists()


def test_samples_flag_downloads_only_sample_libraries(
    served, tmp_path, monkeypatch
) -> None:
    out = tmp_path / "out"
    _run(monkeypatch, served, out, "--samples")
    assert (out / "fakeorchestra.7z").read_bytes() == b"sample-library-bytes"
    assert not (out / "fakesynth-mac.dmg").exists()


def test_samples_combine_with_other_category_flags(
    served, tmp_path, monkeypatch
) -> None:
    out = tmp_path / "out"
    _run(monkeypatch, served, out, "--synths", "--samples")
    assert (out / "fakesynth-mac.dmg").exists()
    assert (out / "fakeorchestra.7z").exists()


def test_only_reaches_sample_libraries_without_flag(
    served, tmp_path, monkeypatch
) -> None:
    out = tmp_path / "out"
    _run(monkeypatch, served, out, "--only", "orchestra")
    assert (out / "fakeorchestra.7z").exists()
    assert not (out / "fakesynth-mac.dmg").exists()


def test_list_shows_sample_libraries_as_opt_in(
    served, tmp_path, monkeypatch, capsys
) -> None:
    _run(monkeypatch, served, tmp_path / "out", "--list")
    printed = capsys.readouterr().out
    assert "Sample Libraries (SFZ) - only with --samples" in printed
    assert "FakeOrchestra" in printed


def test_real_manifest_sample_libraries_are_platform_neutral() -> None:
    # Sample libraries are plain archives, so every platform gets the same pin.
    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "plugins.json").read_text(
            encoding="utf-8"
        )
    )
    libraries = manifest["plugins"]["samples"]
    assert libraries
    for lib in libraries:
        pins = {
            (e["url"], e["sha256"]) for e in lib["urls"].values() if isinstance(e, dict)
        }
        assert len(pins) == 1, lib["name"]
        assert set(lib["urls"]) == {"macos", "windows", "linux"}, lib["name"]
        assert "SFZ" in lib.get("formats", []), lib["name"]
