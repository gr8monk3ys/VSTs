# Checksum Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SHA-256 verification to every plugin download in `scripts/download-plugins.py`, with strict abort-on-mismatch and CI-enforced data invariants in `plugins.json`.

**Architecture:** Each per-platform URL entry in `plugins.json` gains `sha256` (lowercase hex) and `hash_source` (`publisher` | `self`) fields. The downloader streams + hashes in a single I/O pass and aborts on mismatch. A new `--compute-hashes` mode lets a maintainer backfill self-tier hashes. CI enforces the schema, and two existing toothless CI checks (`ruff || true` and the commented-out URL-check `sys.exit(1)`) are corrected as part of this work.

**Tech Stack:** Python 3.9+ stdlib only at runtime (urllib, hashlib, json, argparse). Tests use `pytest` and `jsonschema` (installed in CI inline; no requirements file). Mock HTTP server for integration tests uses stdlib `http.server` in a thread.

**Spec:** `docs/superpowers/specs/2026-05-09-checksum-verification-design.md`

---

## File Structure

| Path | Status | Responsibility |
|------|--------|----------------|
| `scripts/download-plugins.py` | Modified | CLI entry, downloads, verification, hash computation |
| `plugins.json` | Modified | Source-of-truth registry + per-entry hashes |
| `schemas/plugins.schema.json` | New | JSON schema enforcing required fields |
| `tests/__init__.py` | New | Marks tests as a package |
| `tests/conftest.py` | New | Shared pytest fixtures (mock HTTP server, fixture JSON) |
| `tests/test_compute_hash.py` | New | Unit test for `compute_hash_for_url()` |
| `tests/test_compute_hashes_mode.py` | New | Integration test for `--compute-hashes` CLI mode |
| `tests/test_download_verify.py` | New | Integration test for verifying `download_file()` (mismatch + cached re-verify) |
| `tests/test_schema.py` | New | Asserts `plugins.json` validates against schema |
| `tests/fixtures/plugins-empty-hashes.json` | New | Tiny plugins.json with mock-server URLs and missing hashes (for `--compute-hashes` test) |
| `tests/fixtures/plugins-with-hashes.json` | New | Tiny plugins.json with mock-server URLs and known hashes (for verify test) |
| `.github/workflows/ci.yml` | Modified | Add schema-validate step, fix `\|\| true`, uncomment `sys.exit(1)`, run pytest |

**Note on `download-plugins.py` decomposition:** the existing file is ~400 lines and roughly tolerable. We're not restructuring it — just rewriting `download_file()` in place, deleting `download_airwindows()`, and adding two new functions (`compute_hash_for_url`, `recompute_hashes`) plus a `--compute-hashes` branch in `main()`.

---

## Task 1: Set up tests/ directory with pytest

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/` (directory)

**Why first:** Every subsequent task is TDD. We need a working pytest harness with a mock HTTP server fixture before we can write the first failing test.

- [ ] **Step 1: Create `tests/__init__.py`**

Create an empty file at `tests/__init__.py`. This marks `tests/` as a package so imports work consistently across pytest versions.

```python
```

(Yes, the file is empty. Just `touch tests/__init__.py`.)

- [ ] **Step 2: Create `tests/conftest.py` with a mock HTTP server fixture**

Create `tests/conftest.py` with the following content:

```python
"""Shared fixtures for the test suite."""

from __future__ import annotations

import hashlib
import http.server
import socketserver
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pytest


