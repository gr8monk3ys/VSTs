# u-he Update Strategy (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `u-he:<ProductSlug>` value to `update_strategy` so `--check-updates` detects upstream version drift on the 2 u-he plugins (Tyrell N6, Zebralette) by scraping their product page HTML.

**Architecture:** A new `UHE_PRODUCTS` dict in `scripts/download-plugins.py` encodes per-product page URL, version regex, asset URL template, and per-platform suffix/extension. A new `detect_latest_for_uhe(product, page_url=None, dl_base=None)` mirrors `detect_latest_for_github` and returns the same `{tag, assets}` shape. `_parse_update_strategy`'s return value changes from `(repo, tag) | None` to a tagged tuple `('github', repo, tag) | ('u-he', product) | None`; the only caller (`check_updates`) updates accordingly to dispatch to the correct detect function.

**Tech Stack:** Python 3.9+ stdlib only at runtime (urllib, hashlib, json, argparse, re). Tests use the existing `mock_server` fixture to serve fake u-he product pages and binary downloads. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-05-09-uhe-update-strategy-design.md`

---

## File Structure

| Path | Status | Responsibility |
|------|--------|----------------|
| `scripts/download-plugins.py` | Modified | Add `UHE_PRODUCTS` dict and `detect_latest_for_uhe` function. Refactor `_parse_update_strategy` return shape. Update `check_updates` dispatcher. |
| `schemas/plugins.schema.json` | Modified | Extend `update_strategy.pattern` to also accept `u-he:<slug>`. |
| `plugins.json` | Modified | Add `update_strategy: "u-he:TyrellN6"` to Tyrell N6 entry; `update_strategy: "u-he:Zebralette"` to Zebralette entry. |
| `tests/test_check_updates.py` | Modified | Add unit tests for `detect_latest_for_uhe` and integration tests for u-he drift detection (read-only + apply). |
| `tests/test_schema.py` | Modified | Add one negative test: `update_strategy: "u-he:"` (empty product) is rejected. |

**Branch strategy:** all 5 tasks land on a new feature branch `feature/uhe-update-strategy` cut from current main (`147f483`). After Task 5 the branch merges back to main via the standard `superpowers:finishing-a-development-branch` flow.

---

## Task 1: Schema regex extension

**Files:**
- Modify: `schemas/plugins.schema.json`
- Modify: `tests/test_schema.py`

**Why first:** Backfilling `update_strategy: "u-he:..."` (Task 4) requires the schema to admit the new value. Doing schema first keeps `test_plugins_json_validates_against_schema` green throughout.

- [ ] **Step 1: Append a new failing schema test**

Append to `tests/test_schema.py` (after the existing Phase 1 tests that already cover the github form):

```python
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
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_schema.py -v
```

Expected: `test_schema_accepts_uhe_strategy` fails (ValidationError) because the current pattern only admits `github:...` strings. `test_schema_rejects_uhe_strategy_with_empty_product` may pass coincidentally (empty doesn't match the github pattern either). Confirm both states.

- [ ] **Step 3: Update the schema**

Edit `schemas/plugins.schema.json`. The current `update_strategy.pattern` is `^github:[\\w.-]+/[\\w.-]+(@[\\w.-]+)?$`. Replace with:

```json
"update_strategy": {
  "type": "string",
  "pattern": "^(github:[\\w.-]+/[\\w.-]+(@[\\w.-]+)?|u-he:[\\w.-]+)$"
}
```

This is `^(github_form|uhe_form)$`. Both alternatives require at least one `[\w.-]` character after their prefix, so `github:` and `u-he:` (empty) both fail.

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_schema.py -v
```

Expected: 7 passed (5 from Phase 1 + 2 new).

- [ ] **Step 5: Commit**

```bash
git add schemas/plugins.schema.json tests/test_schema.py
git commit -m "feat: extend update_strategy schema to admit u-he:<slug>"
```

---

## Task 2: `UHE_PRODUCTS` + `detect_latest_for_uhe` (TDD)

**Files:**
- Modify: `scripts/download-plugins.py`
- Modify: `tests/test_check_updates.py`

**Why second:** This is the new vertical of behavior — fetching a u-he product page, extracting the version, building asset URLs. Pure function, easily mockable. Asset matching (already in place from Phase 1) and dispatcher (Task 3) both depend on this.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_check_updates.py`:

```python
TYRELL_N6_PAGE_HTML = (
    b"<html><body><h1>TyrellN6</h1>"
    b"<p>TyrellN6 Beta 3.0.1 (revision 17000) released April 1, 2026.</p>"
    b"</body></html>"
)


