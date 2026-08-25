"""Tests for --check-updates and its helpers."""

from __future__ import annotations

import hashlib
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
    return json.dumps(
        {
            "tag_name": tag,
            "assets": [
                {
                    "name": n,
                    "browser_download_url": f"https://example.invalid/{n}",
                    "size": 1234,
                }
                for n in asset_names
            ],
        }
    ).encode("utf-8")


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
    assert (
        result["assets"][0]["url"]
        == "https://example.invalid/airwindows-2026-06-15-abc.dmg"
    )


def _candidates(*names: str) -> list[dict]:
    return [
        {"name": n, "url": f"https://example.invalid/{n}", "size": 1000} for n in names
    ]


def test_find_matching_asset_exact_substitution() -> None:
    current = "Surge-XT-1.3.4-mac.dmg"
    cands = _candidates(
        "Surge-XT-1.3.5-mac.dmg", "Surge-XT-1.3.5-win.exe", "Surge-XT-1.3.5-linux.deb"
    )

    result = dlp.find_matching_asset(current, cands, old_tag="1.3.4", new_tag="1.3.5")

    assert result is not None
    assert result["name"] == "Surge-XT-1.3.5-mac.dmg"


def test_find_matching_asset_token_overlap_fallback() -> None:
    # Rolling-tag case: filename contains a date+commit not derivable by tag substitution.
    current = "airwindows-consolidated-macOS-2026-05-02-dc0ed69.dmg"
    cands = _candidates(
        "airwindows-consolidated-macOS-2026-06-15-newcommit.dmg",
        "AirwindowsConsolidated-2026-06-15-newcommit-Linux.zip",
        "AirwindowsConsolidated-2026-06-15-newcommit-Windows-64bit-setup.exe",
    )

    # old_tag == new_tag (rolling DAWPlugin). Strategy A produces no substitution
    # because old_tag != new_tag is False. Falls through to Strategy B.
    result = dlp.find_matching_asset(
        current, cands, old_tag="DAWPlugin", new_tag="DAWPlugin"
    )

    assert result is not None
    assert result["name"] == "airwindows-consolidated-macOS-2026-06-15-newcommit.dmg"


def test_find_matching_asset_returns_none_when_no_match() -> None:
    current = "Surge-XT-1.3.4-mac.dmg"
    cands = _candidates("totally-unrelated-thing.zip")

    result = dlp.find_matching_asset(current, cands, old_tag="1.3.4", new_tag="1.3.5")

    assert result is None


def test_find_matching_asset_returns_none_for_extension_only_match() -> None:
    current = "fileA.dmg"
    cands = _candidates("fileB.dmg")  # only the .dmg extension is shared

    result = dlp.find_matching_asset(current, cands)

    assert result is None


def _serve_fake_release(
    mock_server, repo: str, tag: str, asset_names: list[str]
) -> None:
    body = _fake_release(tag, asset_names)
    mock_server.add(f"/repos/{repo}/releases/latest", body)


def _write_update_fixture(template: Path, dest: Path) -> None:
    # No URL substitution needed in the JSON — the script will be told the api_base
    # via env var. The plugin URLs themselves point at example.invalid (never fetched
    # in --check-updates read-only mode).
    dest.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")


def test_check_updates_reports_drift_without_writing(
    mock_server, fixtures_dir, tmp_path
) -> None:
    _serve_fake_release(
        mock_server,
        "fake/synth",
        "v1.0.1",
        ["FakeSynth-1.0.1-mac.dmg", "FakeSynth-1.0.1-win.exe"],
    )

    json_path = tmp_path / "plugins.json"
    _write_update_fixture(fixtures_dir / "plugins-update-fixture.json", json_path)
    original_text = json_path.read_text(encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check-updates",
            "--plugins-json",
            str(json_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "VST_DLP_GITHUB_API_BASE": mock_server.base_url},
    )

    assert result.returncode == 1, (
        f"expected exit 1 (drift), got {result.returncode}\n{result.stdout}\n{result.stderr}"
    )
    assert "FakeSynth" in result.stdout
    assert "1.0.0" in result.stdout
    assert "1.0.1" in result.stdout
    assert "NEW VERSION" in result.stdout

    # Crucially: read-only. plugins.json must be byte-identical.
    assert json_path.read_text(encoding="utf-8") == original_text