@dataclass
class MockServer:
    """A running mock HTTP server. Use `add(path, body)` to register responses."""
    host: str
    port: int
    _routes: dict[str, bytes]

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def url_for(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def add(self, path: str, body: bytes) -> str:
        """Register a response body for the given path. Returns the full URL."""
        if not path.startswith("/"):
            path = "/" + path
        self._routes[path] = body
        return self.url_for(path)

    def sha256_of(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return hashlib.sha256(self._routes[path]).hexdigest()


@pytest.fixture
def mock_server() -> Iterator[MockServer]:
    routes: dict[str, bytes] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — http.server interface
            body = routes.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            pass  # silence stderr access logs during tests

    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    host, port = httpd.server_address
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield MockServer(host=host, port=port, _routes=routes)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
```

- [ ] **Step 3: Create the empty `tests/fixtures/` directory**

```bash
mkdir -p tests/fixtures
touch tests/fixtures/.gitkeep
```

- [ ] **Step 4: Verify pytest collects the (empty) test suite**

```bash
pip install pytest jsonschema
pytest tests/ -v
```

Expected: `no tests ran in 0.0Xs`. No errors, no import failures.

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/conftest.py tests/fixtures/.gitkeep
git commit -m "test: add pytest harness with mock HTTP server fixture"
```

---

## Task 2: Implement `compute_hash_for_url()` (TDD)

**Files:**
- Create: `tests/test_compute_hash.py`
- Modify: `scripts/download-plugins.py` (add new function near other helpers)

**Why:** This is the smallest unit of new behavior. The `--compute-hashes` mode (Task 3) and the verifying `download_file()` (Task 6) both build on it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_compute_hash.py`:

```python
"""Unit tests for compute_hash_for_url()."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load the script as a module (it has a hyphen in the name so we can't `import`).
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "download-plugins.py"
_spec = importlib.util.spec_from_file_location("dlp", _SCRIPT)
dlp = importlib.util.module_from_spec(_spec)
sys.modules["dlp"] = dlp
_spec.loader.exec_module(dlp)


def test_compute_hash_returns_sha256_of_stream(mock_server) -> None:
    body = b"the quick brown fox jumps over the lazy dog"
    url = mock_server.add("/file.bin", body)

    actual = dlp.compute_hash_for_url(url)

    assert actual == mock_server.sha256_of("/file.bin")
    # Sanity: matches the well-known SHA-256 of the test phrase.
    assert actual == "05c6e08f1d9fdafa03147fcb8f82f124c76d2f70e3d989dc8aadb5e7d7450bec"
```

- [ ] **Step 2: Run the test, expect failure**

```bash
pytest tests/test_compute_hash.py -v
```

Expected: `AttributeError: module 'dlp' has no attribute 'compute_hash_for_url'`.

- [ ] **Step 3: Implement `compute_hash_for_url()` in `scripts/download-plugins.py`**

Add a new top-level function. Insert it after the existing `download_file` function (around line 105) so related helpers stay clustered. Also add `import hashlib` near the top of the file with the other stdlib imports.

```python
import hashlib
```

```python
def compute_hash_for_url(url: str, chunk_size: int = 65536) -> str:
    """Stream the URL and return the lowercase hex SHA-256 of its body.

    Used by the --compute-hashes maintainer mode. Does NOT write a file
    or perform any verification — it is the trust-on-first-use primitive.
    """
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; VST-Downloader/1.0)'
    })
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as response:
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
```

- [ ] **Step 4: Run the test, expect pass**

```bash
pytest tests/test_compute_hash.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_compute_hash.py scripts/download-plugins.py
git commit -m "feat: add compute_hash_for_url() helper"
```

---

## Task 3: Implement `--compute-hashes` CLI mode (TDD)

**Files:**
- Create: `tests/test_compute_hashes_mode.py`
- Create: `tests/fixtures/plugins-empty-hashes.json`
- Modify: `scripts/download-plugins.py` (add `recompute_hashes()`, add CLI flags, branch in `main()`)

**Why:** We need this mode working *before* we touch `download_file()`, because it's how `plugins.json` will gain its hashes (Task 4). The verifying `download_file()` would refuse to run against today's hash-less data.

- [ ] **Step 1: Create the fixture `tests/fixtures/plugins-empty-hashes.json`**

This file is rewritten by the test (with `MOCKURL` placeholders that the test substitutes against the running mock server). Tests format the fixture before invoking the script.

```json
{
  "meta": {
    "name": "Test Fixture",
    "version": "0.0.0",
    "description": "Two-plugin fixture for --compute-hashes tests",
    "updated": "2026-05-09",
    "author": "test",
    "license": "MIT",
    "platforms": ["macos", "windows", "linux"]
  },
  "plugins": {
    "synths": [
      {
        "name": "FakeSynth",
        "description": "fixture",
        "urls": {
          "macos": {
            "url": "MOCKURL/fakesynth-mac.dmg",
            "filename": "fakesynth-mac.dmg"
          },
          "windows": {
            "url": "MOCKURL/fakesynth-win.exe",
            "filename": "fakesynth-win.exe"
          }
        },
        "version": "1.0.0",
        "formats": ["VST3"],
        "website": "https://example.invalid/fakesynth",
        "open_source": false
      }
    ]
  },
  "manual_download": []
}
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_compute_hashes_mode.py`:

```python
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
```

- [ ] **Step 3: Run the test, expect failure**

```bash
pytest tests/test_compute_hashes_mode.py -v
```

Expected: returncode != 0 because `--compute-hashes` is unknown. `argparse` exits 2 on unknown args.

- [ ] **Step 4: Add the CLI flags and `recompute_hashes()` to `scripts/download-plugins.py`**

In `main()`, add three new arguments to the parser. Insert these lines alongside the existing `parser.add_argument` calls (around line 339):

```python
    parser.add_argument('--compute-hashes', action='store_true',
                        help='Maintainer mode: compute SHA-256 for every URL and emit updated plugins.json')
    parser.add_argument('--in-place', action='store_true',
                        help='With --compute-hashes: rewrite plugins.json instead of stdout')
    parser.add_argument('--force-recompute', action='store_true',
                        help='With --compute-hashes: overwrite existing sha256 fields (otherwise preserved)')
    parser.add_argument('--plugins-json', type=str,
                        help='Path to plugins.json (defaults to ../plugins.json relative to script)')
```

Replace the existing `plugins_json = script_dir.parent / 'plugins.json'` (around line 349) with:

```python
    plugins_json = Path(args.plugins_json) if args.plugins_json else script_dir.parent / 'plugins.json'
```

Add the new helper function alongside the others (place it right after `compute_hash_for_url` from Task 2):

```python
def recompute_hashes(plugins_data: dict, force: bool) -> dict:
    """Walk plugins_data, compute SHA-256 for every URL, return updated dict.

    By default, existing sha256 fields are preserved (so manually-set
    'publisher' hashes are not clobbered). With force=True, every URL is
    recomputed and tagged 'self'.
    """
    for category_plugins in plugins_data.get('plugins', {}).values():
        for plugin in category_plugins:
            urls = plugin.get('urls', {})
            for plat, entry in urls.items():
                if not isinstance(entry, dict) or 'url' not in entry:
                    continue
                if entry.get('sha256') and not force:
                    continue
                digest = compute_hash_for_url(entry['url'])
                entry['sha256'] = digest
                entry['hash_source'] = 'self'
    return plugins_data
```

Add the `--compute-hashes` branch to `main()`, immediately after the `if args.list:` block (around line 358):

```python
    if args.compute_hashes:
        updated = recompute_hashes(plugins_data, args.force_recompute)
        rendered = json.dumps(updated, indent=2, ensure_ascii=False) + "\n"
        if args.in_place:
            plugins_json.write_text(rendered, encoding='utf-8')
        else:
            sys.stdout.write(rendered)
        return
```

- [ ] **Step 5: Run the test, expect pass**

```bash
pytest tests/test_compute_hashes_mode.py -v
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add tests/test_compute_hashes_mode.py tests/fixtures/plugins-empty-hashes.json scripts/download-plugins.py
git commit -m "feat: add --compute-hashes maintainer mode"
```

---

## Task 4: Backfill `plugins.json` with self-tier hashes (one-time maintainer step)

**Files:**
- Modify: `plugins.json`

**Why:** The verifying `download_file()` (Task 6) requires every entry to have a hash. Before that lands, every existing entry needs a real SHA-256.

**Important:** This task downloads ~1.5 GB of installers from real third-party servers. Run it once, on a trusted machine, with a stable network. The result must be committed verbatim — no editing.

**Special cases:** the dynamic Airwindows entry (which has no `urls.{macos,windows,linux}` dict — it uses the GitHub API) is skipped by `recompute_hashes()` because it lacks a `urls` block in the expected shape. We handle it in Task 5.

- [ ] **Step 1: Verify the script's `--list` still works against current data**

```bash
python3 scripts/download-plugins.py --list
```

Expected: prints all categories without errors. (Sanity check before mutating the file.)

- [ ] **Step 2: Run the backfill**

```bash
python3 scripts/download-plugins.py --compute-hashes --in-place
```

Expected: progress output (one HTTP fetch per URL per platform), no errors, takes several minutes. The script overwrites `plugins.json` with a version that has `sha256` + `hash_source: "self"` on every per-platform entry.

- [ ] **Step 3: Inspect the diff**

```bash
git diff plugins.json | head -60
```

Expected: every per-platform URL entry gains exactly two new fields. No URLs change. No `hash_source` other than `"self"`.

- [ ] **Step 4: Sanity-check a hash by hand**

Pick one entry, e.g. Surge XT macOS. Compute SHA-256 of its installer with the system tool and confirm it matches what the script wrote.

```bash
URL=$(python3 -c "import json; print(json.load(open('plugins.json'))['plugins']['synths'][0]['urls']['macos']['url'])")
EXPECTED=$(python3 -c "import json; print(json.load(open('plugins.json'))['plugins']['synths'][0]['urls']['macos']['sha256'])")
curl -sL "$URL" | shasum -a 256 | awk '{print $1}'
echo "Expected: $EXPECTED"
```

Expected: the two hashes match. (Use `sha256sum` on Linux instead of `shasum -a 256`.)

- [ ] **Step 5: Commit**

```bash
git add plugins.json
git commit -m "feat: backfill self-tier SHA-256 hashes for all plugins"
```

---

## Task 5: Pin Airwindows and remove the dynamic-fetch path

**Files:**
- Modify: `plugins.json` (replace Airwindows entry)
- Modify: `scripts/download-plugins.py` (delete `download_airwindows`, simplify `download_category`)

**Why:** The dynamic GitHub-API path (`download-plugins.py:107-151`) can't be hashed at PR-time because the URL targets a mutable tag. Pinning it removes the special case so every entry follows one rule.

- [ ] **Step 1: Find the current Airwindows DAWPlugin release**

Open <https://github.com/baconpaul/airwin2rack/releases/tag/DAWPlugin> in a browser. Note the URLs of the macOS, Windows, and Linux assets. (As of 2026-05, look for `*-macOS.dmg`, `*-win64.zip`, `*-linux.tar.gz`.) Record the exact URLs and pick a corresponding versioned tag if one is offered (e.g. `2025.06.01`); otherwise use the asset URLs directly with the `DAWPlugin` tag — note that this is mutable, so re-pin to a versioned release if available.

- [ ] **Step 2: Replace the Airwindows entry in `plugins.json`**

Find the existing entry (the one whose `name` contains "Airwindows"). It currently has either no `urls` block or a single URL pointing at the API. Replace it with the standard shape:

```json
{
  "name": "Airwindows Consolidated",
  "description": "350+ effects bundled in a single plugin",
  "urls": {
    "macos": {
      "url": "https://github.com/baconpaul/airwin2rack/releases/download/<TAG>/<MAC-ASSET>.dmg",
      "filename": "airwindows-consolidated-macOS.dmg"
    },
    "windows": {
      "url": "https://github.com/baconpaul/airwin2rack/releases/download/<TAG>/<WIN-ASSET>.zip",
      "filename": "airwindows-consolidated-win64.zip"
    },
    "linux": {
      "url": "https://github.com/baconpaul/airwin2rack/releases/download/<TAG>/<LINUX-ASSET>.tar.gz",
      "filename": "airwindows-consolidated-linux.tar.gz"
    }
  },
  "version": "<TAG>",
  "formats": ["VST3", "AU", "CLAP", "LV2"],
  "website": "https://www.airwindows.com/consolidated/",
  "open_source": true,
  "github": "https://github.com/baconpaul/airwin2rack"
}
```

Replace the four `<TAG>` and three asset placeholders with the real values found in Step 1.

- [ ] **Step 3: Compute hashes for the new Airwindows URLs**

```bash
python3 scripts/download-plugins.py --compute-hashes --in-place
```

Expected: only the Airwindows entry gains hashes (others were already populated in Task 4 and `--force-recompute` was not passed). Verify with `git diff plugins.json` — the diff should be confined to the Airwindows entry.

- [ ] **Step 4: Delete `download_airwindows()` and its call site**

In `scripts/download-plugins.py`:

Remove the entire `download_airwindows` function (lines roughly 107-151).

In `download_category`, remove the special-case block that calls it. The current code is:

```python
        # Skip Airwindows (handled separately)
        if 'airwindows' in name.lower():
            download_airwindows(download_dir, plat)
            continue
```

Delete those four lines. Airwindows now flows through the normal `get_plugin_url` + `download_file` path.

- [ ] **Step 5: Smoke-test the script**

```bash
python3 scripts/download-plugins.py --list
```

Expected: no errors, Airwindows still appears in the listing.

- [ ] **Step 6: Commit**

```bash
git add plugins.json scripts/download-plugins.py
git commit -m "feat: pin Airwindows release, remove dynamic-fetch path"
```

---

## Task 6: Implement verifying `download_file()` (TDD)

**Files:**
- Create: `tests/test_download_verify.py`
- Create: `tests/fixtures/plugins-with-hashes.json`
- Modify: `scripts/download-plugins.py` (rewrite `download_file()`, update `download_category` callers)

**Why:** This is the load-bearing change — the actual verification at download time.

- [ ] **Step 1: Create the fixture `tests/fixtures/plugins-with-hashes.json`**

Test code substitutes `MOCKURL` and `MAC_HASH`/`WIN_HASH` placeholders before running.

```json
{
  "meta": {
    "name": "Test Fixture",
    "version": "0.0.0",
    "description": "Two-plugin fixture with pre-populated hashes",
    "updated": "2026-05-09",
    "author": "test",
    "license": "MIT",
    "platforms": ["macos", "windows", "linux"]
  },
  "plugins": {
    "synths": [
      {
        "name": "FakeSynth",
        "description": "fixture",
        "urls": {
          "macos": {
            "url": "MOCKURL/fakesynth-mac.dmg",
            "filename": "fakesynth-mac.dmg",
            "sha256": "MAC_HASH",
            "hash_source": "self"
          }
        },
        "version": "1.0.0",
        "formats": ["VST3"],
        "website": "https://example.invalid/fakesynth",
        "open_source": false
      }
    ]
  },
  "manual_download": []
}
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_download_verify.py`:

```python
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
```

- [ ] **Step 3: Run the tests, expect failure**

```bash
pytest tests/test_download_verify.py -v
```

Expected: failures complaining about `ChecksumMismatch` not existing or about `download_file` having the wrong signature.

- [ ] **Step 4: Define `ChecksumMismatch` and rewrite `download_file()`**

In `scripts/download-plugins.py`, near the top (alongside the other top-level definitions, e.g. right after the `Colors` class):

```python
class ChecksumMismatch(Exception):
    """Raised when a downloaded file's SHA-256 does not match plugins.json."""

    def __init__(self, name: str, expected: str, actual: str) -> None:
        super().__init__(f"{name}: expected {expected}, got {actual}")
        self.name = name
        self.expected = expected
        self.actual = actual
```

Replace the existing `download_file()` (lines 76-105) with the verifying version:

```python
def download_file(url, filepath, name, expected_sha256, hash_source):
    """Download `url` to `filepath`, verifying SHA-256 in a single I/O pass.

    On hash mismatch, removes the partial/cached file and raises
    ChecksumMismatch. On a cached-file hit (filepath already exists), the
    file is re-hashed before being trusted; if it doesn't match, the cached
    file is deleted and the download proceeds normally.
    """
    if filepath.exists():
        h_existing = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h_existing.update(chunk)
        if h_existing.hexdigest() == expected_sha256:
            print(f"  {C.YELLOW}⏭{C.NC}  {name} - already verified ({hash_source})")
            return True
        # Cached file is bad — delete and fall through to re-download.
        filepath.unlink()
        print(f"  {C.YELLOW}⚠{C.NC}  {name} - cached file failed verification, redownloading")

    print(f"  {C.CYAN}⬇{C.NC}  Downloading {name}...")

    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; VST-Downloader/1.0)'
    })

    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(req, timeout=60) as response, open(filepath, 'wb') as f:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
    except urllib.error.HTTPError as e:
        if filepath.exists():
            filepath.unlink()
        print(f"  {C.RED}✗{C.NC}  {name} - HTTP error {e.code}")
        return False
    except urllib.error.URLError as e:
        if filepath.exists():
            filepath.unlink()
        print(f"  {C.RED}✗{C.NC}  {name} - connection error: {e.reason}")
        return False

    actual = h.hexdigest()
    if actual != expected_sha256:
        filepath.unlink()
        print(f"  {C.RED}✗{C.NC}  {name} - HASH MISMATCH")
        print(f"      expected: {expected_sha256}")
        print(f"      actual:   {actual}")
        raise ChecksumMismatch(name, expected_sha256, actual)

    print(f"  {C.GREEN}✓{C.NC}  {name} - verified ({hash_source})")
    return True