def test_detect_latest_for_uhe_parses_version_and_builds_asset_urls(mock_server) -> None:
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
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_check_updates.py -v
```

Expected: `AttributeError: module 'dlp' has no attribute 'detect_latest_for_uhe'` for all three new tests.

- [ ] **Step 3: Add `UHE_PRODUCTS` and `detect_latest_for_uhe` in `scripts/download-plugins.py`**

Place both alongside the other check-updates helpers. The natural spot is immediately after `detect_latest_for_github` and before `find_matching_asset` — keep all detection functions clustered.

```python
UHE_PRODUCTS = {
    'TyrellN6': {
        'page_url': 'https://u-he.com/products/tyrelln6/',
        'version_re': re.compile(r'TyrellN6\s+(?:Beta\s+)?(\d+)\.(\d+)\.(\d+)\s*\(revision\s+(\d+)\)'),
        'asset_template': '{dl_base}/releases/TyrellN6_{vcode}_public_beta_{rev}_{platform}.{ext}',
        'platforms': {
            'macos':   ('Mac',   'zip'),
            'windows': ('Win',   'zip'),
            'linux':   ('Linux', 'tar.xz'),
        },
    },
    'Zebralette': {
        'page_url': 'https://u-he.com/products/zebralette/',
        'version_re': re.compile(r'Zebralette\s+(\d+)\.(\d+)\.(\d+)\s*\(revision\s+(\d+)\)'),
        'asset_template': '{dl_base}/releases/Zebra_Legacy_{vcode}_{rev}_{platform}.{ext}',
        'platforms': {
            'macos':   ('Mac',   'zip'),
            'windows': ('Win',   'zip'),
            'linux':   ('Linux', 'zip'),
        },
    },
}


def detect_latest_for_uhe(product: str, page_url: str | None = None,
                          dl_base: str | None = None) -> dict:
    """Fetch a u-he product page and return the latest release as
    {'tag': str, 'assets': [{'name', 'url', 'size': 0}, ...]}.

    The 'tag' is f'{major}.{minor}.{patch}-r{rev}', stable string-comparable.
    Asset 'size' is 0 — u-he doesn't expose sizes from a list endpoint.

    page_url and dl_base override the values from UHE_PRODUCTS for testing.

    Raises:
      ValueError if `product` is not in UHE_PRODUCTS.
      RuntimeError if the page doesn't contain a recognizable version string.
      urllib.error.HTTPError / URLError on network problems (propagated).
    """
    if product not in UHE_PRODUCTS:
        raise ValueError(f"unknown u-he product: {product!r}")

    cfg = UHE_PRODUCTS[product]
    url = page_url or cfg['page_url']
    base = dl_base or 'https://dl.u-he.com'

    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; VST-Downloader/1.0)',
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read().decode('utf-8', errors='replace')

    m = cfg['version_re'].search(body)
    if not m:
        raise RuntimeError(
            f"u-he page does not contain a recognizable version string for {product}"
        )
    major, minor, patch, rev = m.group(1), m.group(2), m.group(3), m.group(4)
    vcode = f"{major}{minor}{patch}"
    tag = f"{major}.{minor}.{patch}-r{rev}"

    assets = []
    for plat, (plat_name, ext) in cfg['platforms'].items():
        asset_url = cfg['asset_template'].format(
            dl_base=base, vcode=vcode, rev=rev, platform=plat_name, ext=ext,
        )
        # Strip the dl_base prefix to derive the asset filename.
        name = asset_url.rsplit('/', 1)[-1]
        assets.append({'name': name, 'url': asset_url, 'size': 0})

    return {'tag': tag, 'assets': assets}
```

The `dl_base` placeholder in `asset_template` is a deliberate choice: tests pass a mock server URL, so the script ends up requesting `http://127.0.0.1:PORT/releases/TyrellN6_301_public_beta_17000_Mac.zip` (which the mock server can register and serve), while production passes nothing and lands at `https://dl.u-he.com/...`.

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_check_updates.py -v
```

Expected: 13 passed (10 from Phase 1 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add tests/test_check_updates.py scripts/download-plugins.py
git commit -m "feat: add detect_latest_for_uhe() and UHE_PRODUCTS dict"
```

---