def test_check_updates_exit_zero_when_no_drift(
    mock_server, fixtures_dir, tmp_path
) -> None:
    # Mock returns the SAME version that's pinned in the fixture.
    _serve_fake_release(
        mock_server,
        "fake/synth",
        "1.0.0",
        ["FakeSynth-1.0.0-mac.dmg", "FakeSynth-1.0.0-win.exe"],
    )

    json_path = tmp_path / "plugins.json"
    _write_update_fixture(fixtures_dir / "plugins-update-fixture.json", json_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check-updates",
            "--plugins-json",
            str(json_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "VST_DLP_GITHUB_API_BASE": mock_server.base_url},
    )

    assert result.returncode == 0
    assert "no update" in result.stdout.lower()


def test_apply_writes_url_filename_version_and_recomputes_hash(
    mock_server, fixtures_dir, tmp_path
) -> None:
    # Mock-server-served release: simulates upstream having shipped 1.0.1.
    _serve_fake_release(
        mock_server,
        "fake/synth",
        "1.0.1",
        ["FakeSynth-1.0.1-mac.dmg", "FakeSynth-1.0.1-win.exe"],
    )

    # Mock the actual download endpoints that recompute_hashes will hit.
    mac_body = b"new-mac-installer-bytes"
    win_body = b"new-win-installer-bytes"
    mock_server.add("/FakeSynth-1.0.1-mac.dmg", mac_body)
    mock_server.add("/FakeSynth-1.0.1-win.exe", win_body)

    json_path = tmp_path / "plugins.json"
    # Modify fixture: rewrite the example.invalid URLs to point at the mock server,
    # so when --apply re-points URLs to the new asset URLs from the API response,
    # the hashes can actually be computed against the mock's body.
    fixture_text = (fixtures_dir / "plugins-update-fixture.json").read_text(
        encoding="utf-8"
    )
    json_path.write_text(fixture_text, encoding="utf-8")

    # The API response uses browser_download_url=https://example.invalid/<name>; rewrite
    # it to mock_server.base_url so recompute_hashes can fetch them.
    # We do this by serving release JSON whose asset URLs point at the mock server.
    body = json.dumps(
        {
            "tag_name": "1.0.1",
            "assets": [
                {
                    "name": "FakeSynth-1.0.1-mac.dmg",
                    "browser_download_url": mock_server.url_for(
                        "/FakeSynth-1.0.1-mac.dmg"
                    ),
                    "size": len(mac_body),
                },
                {
                    "name": "FakeSynth-1.0.1-win.exe",
                    "browser_download_url": mock_server.url_for(
                        "/FakeSynth-1.0.1-win.exe"
                    ),
                    "size": len(win_body),
                },
            ],
        }
    ).encode("utf-8")
    mock_server.add("/repos/fake/synth/releases/latest", body)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check-updates",
            "--apply",
            "--plugins-json",
            str(json_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "VST_DLP_GITHUB_API_BASE": mock_server.base_url},
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    data = json.loads(json_path.read_text(encoding="utf-8"))
    plugin = data["plugins"]["synths"][0]
    assert plugin["version"] == "1.0.1"

    mac = plugin["urls"]["macos"]
    win = plugin["urls"]["windows"]

    import hashlib

    assert mac["filename"] == "FakeSynth-1.0.1-mac.dmg"
    assert mac["url"] == mock_server.url_for("/FakeSynth-1.0.1-mac.dmg")
    assert mac["sha256"] == hashlib.sha256(mac_body).hexdigest()
    assert mac["hash_source"] == "self"

    assert win["filename"] == "FakeSynth-1.0.1-win.exe"
    assert win["url"] == mock_server.url_for("/FakeSynth-1.0.1-win.exe")
    assert win["sha256"] == hashlib.sha256(win_body).hexdigest()
    assert win["hash_source"] == "self"