```

- [ ] **Step 5: Update `download_category()` to pass the new args**

In `scripts/download-plugins.py`, replace the body of the for-loop in `download_category` so that it reads the hash + source out of the URL entry. The current code is:

```python
        url, filename = get_plugin_url(plugin, plat)

        if not url:
            print(f"  {C.YELLOW}⏭{C.NC}  {name} - not available for {plat}")
            continue

        if not filename:
            filename = url.split('/')[-1].split('?')[0]
            filename = urllib.request.unquote(filename)

        filepath = download_dir / filename

        if not download_file(url, filepath, name):
            failed += 1
```

Change `get_plugin_url` to return the full URL entry (or `None`) so we can pull the hash out of it. Replace the body of `get_plugin_url` (around line 172) with:

```python
def get_plugin_url(plugin, plat):
    """Get the URL entry dict for the current platform.

    Returns a dict with keys 'url', 'filename', 'sha256', 'hash_source'
    or None if the plugin is unavailable for this platform.
    """
    urls = plugin.get('urls', {})
    entry = urls.get(plat)
    if isinstance(entry, dict) and entry.get('url'):
        return entry
    return None
```

This drops the legacy `url_macos` / fallback paths — they were never used after the v2 schema landed. The fixture and the production `plugins.json` both use the `urls.<plat>` dict shape.

Then update the loop in `download_category` (around line 212):

```python
    for plugin in plugins:
        name = plugin.get('name', 'Unknown')
        entry = get_plugin_url(plugin, plat)

        if entry is None:
            print(f"  {C.YELLOW}⏭{C.NC}  {name} - not available for {plat}")
            continue

        url = entry['url']
        filename = entry.get('filename') or urllib.request.unquote(url.split('/')[-1].split('?')[0])
        filepath = download_dir / filename

        if not download_file(url, filepath, name, entry['sha256'], entry['hash_source']):
            failed += 1