## Task 3: `_parse_update_strategy` refactor + `check_updates` dispatcher (TDD)

**Files:**
- Modify: `scripts/download-plugins.py`
- Modify: `tests/test_check_updates.py`

**Why now:** With `detect_latest_for_uhe` in place, the dispatcher can call it. The `_parse_update_strategy` return shape change is breaking but contained — the only existing caller is `check_updates`.

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/test_check_updates.py`:

```python
def test_check_updates_drift_for_uhe_plugin(mock_server, fixtures_dir, tmp_path) -> None:
    # Fake page advertises 3.0.1-r17000; fixture is pinned at 3.0.0-r16976.
    mock_server.add("/products/tyrelln6/", TYRELL_N6_PAGE_HTML)

    json_path = tmp_path / "plugins.json"
    fixture = {
        "meta": {
            "name": "Test Fixture", "version": "0.0.0", "description": "uhe drift",
            "updated": "2026-05-09", "author": "test", "license": "MIT",
            "platforms": ["macos"],
        },
        "plugins": {"synths": [{
            "name": "Tyrell N6",
            "description": "fixture",
            "update_strategy": "u-he:TyrellN6",
            "urls": {"macos": {
                "url": "https://example.invalid/TyrellN6_300_public_beta_16976_Mac.zip",
                "filename": "TyrellN6_300_public_beta_16976_Mac.zip",
                "sha256": "0" * 64,
                "hash_source": "self",
            }},
            "version": "3.0.0",
            "formats": ["VST3"],
            "website": "https://u-he.com/products/tyrelln6/",
            "open_source": False,
        }]},
        "manual_download": [],
    }
    json_path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    original_text = json_path.read_text(encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check-updates",
         "--plugins-json", str(json_path)],
        capture_output=True, text=True, check=False,
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


def test_check_updates_apply_for_uhe_plugin(mock_server, fixtures_dir, tmp_path) -> None:
    mock_server.add("/products/tyrelln6/", TYRELL_N6_PAGE_HTML)

    # The new asset bytes the apply path will fetch + hash.
    mac_body = b"new-mac-tyrelln6"
    mock_server.add("/releases/TyrellN6_301_public_beta_17000_Mac.zip", mac_body)

    json_path = tmp_path / "plugins.json"
    fixture = {
        "meta": {
            "name": "Test Fixture", "version": "0.0.0", "description": "uhe apply",
            "updated": "2026-05-09", "author": "test", "license": "MIT",
            "platforms": ["macos"],
        },
        "plugins": {"synths": [{
            "name": "Tyrell N6",
            "description": "fixture",
            "update_strategy": "u-he:TyrellN6",
            "urls": {"macos": {
                "url": "https://example.invalid/TyrellN6_300_public_beta_16976_Mac.zip",
                "filename": "TyrellN6_300_public_beta_16976_Mac.zip",
                "sha256": "0" * 64,
                "hash_source": "self",
            }},
            "version": "3.0.0",
            "formats": ["VST3"],
            "website": "https://u-he.com/products/tyrelln6/",
            "open_source": False,
        }]},
        "manual_download": [],
    }
    json_path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check-updates", "--apply",
         "--plugins-json", str(json_path)],
        capture_output=True, text=True, check=False,
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
    assert mac["url"] == mock_server.url_for("/releases/TyrellN6_301_public_beta_17000_Mac.zip")
    assert mac["sha256"] == hashlib.sha256(mac_body).hexdigest()
    assert mac["hash_source"] == "self"
```

These tests use two new env vars (`VST_DLP_UHE_PAGE_URL_<Product>` and `VST_DLP_UHE_DL_BASE`) that the script will read in Step 3 below. The pattern mirrors `VST_DLP_GITHUB_API_BASE` from Phase 1 — production reads no env, tests inject overrides.

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_check_updates.py::test_check_updates_drift_for_uhe_plugin -v
```

Expected: failure because `_parse_update_strategy` returns `None` for `"u-he:TyrellN6"` (it only knows `github:` today), so the entry lands in `report['failures']` with reason "malformed update_strategy". The test asserts NEW VERSION in stdout, which won't appear.

- [ ] **Step 3: Refactor `_parse_update_strategy` and update `check_updates`**

Replace the existing `_parse_update_strategy` (returns `tuple[str, str | None] | None` today) with the tagged-tuple version:

```python
def _parse_update_strategy(strategy: str):
    """Parse known update_strategy values.

    Returns one of:
      ('github', repo: str, tag: str | None)
      ('u-he', product: str)
      None  if the value is missing or unrecognized.
    """
    if not strategy:
        return None
    if strategy.startswith('github:'):
        rest = strategy[len('github:'):]
        if not rest:
            return None
        if '@' in rest:
            repo, tag = rest.rsplit('@', 1)
            if not repo or not tag:
                return None
            return ('github', repo, tag)
        return ('github', rest, None)
    if strategy.startswith('u-he:'):
        product = strategy[len('u-he:'):]
        if not product:
            return None
        return ('u-he', product)
    return None
```

Find the `check_updates` function and replace the dispatch block. The current Phase 1 code is:

```python
            parsed = _parse_update_strategy(strategy)
            if not parsed:
                report['failures'].append({
                    'name': name, 'category': category,
                    'reason': f'malformed update_strategy: {strategy}',
                })
                continue

            repo, tag = parsed

            try:
                release = detect_latest_for_github(repo, tag=tag, api_base=api_base)
            except urllib.error.HTTPError as e:
                report['failures'].append({...})
                continue
            except urllib.error.URLError as e:
                report['failures'].append({...})
                continue

            new_tag = release['tag']
            old_tag = tag if tag else current_version
```

Replace with the dispatched version:

```python
            parsed = _parse_update_strategy(strategy)
            if not parsed:
                report['failures'].append({
                    'name': name, 'category': category,
                    'reason': f'malformed update_strategy: {strategy}',
                })
                continue

            try:
                if parsed[0] == 'github':
                    _, repo, tag = parsed
                    release = detect_latest_for_github(repo, tag=tag, api_base=api_base)
                    old_tag = tag if tag else current_version
                elif parsed[0] == 'u-he':
                    _, product = parsed
                    page_url = os.environ.get(f'VST_DLP_UHE_PAGE_URL_{product}')
                    dl_base = os.environ.get('VST_DLP_UHE_DL_BASE')
                    release = detect_latest_for_uhe(product, page_url=page_url, dl_base=dl_base)
                    # u-he tags carry a revision (e.g. "3.0.1-r17000") that won't
                    # substring-match current_version (e.g. "3.0.0"); Strategy A
                    # skips and Strategy B does the matching.
                    old_tag = current_version
                    tag = None  # for the rolling-tag display logic below
                else:
                    raise RuntimeError(f"unknown strategy kind: {parsed[0]}")
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError, RuntimeError) as e:
                report['failures'].append({
                    'name': name, 'category': category,
                    'reason': f'detection failed: {e}',
                })
                continue

            new_tag = release['tag']
```

The two new env vars (`VST_DLP_UHE_PAGE_URL_<Product>` and `VST_DLP_UHE_DL_BASE`) are only consumed by tests; production reads neither and uses the values from `UHE_PRODUCTS`.

- [ ] **Step 4: Run, expect pass**

```bash
pytest tests/test_check_updates.py -v
```

Expected: 15 passed (13 from Tasks 1-2 + 2 new integration tests).

- [ ] **Step 5: Run all tests so far to make sure Phase 1 still works**

```bash
pytest tests/ -v 2>&1 | tail -10
```

Expected: 26 passed (23 from main + 3 from this branch's Tasks 1-2 + Task 3's 2 tests = wait, let me recount). Actually: 23 from main was after merging Phase 1; this branch adds 2 from Task 1 (schema), 3 from Task 2 (detect), 2 from Task 3 (integration) = 7 new. Total: 23 + 7 = 30. Confirm by counting actual output.

- [ ] **Step 6: Commit**

```bash
git add scripts/download-plugins.py tests/test_check_updates.py
git commit -m "feat: dispatch check_updates by strategy kind, supporting u-he"
```

---

## Task 4: Backfill `update_strategy` on Tyrell N6 + Zebralette

**Files:**
- Modify: `plugins.json`

**Why fourth:** The schema admits the value (Task 1), the runtime handles it (Tasks 2-3). The data can land cleanly now.

- [ ] **Step 1: Add `update_strategy` to the Tyrell N6 entry**

Find `"name": "Tyrell N6"` in `plugins.json`. Add a line `"update_strategy": "u-he:TyrellN6",` immediately after the `"description"` line:

```json
      {
        "name": "Tyrell N6",
        "description": "u-he analog synth - 580+ presets, native binaries",
        "update_strategy": "u-he:TyrellN6",
        "urls": { ... }
```