def test_find_matching_asset_url_tokens_disambiguate_architecture() -> None:
    # Maintainer's filename is the simpler form, but the URL has the full upstream name.
    current_filename = "dragonfly-reverb-3.2.10-macos.dmg"
    current_url = "https://example.invalid/dragonfly-reverb-3.2.10-macos-universal.dmg"
    cands = _candidates(
        "dragonfly-reverb-3.2.10-macos-intel.dmg",
        "dragonfly-reverb-3.2.10-macos-universal.dmg",
    )

    # Without the URL, both arch variants would tie on tokens with the filename.
    # With the URL, the universal variant scores higher because 'universal' appears in the URL.
    result = dlp.find_matching_asset(current_filename, cands, current_url=current_url)

    assert result is not None
    assert result["name"] == "dragonfly-reverb-3.2.10-macos-universal.dmg"


TYRELL_N6_PAGE_HTML = (
    b"<html><body><h1>TyrellN6</h1>"
    b"<p>TyrellN6 Beta 3.0.1 (revision 17000) released April 1, 2026.</p>"
    b"</body></html>"
)


def test_detect_latest_for_uhe_parses_version_and_builds_asset_urls(
    mock_server,
) -> None:
    mock_server.add("/products/tyrelln6/", TYRELL_N6_PAGE_HTML)

    result = dlp.detect_latest_for_uhe(
        "TyrellN6",
        page_url=mock_server.url_for("/products/tyrelln6/"),
        dl_base=mock_server.base_url,
    )

    assert result["tag"] == "3.0.1-r17000"
    asset_names = sorted(a["name"] for a in result["assets"])
    assert asset_names == [
        "TyrellN6_301_public_beta_17000_Linux.tar.xz",
        "TyrellN6_301_public_beta_17000_Mac.zip",
        "TyrellN6_301_public_beta_17000_Win.zip",
    ]
    # Asset URLs must use the dl_base override.
    for asset in result["assets"]:
        assert asset["url"].startswith(mock_server.base_url + "/releases/")


def test_detect_latest_for_uhe_raises_on_unknown_product() -> None:
    with pytest.raises(ValueError, match="unknown u-he product"):
        dlp.detect_latest_for_uhe("NotAProduct")


def test_detect_latest_for_uhe_raises_when_version_regex_fails(mock_server) -> None:
    mock_server.add("/products/tyrelln6/", b"<html>nothing useful here</html>")

    with pytest.raises(RuntimeError, match="recognizable version"):
        dlp.detect_latest_for_uhe(
            "TyrellN6",
            page_url=mock_server.url_for("/products/tyrelln6/"),
            dl_base=mock_server.base_url,
        )


def test_find_matching_asset_prefers_filename_over_url_tokens() -> None:
    # OB-Xd-style: current entry's URL has `OB-Xd` which splits into 'ob','xd'
    # tokens. Without filename-first scoring, the macOS .pkg candidate would
    # win for the Windows entry because its tokens include 'ob','xd','19'.
    current_filename = "Obxd219.exe"
    current_url = "https://github.com/reales/OB-Xd/releases/download/v2.19/Obxd219.exe"
    cands = _candidates(
        "OB-Xd.2.19.pkg",  # macOS installer (would win on URL-token boost)
        "Obxd219.exe",  # actual Windows installer
        "Obxd219.deb",  # Linux installer
    )

    result = dlp.find_matching_asset(current_filename, cands, current_url=current_url)

    assert result is not None
    assert result["name"] == "Obxd219.exe"