```

- [ ] **Step 6: Update `list_plugins()` for the new `get_plugin_url` return shape**

In `scripts/download-plugins.py`, `list_plugins` currently has this loop body (around line 296):

```python
            url, _ = get_plugin_url(plugin, plat)

            if url:
                print(f"  • {name}")
            else:
                print(f"  • {name} {C.YELLOW}(not available for {plat}){C.NC}")
```

Change it to use the new entry-dict return value:

```python
            entry = get_plugin_url(plugin, plat)

            if entry is not None:
                print(f"  • {name}")
            else:
                print(f"  • {name} {C.YELLOW}(not available for {plat}){C.NC}")
```

- [ ] **Step 7: Wrap `main()` to convert `ChecksumMismatch` into a non-zero exit**

In `main()`, wrap the `for category in categories: download_category(...)` loop:

```python
    failed = 0
    try:
        for category in categories:
            failed += download_category(plugins_data, category, download_dir, plat)
    except ChecksumMismatch as e:
        print(f"\n{C.RED}HASH MISMATCH detected for {e.name}.{C.NC}")
        print(f"{C.RED}Aborting. The bad file has been deleted.{C.NC}")
        sys.exit(1)
```

- [ ] **Step 8: Run the tests, expect pass**

```bash
pytest tests/test_download_verify.py -v
```

Expected: `4 passed`.

- [ ] **Step 9: Run all tests so far and verify --list still works**

```bash
pytest tests/ -v
python3 scripts/download-plugins.py --list
```

Expected: 7 tests passed (1 + 2 + 4). The `--list` output enumerates every plugin without errors (this catches the `list_plugins` regression that step 6 prevents).

- [ ] **Step 10: Commit**

```bash
git add tests/test_download_verify.py tests/fixtures/plugins-with-hashes.json scripts/download-plugins.py
git commit -m "feat: stream-verify SHA-256 of every plugin download"
```

---

## Task 7: Add JSON schema and schema-validation test

**Files:**
- Create: `schemas/plugins.schema.json`
- Create: `tests/test_schema.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema.py`:

```python
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
```

- [ ] **Step 2: Run the tests, expect failure**

```bash
pytest tests/test_schema.py -v
```

Expected: `FileNotFoundError` (no schemas/plugins.schema.json yet).

- [ ] **Step 3: Create `schemas/plugins.schema.json`**

```bash
mkdir -p schemas
```

Create `schemas/plugins.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "free-vst-plugins plugins.json",
  "type": "object",
  "required": ["meta", "plugins"],
  "properties": {
    "meta": {
      "type": "object",
      "required": ["name", "version", "description", "updated", "author", "license", "platforms"],
      "additionalProperties": true
    },
    "plugins": {
      "type": "object",
      "additionalProperties": {
        "type": "array",
        "items": { "$ref": "#/$defs/plugin" }
      }
    },
    "manual_download": {
      "type": "array"
    }
  },
  "$defs": {
    "plugin": {
      "type": "object",
      "required": ["name", "urls"],
      "properties": {
        "name": { "type": "string" },
        "urls": {
          "type": "object",
          "minProperties": 1,
          "additionalProperties": false,
          "properties": {
            "macos":   { "$ref": "#/$defs/urlEntry" },
            "windows": { "$ref": "#/$defs/urlEntry" },
            "linux":   { "$ref": "#/$defs/urlEntry" }
          }
        }
      },
      "additionalProperties": true
    },
    "urlEntry": {
      "type": "object",
      "required": ["url", "filename", "sha256", "hash_source"],
      "properties": {
        "url":      { "type": "string", "format": "uri" },
        "filename": { "type": "string", "minLength": 1 },
        "sha256":   { "type": "string", "pattern": "^[a-f0-9]{64}$" },
        "hash_source": { "enum": ["publisher", "self"] }
      },
      "additionalProperties": false
    }
  }
}
```

- [ ] **Step 4: Run the tests, expect pass**

```bash
pytest tests/test_schema.py -v
```

Expected: `3 passed`. If `test_plugins_json_validates_against_schema` fails, Tasks 4 and 5 left an entry without hashes — go back and fix that data, do not loosen the schema.

- [ ] **Step 5: Commit**

```bash
git add schemas/plugins.schema.json tests/test_schema.py
git commit -m "feat: add JSON schema enforcing sha256 + hash_source on every URL"
```

---

## Task 8: Wire schema validation and fix toothless CI

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add schema-validation step to the `lint` job**

In `.github/workflows/ci.yml`, immediately after the existing "Validate JSON" step (at line 26), add a new step:

```yaml
      - name: Validate plugins.json against schema
        run: |
          pip install jsonschema
          python -c "import json, jsonschema; \
            schema = json.load(open('schemas/plugins.schema.json')); \
            data = json.load(open('plugins.json')); \
            jsonschema.validate(instance=data, schema=schema); \
            print('plugins.json validates against schema')"