- [ ] **Step 2: Add `update_strategy` to the Zebralette entry**

Find `"name": "Zebralette"`. Add `"update_strategy": "u-he:Zebralette",` in the same position.

- [ ] **Step 3: Verify schema still validates**

```bash
pytest tests/test_schema.py::test_plugins_json_validates_against_schema -v
```

Expected: PASS.

- [ ] **Step 4: Run `--list` smoke test to confirm nothing's broken**

```bash
python3 scripts/download-plugins.py --list 2>&1 | head -30
```

Expected: Tyrell N6 and Zebralette still appear in the synths section.

- [ ] **Step 5: Commit**

```bash
git add plugins.json
git commit -m "feat: backfill update_strategy on the 2 u-he plugin entries"
```

---

## Task 5: Local end-to-end smoke test (no commit unless cleanup needed)

**Files:** none (verification only).

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v
```

Expected: 30 passed.

- [ ] **Step 2: Lint**

```bash
ruff check scripts/download-plugins.py
```

Expected: clean.

- [ ] **Step 3: Schema validation against current data**

```bash
python3 -c "import json, jsonschema; jsonschema.validate(instance=json.load(open('plugins.json')), schema=json.load(open('schemas/plugins.schema.json'))); print('schema OK')"
```

Expected: `schema OK`.

- [ ] **Step 4: Run `--check-updates` against the real u-he website**

```bash
GITHUB_TOKEN=$(gh auth token) python3 scripts/download-plugins.py --check-updates 2>&1 | head -50
```

Expected: Tyrell N6 and Zebralette now appear with concrete version strings (not "manual"). Whether they show "no update" or "NEW VERSION" depends on whether u-he has shipped newer builds since this manifest was last refreshed. Don't `--apply` from this step.

- [ ] **Step 5: Final commit (only if Steps 2-4 surfaced something to fix)**

If ruff or the smoke test surfaced anything fixable:

```bash
git add -p
git commit -m "fix: address local smoke-test feedback"
```

Otherwise no commit.

---

## Summary of commits this plan produces

1. `feat: extend update_strategy schema to admit u-he:<slug>`
2. `feat: add detect_latest_for_uhe() and UHE_PRODUCTS dict`
3. `feat: dispatch check_updates by strategy kind, supporting u-he`
4. `feat: backfill update_strategy on the 2 u-he plugin entries`
5. (optional) `fix: address local smoke-test feedback`

---

## Spec coverage check (self-review)

| Spec section | Implemented in |
|---|---|
| §1 New value family `u-he:<ProductSlug>` accepted by schema | Task 1 |
| §1 Schema regex `^(github_form|uhe_form)$` | Task 1 step 3 |
| §2 Initial coverage: TyrellN6 + Zebralette | Task 4 |
| §3 `UHE_PRODUCTS` dict with page_url, version_re, asset_template, platforms | Task 2 step 3 |
| §4 `detect_latest_for_uhe(product, page_url=None, dl_base=None)` returning `{tag, assets}` | Task 2 step 3 |
| §4 `vcode = f'{major}{minor}{patch}'` substitution | Task 2 step 3 |
| §4 Tag format `f'{major}.{minor}.{patch}-r{rev}'` | Task 2 step 3 |
| §5 `_parse_update_strategy` returns tagged tuple | Task 3 step 3 |
| §5 `check_updates` dispatches by parsed kind | Task 3 step 3 |
| §5 `old_tag = current_version` for u-he | Task 3 step 3 |
| §6 Reuses existing `find_matching_asset` | (no change required — verified by Task 3 integration tests) |
| §7 Failure mode: unknown product → `ValueError` → caught in dispatcher | Task 2 step 3 (raise) + Task 3 step 3 (except) |
| §7 Failure mode: regex no match → `RuntimeError` → caught | Task 2 step 3 (raise) + Task 3 step 3 (except) |
| §7 Failure mode: HTTP error → caught | Task 3 step 3 (existing `except urllib.error.HTTPError` clause widened) |
| §8 3 new tests: detect parses, drift, apply | Tasks 2 (3 detect-level tests) + Task 3 (2 integration tests = 5 total) |
| §8 1 schema test extension (empty product) | Task 1 (2 schema tests added: accept and reject) |
| §9 No CI changes | confirmed — Phase 1's `--check-updates` step picks up u-he automatically |

No gaps.