def test_check_updates_drift_for_uhe_plugin(
    mock_server, fixtures_dir, tmp_path
) -> None:
    # Fake page advertises 3.0.1-r17000; fixture is pinned at 3.0.0-r16976.
    mock_server.add("/products/tyrelln6/", TYRELL_N6_PAGE_HTML)

    json_path = tmp_path / "plugins.json"
    fixture = {
        "meta": {
            "name": "Test Fixture",
            "version": "0.0.0",
            "description": "uhe drift",
            "updated": "2026-05-09",
            "author": "test",
            "license": "MIT",
            "platforms": ["macos"],
        },
        "plugins": {
            "synths": [
                {
                    "name": "Tyrell N6",
                    "description": "fixture",
                    "update_strategy": "u-he:TyrellN6",
                    "urls": {
                        "macos": {
                            "url": "https://example.invalid/TyrellN6_300_public_beta_16976_Mac.zip",
                            "filename": "TyrellN6_300_public_beta_16976_Mac.zip",
                            "sha256": "0" * 64,
                            "hash_source": "self",
                        }
                    },
                    "version": "3.0.0",
                    "formats": ["VST3"],
                    "website": "https://u-he.com/products/tyrelln6/",
                    "open_source": False,
                }
            ]
        },
        "manual_download": [],
    }
    json_path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    original_text = json_path.read_text(encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check-updates",
            "--plugins-json",
            str(json_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "VST_DLP_UHE_PAGE_URL_TyrellN6": mock_server.url_for("/products/tyrelln6/"),
            "VST_DLP_UHE_DL_BASE": mock_server.base_url,
        },
    )

    assert result.returncode == 1, f"expected exit 1\n{result.stdout}\n{result.stderr}"
    assert "Tyrell N6" in result.stdout
    assert "NEW VERSION" in result.stdout
    assert "3.0.1" in result.stdout or "17000" in result.stdout

    # Read-only: file unchanged.
    assert json_path.read_text(encoding="utf-8") == original_text


def test_check_updates_apply_for_uhe_plugin(
    mock_server, fixtures_dir, tmp_path
) -> None:
    mock_server.add("/products/tyrelln6/", TYRELL_N6_PAGE_HTML)

    # The new asset bytes the apply path will fetch + hash.
    mac_body = b"new-mac-tyrelln6"
    mock_server.add("/releases/TyrellN6_301_public_beta_17000_Mac.zip", mac_body)

    json_path = tmp_path / "plugins.json"
    fixture = {
        "meta": {
            "name": "Test Fixture",
            "version": "0.0.0",
            "description": "uhe apply",
            "updated": "2026-05-09",
            "author": "test",
            "license": "MIT",
            "platforms": ["macos"],
        },
        "plugins": {
            "synths": [
                {
                    "name": "Tyrell N6",
                    "description": "fixture",
                    "update_strategy": "u-he:TyrellN6",
                    "urls": {
                        "macos": {
                            "url": "https://example.invalid/TyrellN6_300_public_beta_16976_Mac.zip",
                            "filename": "TyrellN6_300_public_beta_16976_Mac.zip",
                            "sha256": "0" * 64,
                            "hash_source": "self",
                        }
                    },
                    "version": "3.0.0",
                    "formats": ["VST3"],
                    "website": "https://u-he.com/products/tyrelln6/",
                    "open_source": False,
                }
            ]
        },
        "manual_download": [],
    }
    json_path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check-updates",
            "--apply",
            "--plugins-json",
            str(json_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "VST_DLP_UHE_PAGE_URL_TyrellN6": mock_server.url_for("/products/tyrelln6/"),
            "VST_DLP_UHE_DL_BASE": mock_server.base_url,
        },
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    data = json.loads(json_path.read_text(encoding="utf-8"))
    plugin = data["plugins"]["synths"][0]
    assert plugin["version"] == "3.0.1-r17000"

    mac = plugin["urls"]["macos"]
    import hashlib

    assert mac["filename"] == "TyrellN6_301_public_beta_17000_Mac.zip"
    assert mac["url"] == mock_server.url_for(
        "/releases/TyrellN6_301_public_beta_17000_Mac.zip"
    )
    assert mac["sha256"] == hashlib.sha256(mac_body).hexdigest()
    assert mac["hash_source"] == "self"