```

- [ ] **Step 2: Remove `|| true` from the ruff line**

Change line 31 of `.github/workflows/ci.yml` from:

```yaml
          ruff check scripts/download-plugins.py || true
```

to:

```yaml
          ruff check scripts/download-plugins.py
```

- [ ] **Step 3: Uncomment the URL-check exit**

In `.github/workflows/ci.yml`, find the URL-check step (around line 148). Change:

```python
              # Don't fail the build for URL issues (they may be temporary)
              # sys.exit(1)
```

to:

```python
              sys.exit(1)
```

(Remove both comment lines AND uncomment the exit.)

- [ ] **Step 4: Add a pytest step to the `test-script` matrix job**

In the `test-script` job, after the existing "Test platform detection" step (around line 80), add:

```yaml
      - name: Run unit + integration tests
        run: |
          pip install pytest jsonschema
          pytest tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: validate schema, run tests, remove toothless || true and silent URL failures"
```

---

## Task 9: Local end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Run all tests**

```bash
pip install pytest jsonschema
pytest tests/ -v
```

Expected: 10 tests passed (1 + 2 + 4 + 3).

- [ ] **Step 2: Lint with ruff**

```bash
pip install ruff
ruff check scripts/download-plugins.py
```

Expected: no errors. Fix any reported issues — don't suppress them, since CI will now fail on them.

- [ ] **Step 3: Smoke-test the CLI**

```bash
python3 scripts/download-plugins.py --help
python3 scripts/download-plugins.py --list
```

Expected: both run without errors.

- [ ] **Step 4: Smoke-test a single download against the real upstream**

Pick one plugin (e.g., the smallest open-source synth for your OS). Download it and confirm the verification line prints.

```bash
python3 scripts/download-plugins.py --synths --dir /tmp/vst-test
```

Expected: each line ends with `verified (self)`.

- [ ] **Step 5: Negative test — flip a hash and confirm abort**

```bash
# Save the real plugins.json
cp plugins.json plugins.json.bak

