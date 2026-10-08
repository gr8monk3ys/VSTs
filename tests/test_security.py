"""Security invariants: HTTPS-only fetching, safe redirects, filenames that
cannot leave the download folder, verified-only extraction, and schema rules
that keep unsafe catalog entries out of plugins.json."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

import jsonschema
import pytest

from free_vst_plugins import cli as dlp

REPO = Path(__file__).resolve().parents[1]
GOOD_HASH = "a" * 64


def _entry(**overrides) -> dict:
    entry = {
        "url": "https://example.invalid/x.exe",
        "filename": "x.exe",
        "sha256": GOOD_HASH,
        "hash_source": "self",
    }
    entry.update(overrides)
    return entry


# ── URL policy and redirects ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid/x.exe",
        "http://127.0.0.1:8000/x.exe",
        "http://localhost/x.exe",
    ],
)
def test_check_url_allowed_accepts_https_and_loopback_http(url) -> None:
    dlp.check_url_allowed(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid/x.exe",
        "file:///C:/Windows/System32/cmd.exe",
        "ftp://example.invalid/x.exe",
        "x.exe",
    ],
)
def test_check_url_allowed_refuses_everything_else(url) -> None:
    with pytest.raises(dlp.InsecureURLError):
        dlp.check_url_allowed(url)


def _redirect(old_url: str, new_url: str, headers: dict) -> urllib.request.Request:
    req = urllib.request.Request(old_url, headers=headers)
    return dlp._SafeRedirectHandler().redirect_request(
        req, None, 302, "Found", {}, new_url
    )


def test_redirect_to_another_host_drops_authorization() -> None:
    new = _redirect(
        "https://api.github.com/x",
        "https://evil.example/x",
        {"Authorization": "Bearer secret", "Accept": "a"},
    )
    assert not new.has_header("Authorization")
    assert new.get_header("Accept") == "a"


def test_redirect_on_same_host_keeps_authorization() -> None:
    new = _redirect(
        "https://api.github.com/x",
        "https://api.github.com/y",
        {"Authorization": "Bearer secret"},
    )
    assert new.get_header("Authorization") == "Bearer secret"


def test_redirect_downgrade_to_http_is_refused() -> None:
    with pytest.raises(dlp.InsecureURLError):
        _redirect("https://vendor.example/x.exe", "http://vendor.example/x.exe", {})


def test_download_file_refuses_plain_http(tmp_path) -> None:
    out = tmp_path / "x.exe"
    ok = dlp.download_file("http://example.invalid/x.exe", out, "X", GOOD_HASH, "s")
    assert ok is False
    assert not out.exists()
    assert not (tmp_path / "x.exe.part").exists()


def test_github_token_only_sent_to_api_github_com(monkeypatch) -> None:
    seen: list[dict] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"tag_name": "v1", "assets": []}'

    def fake_open_url(url, *, timeout, headers=None):
        seen.append(dict(headers or {}))
        return FakeResponse()

    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setattr(dlp, "open_url", fake_open_url)

    dlp.detect_latest_for_github("o/r", api_base="http://127.0.0.1:1")
    dlp.detect_latest_for_github("o/r")

    assert "Authorization" not in seen[0]
    assert seen[1]["Authorization"] == "Bearer secret"


# ── Download targets stay inside the download folder ───────────────────────


@pytest.mark.parametrize(
    "entry",
    [
        _entry(filename="../evil.exe"),
        _entry(filename="..\\evil.exe"),
        _entry(filename="C:\\Users\\x\\evil.exe"),
        _entry(filename="/etc/evil"),
        _entry(filename=".."),
        _entry(filename="x.exe:stream"),
        _entry(filename="", url="https://example.invalid/a/..%2F..%2Fevil.exe"),
        _entry(url="http://example.invalid/x.exe"),
        _entry(sha256="F" * 64),
        _entry(sha256=""),
        {"url": "https://example.invalid/x.exe", "filename": "x.exe"},
    ],
)
def test_resolve_target_refuses_unsafe_entries(entry, tmp_path) -> None:
    plugin = {"name": "X", "urls": {"windows": entry}}
    with pytest.raises(dlp.UnsafeEntry):
        dlp.resolve_target(plugin, "windows", tmp_path)


def test_resolve_target_returns_path_inside_download_dir(tmp_path) -> None:
    plugin = {"name": "X", "urls": {"windows": _entry()}}
    target = dlp.resolve_target(plugin, "windows", tmp_path)
    assert target.path == tmp_path / "x.exe"
    assert target.sha256 == GOOD_HASH
    assert dlp.resolve_target(plugin, "macos", tmp_path) is None


def test_traversal_filename_neither_writes_nor_deletes_outside(
    mock_server, tmp_path, monkeypatch
) -> None:
    body = b"payload"
    url = mock_server.add("/evil.exe", body)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me", encoding="utf-8")
    manifest = {
        "meta": {},
        "plugins": {
            "synths": [
                {
                    "name": "Evil",
                    "urls": {
                        "windows": _entry(
                            url=url,
                            filename="../victim.txt",
                            sha256=hashlib.sha256(body).hexdigest(),
                        )
                    },
                }
            ]
        },
    }
    plugins_json = tmp_path / "plugins.json"
    plugins_json.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "x",
            "--platform",
            "windows",
            "--dir",
            str(tmp_path / "out"),
            "--plugins-json",
            str(plugins_json),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        dlp.main()
    assert exc.value.code == 1
    assert victim.read_text(encoding="utf-8") == "keep me"


def test_failed_download_leaves_no_file_under_final_name(mock_server, tmp_path) -> None:
    out = tmp_path / "x.exe"
    ok = dlp.download_file(mock_server.url_for("/missing"), out, "X", GOOD_HASH, "s")
    assert ok is False
    assert list(tmp_path.iterdir()) == []


# ── Archive extraction ──────────────────────────────────────────────────────


def test_extract_archives_refuses_zip_slip(tmp_path) -> None:
    archive = tmp_path / "lib.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("ok.txt", "fine")
        zf.writestr("../escaped.txt", "nope")
    dlp.extract_archives([archive])
    assert not (tmp_path / "lib").exists()
    assert not (tmp_path / "escaped.txt").exists()


def test_extract_archives_only_touches_the_archives_given(tmp_path) -> None:
    for stem in ("verified", "unrelated"):
        with zipfile.ZipFile(tmp_path / f"{stem}.zip", "w") as zf:
            zf.writestr("a.txt", stem)
    dlp.extract_archives([tmp_path / "verified.zip"])
    assert (tmp_path / "verified" / "a.txt").read_text() == "verified"
    assert not (tmp_path / "unrelated").exists()


# ── Update pipeline ─────────────────────────────────────────────────────────


def test_find_matching_asset_never_picks_a_checksum_sidecar() -> None:
    cands = [
        {"name": "Surge-XT-1.3.2-Setup.exe.sha256", "url": "u1", "size": 1},
        {"name": "Surge-XT-1.3.2-Setup.exe", "url": "u2", "size": 1},
    ]
    result = dlp.find_matching_asset("Surge-XT-1.3.1-Setup.exe", cands)
    assert result["name"] == "Surge-XT-1.3.2-Setup.exe"


def test_pin_applied_updates_reverts_only_the_plugin_that_fails(
    mock_server,
) -> None:
    good_url = mock_server.add("/good-2.exe", b"good")
    original = {
        "plugins": {
            "synths": [
                {"name": "Good", "version": "1", "urls": {"windows": _entry()}},
                {"name": "Bad", "version": "1", "urls": {"windows": _entry()}},
            ]
        }
    }
    data = copy.deepcopy(original)
    for plugin, url in zip(
        data["plugins"]["synths"], (good_url, mock_server.url_for("/gone.exe"))
    ):
        entry = plugin["urls"]["windows"]
        entry["url"] = url
        entry.pop("sha256")
        entry.pop("hash_source")
        plugin["version"] = "2"

    reverted = dlp.pin_applied_updates(data, original)

    assert [r["name"] for r in reverted] == ["Bad"]
    good, bad = data["plugins"]["synths"]
    assert good["urls"]["windows"]["sha256"] == hashlib.sha256(b"good").hexdigest()
    assert good["version"] == "2"
    assert bad == original["plugins"]["synths"][1]


# ── Catalog site and schema ─────────────────────────────────────────────────


def _load_build_site():
    spec = importlib.util.spec_from_file_location(
        "build_site", REPO / "scripts" / "build_site.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_site_never_renders_a_javascript_href() -> None:
    build_site = _load_build_site()
    card = build_site.render_plugin_card(
        {"name": "X", "website": "javascript:alert(1)", "urls": {}}
    )
    manual = build_site.render_manual_card(
        {"name": "Y", "website": "JavaScript:alert(1)"}
    )
    assert "javascript:" not in card.lower()
    assert "javascript:" not in manual.lower()
    assert build_site.REPO_URL in card


def _manifest_with(entry: dict, **plugin_fields) -> dict:
    return {
        "meta": {
            "name": "x",
            "version": "0",
            "description": "x",
            "updated": "2026-10-07",
            "author": "x",
            "license": "MIT",
            "platforms": ["windows"],
        },
        "plugins": {
            "synths": [{"name": "x", "urls": {"windows": entry}, **plugin_fields}]
        },
        "manual_download": [],
    }


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(
        (REPO / "schemas" / "plugins.schema.json").read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    "manifest",
    [
        _manifest_with(_entry(url="http://example.invalid/x.exe")),
        _manifest_with(_entry(url="file:///etc/passwd")),
        _manifest_with(_entry(filename="../x.exe")),
        _manifest_with(_entry(filename="sub\\x.exe")),
        _manifest_with(_entry(filename="C:x.exe")),
        _manifest_with(_entry(filename="..")),
        _manifest_with(_entry(), website="javascript:alert(1)"),
    ],
)
def test_schema_rejects_unsafe_entries(schema, manifest) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=manifest, schema=schema)


def test_schema_rejects_manual_entry_with_non_https_website(schema) -> None:
    manifest = _manifest_with(_entry())
    manifest["manual_download"] = [{"name": "M", "website": "javascript:alert(1)"}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=manifest, schema=schema)


def test_schema_accepts_a_plain_entry(schema) -> None:
    jsonschema.validate(
        instance=_manifest_with(_entry(filename="Surge XT 1.3.4 (x64).exe")),
        schema=schema,
    )