def test_parse_update_strategy_recognizes_stable_url():
    assert dlp._parse_update_strategy("stable-url") == ("stable-url",)


def test_parse_update_strategy_rejects_stable_url_with_slug():
    # `stable-url:something` is not a recognized variant — must be exactly "stable-url".
    assert dlp._parse_update_strategy("stable-url:foo") is None


def test_detect_drift_for_stable_url_flags_changed_bytes(mock_server):
    new_body = b"<<<new binary content>>>"
    new_url = mock_server.add("/plugin.zip", new_body)

    entry = {
        "name": "FakePlugin",
        "update_strategy": "stable-url",
        "urls": {
            "macos": {
                "url": new_url,
                "filename": "plugin.zip",
                "sha256": "0" * 64,  # stored hash that won't match new_body
                "hash_source": "self",
            },
        },
    }

    result = dlp.detect_drift_for_stable_url(entry)

    assert result["drift"] is True
    assert "macos" in result["platforms"]
    macos = result["platforms"]["macos"]
    assert macos["changed"] is True
    assert macos["old_sha256"] == "0" * 64
    assert macos["new_sha256"] == hashlib.sha256(new_body).hexdigest()


def test_detect_drift_for_stable_url_no_drift_when_hash_matches(mock_server):
    body = b"<<<unchanged binary content>>>"
    url = mock_server.add("/plugin.zip", body)
    stored = hashlib.sha256(body).hexdigest()

    entry = {
        "name": "FakePlugin",
        "update_strategy": "stable-url",
        "urls": {
            "macos": {
                "url": url,
                "filename": "plugin.zip",
                "sha256": stored,
                "hash_source": "self",
            },
        },
    }

    result = dlp.detect_drift_for_stable_url(entry)

    assert result["drift"] is False
    assert result["platforms"]["macos"]["changed"] is False
    assert result["platforms"]["macos"]["new_sha256"] == stored


def test_check_updates_drift_for_stable_url_plugin(mock_server):
    new_body = b"<<<new build pushed silently by vendor>>>"
    drifted_url = mock_server.add("/valhalla/supermassive-mac.zip", new_body)

    plugins_data = {
        "meta": {
            "name": "test",
            "version": "1",
            "description": "x",
            "updated": "2026-05-09",
            "author": "x",
            "license": "x",
            "platforms": ["macos"],
        },
        "plugins": {
            "effects": [
                {
                    "name": "FakeStable",
                    "version": "5.0.0",
                    "update_strategy": "stable-url",
                    "urls": {
                        "macos": {
                            "url": drifted_url,
                            "filename": "supermassive-mac.zip",
                            "sha256": "0" * 64,  # stale hash — will not match new_body
                            "hash_source": "self",
                        },
                    },
                }
            ],
        },
    }

    report = dlp.check_updates(plugins_data)

    assert len(report["updates"]) == 1
    upd = report["updates"][0]
    assert upd["name"] == "FakeStable"
    assert upd["strategy"] == "stable-url"
    assert upd["old_version"] == "5.0.0"
    assert upd["new_version"] == "5.0.0"  # unchanged for stable-url
    plats = {p["plat"]: p for p in upd["platforms"]}
    assert "macos" in plats
    assert plats["macos"]["changed"] is True
    assert plats["macos"]["new_sha256"] == hashlib.sha256(new_body).hexdigest()