# Corrupt the first entry's macos sha256 (replace one hex digit).
python3 -c "
import json
d = json.load(open('plugins.json'))
e = d['plugins']['synths'][0]['urls']['macos']
e['sha256'] = 'f' + e['sha256'][1:]
json.dump(d, open('plugins.json','w'), indent=2)
"

# Try a fresh download, expect abort with non-zero exit.
rm -rf /tmp/vst-corrupt
python3 scripts/download-plugins.py --synths --dir /tmp/vst-corrupt
echo "exit code: $?"

# Restore plugins.json
mv plugins.json.bak plugins.json
```

Expected output: `HASH MISMATCH` printed in red, exit code != 0, and `/tmp/vst-corrupt/` does not contain the bad file.

- [ ] **Step 6: Final commit (only if any cleanup was needed)**

If steps 2 or 3 surfaced anything that needed fixing:

```bash
git add -p
git commit -m "fix: address ruff/CI feedback from local run"
```

Otherwise, no commit needed.

---

## Summary of commits this plan produces

1. `test: add pytest harness with mock HTTP server fixture`
2. `feat: add compute_hash_for_url() helper`
3. `feat: add --compute-hashes maintainer mode`
4. `feat: backfill self-tier SHA-256 hashes for all plugins`
5. `feat: pin Airwindows release, remove dynamic-fetch path`
6. `feat: stream-verify SHA-256 of every plugin download`
7. `feat: add JSON schema enforcing sha256 + hash_source on every URL`
8. `ci: validate schema, run tests, remove toothless || true and silent URL failures`
9. (optional) `fix: address ruff/CI feedback from local run`

---

## Spec coverage check (self-review)

| Spec section | Implemented in |
|--------------|----------------|
| §1 Data shape (`sha256` + `hash_source` on every URL entry) | Tasks 4, 5 (data); Task 7 (schema enforcement) |
| §1 Replace dynamic Airwindows entry | Task 5 |
| §2 CI: schema validation step | Task 8 step 1 |
| §2 CI: remove `\|\| true` from ruff | Task 8 step 2 |
| §2 CI: uncomment `sys.exit(1)` in URL check | Task 8 step 3 |
| §3 Verifying `download_file()` (stream + hash, mismatch → unlink + raise) | Task 6 |
| §3 Cached-file re-verification | Task 6 (test in step 2, code in step 4) |
| §3 `main()` exits 1 on mismatch | Task 6 step 6, validated in test 4 of step 2 |
| §4 `--compute-hashes`, `--in-place`, `--force-recompute` | Task 3 |
| §4 Backfill at repo level | Task 4 |
| §4 Self-tier hashes only from this mode | Task 3 step 4 (`recompute_hashes` always tags `'self'`) |
| §5 Schema validation test | Task 7 |
| §5 Mismatch handling test | Task 6 (test 2) |
| §5 Re-verification test | Task 6 (test 3) |
| §5 Tests added to existing matrix | Task 8 step 4 |

No gaps.