def test_check_updates_no_drift_for_stable_url_plugin(mock_server):
    body = b"<<<unchanged>>>"
    url = mock_server.add("/static.zip", body)
    stored = hashlib.sha256(body).hexdigest()

    plugins_data = {
        "meta": {
            "name": "test",
            "version": "1",
            "description": "x",
            "updated": "2026-05-09",
            "author": "x",
            "license": "x",
            "platforms": ["macos"],
        },
        "plugins": {
            "effects": [
                {
                    "name": "FakeStable",
                    "version": "1.0",
                    "update_strategy": "stable-url",
                    "urls": {
                        "macos": {
                            "url": url,
                            "filename": "static.zip",
                            "sha256": stored,
                            "hash_source": "self",
                        },
                    },
                }
            ],
        },
    }

    report = dlp.check_updates(plugins_data)

    assert len(report["updates"]) == 0
    assert len(report["no_updates"]) == 1
    assert report["no_updates"][0]["name"] == "FakeStable"


def test_apply_for_stable_url_plugin(mock_server):
    new_body = b"<<<new build>>>"
    drifted_url = mock_server.add("/valhalla/supermassive-mac.zip", new_body)
    new_hash = hashlib.sha256(new_body).hexdigest()
    old_hash = "0" * 64

    plugins_data = {
        "meta": {
            "name": "test",
            "version": "1",
            "description": "x",
            "updated": "2026-05-09",
            "author": "x",
            "license": "x",
            "platforms": ["macos"],
        },
        "plugins": {
            "effects": [
                {
                    "name": "FakeStable",
                    "version": "5.0.0",
                    "update_strategy": "stable-url",
                    "urls": {
                        "macos": {
                            "url": drifted_url,
                            "filename": "supermassive-mac.zip",
                            "sha256": old_hash,
                            "hash_source": "publisher",  # gets reset to 'self' by apply
                        },
                    },
                }
            ],
        },
    }

    report = dlp.check_updates(plugins_data)
    dlp.apply_updates(plugins_data, report)

    plugin = plugins_data["plugins"]["effects"][0]
    macos = plugin["urls"]["macos"]
    assert macos["sha256"] == new_hash
    assert macos["hash_source"] == "self"
    assert macos["url"] == drifted_url
    assert macos["filename"] == "supermassive-mac.zip"
    assert plugin["version"] == "5.0.0"


def test_apply_for_stable_url_skips_unchanged_platforms(mock_server):
    # macOS: bytes match the stored hash (no drift).
    mac_body = b"<<<unchanged mac build>>>"
    mac_url = mock_server.add("/stable/mac.zip", mac_body)
    mac_stored = hashlib.sha256(mac_body).hexdigest()

    # Windows: bytes do NOT match the stored hash (drifted).
    win_body = b"<<<new windows build pushed silently>>>"
    win_url = mock_server.add("/stable/win.zip", win_body)
    win_stale = "0" * 64
    win_new = hashlib.sha256(win_body).hexdigest()

    plugins_data = {
        "meta": {
            "name": "test",
            "version": "1",
            "description": "x",
            "updated": "2026-05-09",
            "author": "x",
            "license": "x",
            "platforms": ["macos", "windows"],
        },
        "plugins": {
            "effects": [
                {
                    "name": "FakeStable",
                    "version": "5.0.0",
                    "update_strategy": "stable-url",
                    "urls": {
                        "macos": {
                            "url": mac_url,
                            "filename": "mac.zip",
                            "sha256": mac_stored,
                            "hash_source": "publisher",
                        },
                        "windows": {
                            "url": win_url,
                            "filename": "win.zip",
                            "sha256": win_stale,
                            "hash_source": "publisher",
                        },
                    },
                }
            ],
        },
    }

    report = dlp.check_updates(plugins_data)
    dlp.apply_updates(plugins_data, report)

    plugin = plugins_data["plugins"]["effects"][0]
    macos = plugin["urls"]["macos"]
    windows = plugin["urls"]["windows"]

    # Drifted platform: sha256 updated, hash_source reset to 'self'.
    assert windows["sha256"] == win_new
    assert windows["hash_source"] == "self"

    # Unchanged platform: sha256 untouched, hash_source untouched.
    assert macos["sha256"] == mac_stored
    assert macos["hash_source"] == "publisher"
