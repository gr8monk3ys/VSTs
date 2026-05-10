# Stable-URL Hash Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third `update_strategy` family — `stable-url` — that detects content drift on plugins whose URL never changes by re-hashing the bytes and comparing to the stored sha256. Auto-applies the new hash on `--apply`.

**Architecture:** Extend the existing `_parse_update_strategy` / `check_updates` / `apply_updates` pipeline with a third branch. The detector fetches each platform's URL, re-hashes, and emits a different update-row shape (carrying new hashes, since URL/filename/version don't change). `apply_updates` dispatches on a new `'strategy'` field in the update row.

**Tech Stack:** Python 3.10+ stdlib (urllib, hashlib, json, http.server for tests), pytest. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-09-stable-url-hash-refresh-design.md`

---

## File Structure

| File | Responsibility | Change type |
|---|---|---|
| `scripts/download-plugins.py` | Add `detect_drift_for_stable_url()`, extend `_parse_update_strategy`, add a `'stable-url'` branch in `check_updates`, add a strategy-dispatching branch in `apply_updates`, extend `print_check_updates_report` for the drift display | Modify |
| `schemas/plugins.schema.json` | Extend `update_strategy.pattern` to accept the literal `stable-url` | Modify |
| `plugins.json` | Add `update_strategy: "stable-url"` to 5 entries | Modify |
| `tests/test_check_updates.py` | Add 4 tests (parser, detector, drift integration, no-drift integration, apply integration) | Modify |
| `tests/test_schema.py` | Add 1 positive test for `stable-url` and 1 negative test for `stable-url:slug` | Modify |

**Branch:** Work on a feature branch off `main` named `phase-3-stable-url`. Worktrees not required since this is a single-session subagent run; the feature-branch convention from prior phases applies.

---

## Task 1: Extend schema regex to accept `stable-url`

**Files:**
- Modify: `schemas/plugins.schema.json:31`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing positive test**

Existing `tests/test_schema.py` uses inline dict literals (no shared fixtures) — mirror that pattern. Add at the end of the file:

```python
def test_schema_accepts_stable_url_strategy() -> None:
    schema = json.loads((REPO / "schemas" / "plugins.schema.json").read_text(encoding="utf-8"))
    good = {
        "meta": {
            "name": "x", "version": "0", "description": "x",
            "updated": "2026-05-09", "author": "x", "license": "MIT",
            "platforms": ["macos"],
        },
        "plugins": {"synths": [{
            "name": "x", "description": "x",
            "update_strategy": "stable-url",
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


def test_schema_rejects_stable_url_with_slug() -> None:
    schema = json.loads((REPO / "schemas" / "plugins.schema.json").read_text(encoding="utf-8"))
    bad = {
        "meta": {
            "name": "x", "version": "0", "description": "x",
            "updated": "2026-05-09", "author": "x", "license": "MIT",
            "platforms": ["macos"],
        },
        "plugins": {"synths": [{
            "name": "x", "description": "x",
            "update_strategy": "stable-url:foo",
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

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_schema.py::test_schema_accepts_stable_url_strategy tests/test_schema.py::test_schema_rejects_stable_url_with_slug -v`

Expected: First test FAILS (regex doesn't accept `stable-url`); second test PASSES vacuously (also rejects `stable-url:foo`) — re-run after the regex change to confirm it still rejects.

- [ ] **Step 3: Update the schema regex**

In `schemas/plugins.schema.json`, change line 31:

From:
```json
"pattern": "^(github:[\\w.-]+/[\\w.-]+(@[\\w.-]+)?|u-he:[\\w.-]+)$"
```

To:
```json
"pattern": "^(github:[\\w.-]+/[\\w.-]+(@[\\w.-]+)?|u-he:[\\w.-]+|stable-url)$"
```

The new alternative is a literal `stable-url` (no slug). The trailing `$` anchors prevent `stable-url:anything` from matching.

- [ ] **Step 4: Run schema tests to verify they pass**

Run: `pytest tests/test_schema.py -v`

Expected: All schema tests PASS, including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add schemas/plugins.schema.json tests/test_schema.py
git commit -m "schema: accept update_strategy: stable-url"
```

---

## Task 2: Recognize `stable-url` in `_parse_update_strategy`

**Files:**
- Modify: `scripts/download-plugins.py:360-385`
- Test: `tests/test_check_updates.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_check_updates.py` (in the section with the other parser tests, if any; otherwise add at the end of the parser-related block):

```python
def test_parse_update_strategy_recognizes_stable_url():
    assert dlp._parse_update_strategy("stable-url") == ("stable-url",)


def test_parse_update_strategy_rejects_stable_url_with_slug():
    # `stable-url:something` is not a recognized variant — must be exactly "stable-url".
    assert dlp._parse_update_strategy("stable-url:foo") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_check_updates.py::test_parse_update_strategy_recognizes_stable_url tests/test_check_updates.py::test_parse_update_strategy_rejects_stable_url_with_slug -v`

Expected: First test FAILS (returns `None`); second test PASSES vacuously.

- [ ] **Step 3: Add the recognition branch**

In `scripts/download-plugins.py`, modify `_parse_update_strategy` (currently at line 360-385). Add the new branch *before* the final `return None`:

```python
def _parse_update_strategy(strategy: str):
    """Parse known update_strategy values.

    Returns one of:
      ('github', repo: str, tag: str | None)
      ('u-he', product: str)
      ('stable-url',)
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
    if strategy == 'stable-url':
        return ('stable-url',)
    return None
```

The check is `==` (exact match), so `stable-url:foo` falls through to `return None`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_check_updates.py -v -k "parse_update_strategy"`

Expected: All parser tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/download-plugins.py tests/test_check_updates.py
git commit -m "feat: recognize stable-url in _parse_update_strategy"
```

---

## Task 3: Implement `detect_drift_for_stable_url`

**Files:**
- Modify: `scripts/download-plugins.py` (add new function near the other `detect_latest_for_*` functions, around line 310)
- Test: `tests/test_check_updates.py`

- [ ] **Step 1: Write the failing test for drift detection**

Add to `tests/test_check_updates.py`:

```python
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
```

If `hashlib` is not yet imported in the test file, add `import hashlib` at the top.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_check_updates.py::test_detect_drift_for_stable_url_flags_changed_bytes tests/test_check_updates.py::test_detect_drift_for_stable_url_no_drift_when_hash_matches -v`

Expected: Both FAIL with `AttributeError: module 'dlp' has no attribute 'detect_drift_for_stable_url'`.

- [ ] **Step 3: Implement `detect_drift_for_stable_url`**

In `scripts/download-plugins.py`, add this function immediately after `detect_latest_for_uhe` (before `find_matching_asset`, around line 308):

```python
def detect_drift_for_stable_url(entry: dict) -> dict:
    """Re-hash each platform URL in `entry` and report which platforms drifted.

    Used by the 'stable-url' update strategy. The vendor URL is assumed to be
    canonical (it never changes); the only signal that the upstream file has
    been swapped is its sha256 differing from what we stored.

    Returns:
      {
        'drift': bool,            # True if any platform's hash changed
        'platforms': {
          '<plat>': {
            'url': str,
            'old_sha256': str,
            'new_sha256': str,
            'changed': bool,
          },
          ...
        },
      }

    Raises:
      ValueError if `entry['urls']` is missing or empty, or if any URL serves
        text/html or application/json (the existing compute_hash_for_url guard
        — vendors sometimes replace a binary URL with a download-gate page,
        and silently re-hashing that HTML would be wrong).
      urllib.error.HTTPError / URLError on network failure.
    """
    urls = entry.get('urls') or {}
    platforms_with_url = {p: e for p, e in urls.items()
                          if isinstance(e, dict) and e.get('url')}
    if not platforms_with_url:
        raise ValueError(
            f"stable-url entry {entry.get('name', '<unknown>')!r} has no platforms with URLs"
        )

    out = {'drift': False, 'platforms': {}}
    for plat, urlentry in platforms_with_url.items():
        url = urlentry['url']
        stored = urlentry.get('sha256')
        if not stored:
            raise ValueError(
                f"stable-url entry {entry.get('name', '<unknown>')!r} platform "
                f"{plat!r} has no stored sha256 to compare against"
            )
        new_hash = compute_hash_for_url(url)
        changed = new_hash != stored
        if changed:
            out['drift'] = True
        out['platforms'][plat] = {
            'url': url,
            'old_sha256': stored,
            'new_sha256': new_hash,
            'changed': changed,
        }
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_check_updates.py::test_detect_drift_for_stable_url_flags_changed_bytes tests/test_check_updates.py::test_detect_drift_for_stable_url_no_drift_when_hash_matches -v`

Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/download-plugins.py tests/test_check_updates.py
git commit -m "feat: detect_drift_for_stable_url byte-comparison primitive"
```

---

## Task 4: Wire `stable-url` into `check_updates` dispatcher

**Files:**
- Modify: `scripts/download-plugins.py:425-499` (the dispatcher and the report-row builder)
- Test: `tests/test_check_updates.py`

- [ ] **Step 1: Write the failing integration test for drift**

Add to `tests/test_check_updates.py`:

```python
def test_check_updates_drift_for_stable_url_plugin(mock_server, tmp_path):
    new_body = b"<<<new build pushed silently by vendor>>>"
    drifted_url = mock_server.add("/valhalla/supermassive-mac.zip", new_body)

    plugins_data = {
        "meta": {"name": "test", "version": "1", "description": "x",
                 "updated": "2026-05-09", "author": "x", "license": "x",
                 "platforms": ["macos"]},
        "plugins": {
            "effects": [{
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
            }],
        },
    }

    report = dlp.check_updates(plugins_data)

    assert len(report["updates"]) == 1
    upd = report["updates"][0]
    assert upd["name"] == "FakeStable"
    assert upd["strategy"] == "stable-url"
    assert upd["old_version"] == "5.0.0"
    assert upd["new_version"] == "5.0.0"  # unchanged for stable-url
    # platforms is the same shape (list of per-platform updates) as the github/u-he path
    plats = {p["plat"]: p for p in upd["platforms"]}
    assert "macos" in plats
    assert plats["macos"]["changed"] is True
    assert plats["macos"]["new_sha256"] == hashlib.sha256(new_body).hexdigest()


def test_check_updates_no_drift_for_stable_url_plugin(mock_server, tmp_path):
    body = b"<<<unchanged>>>"
    url = mock_server.add("/static.zip", body)
    stored = hashlib.sha256(body).hexdigest()

    plugins_data = {
        "meta": {"name": "test", "version": "1", "description": "x",
                 "updated": "2026-05-09", "author": "x", "license": "x",
                 "platforms": ["macos"]},
        "plugins": {
            "effects": [{
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
            }],
        },
    }

    report = dlp.check_updates(plugins_data)

    assert len(report["updates"]) == 0
    assert len(report["no_updates"]) == 1
    assert report["no_updates"][0]["name"] == "FakeStable"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_check_updates.py::test_check_updates_drift_for_stable_url_plugin tests/test_check_updates.py::test_check_updates_no_drift_for_stable_url_plugin -v`

Expected: Both FAIL — the dispatcher in `check_updates` has no branch for `stable-url`, so the entry falls through to a malformed-strategy failure (or unknown-kind RuntimeError).

- [ ] **Step 3: Add the dispatcher branch**

In `scripts/download-plugins.py`, modify `check_updates`. Locate the existing `try:` block that dispatches `parsed[0] == 'github'` / `parsed[0] == 'u-he'` (around line 425-444). Add a new `elif` branch for `stable-url` that handles the row construction inline (because the per-platform shape is different from github/u-he and wouldn't fit the asset-matching pipeline below it):

Replace this block:
```python
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
                    old_tag = current_version
                    tag = None
                else:
                    raise RuntimeError(f"unknown strategy kind: {parsed[0]}")
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError, RuntimeError) as e:
                report['failures'].append({
                    'name': name, 'category': category,
                    'reason': f'detection failed: {e}',
                })
                continue
```

With:
```python
            # stable-url is its own pipeline — no asset matching, just rehash + compare.
            if parsed[0] == 'stable-url':
                try:
                    drift_result = detect_drift_for_stable_url(plugin)
                except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as e:
                    report['failures'].append({
                        'name': name, 'category': category,
                        'reason': f'detection failed: {e}',
                    })
                    continue
                if drift_result['drift']:
                    platform_rows = [
                        {'plat': plat, 'changed': info['changed'],
                         'old_sha256': info['old_sha256'], 'new_sha256': info['new_sha256']}
                        for plat, info in drift_result['platforms'].items()
                    ]
                    report['updates'].append({
                        'name': name, 'category': category,
                        'strategy': 'stable-url',
                        'old_version': current_version,
                        'new_version': current_version,  # vendor didn't bump a label
                        'platforms': platform_rows,
                    })
                else:
                    report['no_updates'].append({
                        'name': name, 'category': category, 'version': current_version,
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
                    old_tag = current_version
                    tag = None
                else:
                    raise RuntimeError(f"unknown strategy kind: {parsed[0]}")
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError, RuntimeError) as e:
                report['failures'].append({
                    'name': name, 'category': category,
                    'reason': f'detection failed: {e}',
                })
                continue
```

The `stable-url` path lives *before* the github/u-he `try` block and ends with `continue`, so the github/u-he flow (asset matching, version comparison) is bypassed entirely. The github/u-he `report['updates']` builder later in the function adds rows without a `'strategy'` field — that's fine; downstream code reads `update.get('strategy')` and treats absence as the legacy github/u-he shape.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_check_updates.py -v`

Expected: All check-updates tests PASS, including the two new integration tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/download-plugins.py tests/test_check_updates.py
git commit -m "feat: dispatch stable-url drift detection in check_updates"
```

---

## Task 5: Update report formatter for stable-url drift

**Files:**
- Modify: `scripts/download-plugins.py:502-534` (`print_check_updates_report`)
- Test: manual verification (no unit test — formatter is a thin display layer; behavior covered indirectly by integration smoke)

- [ ] **Step 1: Read the current formatter**

Run: `sed -n '502,534p' scripts/download-plugins.py`

Confirm the formatter dispatches on `kind` (one of `'updates'`, `'no_updates'`, `'manual'`, `'failures'`).

- [ ] **Step 2: Modify the `'updates'` branch to dispatch on strategy**

In `print_check_updates_report`, replace the `if kind == 'updates':` branch:

From:
```python
            if kind == 'updates':
                print(f"  {name:<30} {item['old_version']:<8} → {item['new_version']:<8} {C.YELLOW}⬆ NEW VERSION{C.NC}")
                for pu in item['platforms']:
                    print(f"    {pu['plat']:8} {pu['new_asset']['name']}")
```

To:
```python
            if kind == 'updates':
                if item.get('strategy') == 'stable-url':
                    print(f"  {name:<30} {item['old_version']:<8} → {item['new_version']:<8} {C.YELLOW}⬆ CONTENT DRIFT{C.NC}")
                    for pu in item['platforms']:
                        if pu.get('changed'):
                            short_old = pu['old_sha256'][:8]
                            short_new = pu['new_sha256'][:8]
                            print(f"    {pu['plat']:8} sha256 {short_old} → {short_new}")
                        else:
                            print(f"    {pu['plat']:8} unchanged")
                else:
                    print(f"  {name:<30} {item['old_version']:<8} → {item['new_version']:<8} {C.YELLOW}⬆ NEW VERSION{C.NC}")
                    for pu in item['platforms']:
                        print(f"    {pu['plat']:8} {pu['new_asset']['name']}")
```

- [ ] **Step 3: Sanity-test the formatter by running the existing integration test**

Run: `pytest tests/test_check_updates.py::test_check_updates_drift_for_stable_url_plugin -v`

Expected: PASS (formatter doesn't have its own assertions; this just confirms the new branch doesn't crash on the new shape).

- [ ] **Step 4: Visual smoke — invoke check_updates with the new fixture and read output**

Run:
```bash
python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('dlp', 'scripts/download-plugins.py')
dlp = importlib.util.module_from_spec(spec)
sys.modules['dlp'] = dlp
spec.loader.exec_module(dlp)

report = {
    'updates': [{
        'name': 'FakeStable', 'category': 'effects',
        'strategy': 'stable-url',
        'old_version': '5.0.0', 'new_version': '5.0.0',
        'platforms': [
            {'plat': 'macos', 'changed': True,
             'old_sha256': '0'*64, 'new_sha256': 'a'*64},
            {'plat': 'windows', 'changed': False,
             'old_sha256': 'b'*64, 'new_sha256': 'b'*64},
        ],
    }],
    'no_updates': [], 'manual': [], 'failures': [],
}
dlp.print_check_updates_report(report)
"
```

Expected output should contain:
```
  FakeStable                     5.0.0    → 5.0.0    ⬆ CONTENT DRIFT
    macos    sha256 00000000 → aaaaaaaa
    windows  unchanged
```

- [ ] **Step 5: Commit**

```bash
git add scripts/download-plugins.py
git commit -m "feat: format stable-url drift in check-updates report"
```

---

## Task 6: Wire `stable-url` into `apply_updates`

**Files:**
- Modify: `scripts/download-plugins.py:539-567` (`apply_updates`)
- Test: `tests/test_check_updates.py`

- [ ] **Step 1: Write the failing integration test**

Add to `tests/test_check_updates.py`:

```python
def test_apply_for_stable_url_plugin(mock_server, tmp_path):
    new_body = b"<<<new build>>>"
    drifted_url = mock_server.add("/valhalla/supermassive-mac.zip", new_body)
    new_hash = hashlib.sha256(new_body).hexdigest()
    old_hash = "0" * 64

    plugins_data = {
        "meta": {"name": "test", "version": "1", "description": "x",
                 "updated": "2026-05-09", "author": "x", "license": "x",
                 "platforms": ["macos"]},
        "plugins": {
            "effects": [{
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
            }],
        },
    }

    report = dlp.check_updates(plugins_data)
    dlp.apply_updates(plugins_data, report)

    plugin = plugins_data["plugins"]["effects"][0]
    macos = plugin["urls"]["macos"]
    assert macos["sha256"] == new_hash
    assert macos["hash_source"] == "self"
    # URL, filename, version unchanged for stable-url
    assert macos["url"] == drifted_url
    assert macos["filename"] == "supermassive-mac.zip"
    assert plugin["version"] == "5.0.0"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_check_updates.py::test_apply_for_stable_url_plugin -v`

Expected: FAIL — `apply_updates` currently iterates `for pu in upd['platforms']: asset = pu['new_asset']`, which doesn't exist on the stable-url shape, so it either crashes with KeyError or silently does nothing depending on how Python evaluates the missing key.

- [ ] **Step 3: Add the strategy-dispatch branch to `apply_updates`**

In `scripts/download-plugins.py`, modify `apply_updates` (currently at line 539-567):

From:
```python
def apply_updates(plugins_data: dict, report: dict) -> None:
    """..."""
    index = {}
    for cat, plugins in plugins_data.get('plugins', {}).items():
        for p in plugins:
            index[(cat, p.get('name'))] = p

    for upd in report['updates']:
        plugin = index.get((upd['category'], upd['name']))
        if plugin is None:
            continue
        for pu in upd['platforms']:
            asset = pu['new_asset']
            if asset is None:
                continue
            entry = plugin['urls'][pu['plat']]
            entry['url'] = asset['url']
            entry['filename'] = asset['name']
            entry.pop('sha256', None)
            entry.pop('hash_source', None)
        if upd['old_version'] != upd['new_version']:
            plugin['version'] = upd['new_version']
```

To:
```python
def apply_updates(plugins_data: dict, report: dict) -> None:
    """Mutate plugins_data in place.

    For github/u-he updates: rewrite urls[plat].url + filename, clear sha256 +
    hash_source (recompute_hashes will re-fill them), bump version.

    For stable-url updates: write the pre-computed new sha256 directly (no
    re-fetch needed — detect_drift_for_stable_url already paid that cost), set
    hash_source to 'self' (we just hashed it ourselves), leave url/filename/
    version untouched (they didn't change).
    """
    index = {}
    for cat, plugins in plugins_data.get('plugins', {}).items():
        for p in plugins:
            index[(cat, p.get('name'))] = p

    for upd in report['updates']:
        plugin = index.get((upd['category'], upd['name']))
        if plugin is None:
            continue

        if upd.get('strategy') == 'stable-url':
            for pu in upd['platforms']:
                if not pu.get('changed'):
                    continue
                entry = plugin['urls'][pu['plat']]
                entry['sha256'] = pu['new_sha256']
                entry['hash_source'] = 'self'
            continue  # url/filename/version unchanged for stable-url

        # github/u-he path
        for pu in upd['platforms']:
            asset = pu['new_asset']
            if asset is None:
                continue
            entry = plugin['urls'][pu['plat']]
            entry['url'] = asset['url']
            entry['filename'] = asset['name']
            entry.pop('sha256', None)
            entry.pop('hash_source', None)
        if upd['old_version'] != upd['new_version']:
            plugin['version'] = upd['new_version']
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_check_updates.py -v`

Expected: All check-updates tests PASS.

- [ ] **Step 5: Verify the `--apply` end-to-end path doesn't double-fetch**

The CLI `--apply` flow in `main()` runs `apply_updates(...)` then `recompute_hashes(plugins_data, force=False)`. For stable-url entries, `apply_updates` *sets* the new sha256, so `recompute_hashes(force=False)` skips them (it only recomputes when `entry.get('sha256')` is falsy). Confirm by reading `recompute_hashes` at line 174-192 — the check `if entry.get('sha256') and not force: continue` is what we rely on. No code change needed; just verify the assumption holds.

Run: `sed -n '174,192p' scripts/download-plugins.py`

Expected: confirms `recompute_hashes(force=False)` skips entries that already have `sha256` set.

- [ ] **Step 6: Commit**

```bash
git add scripts/download-plugins.py tests/test_check_updates.py
git commit -m "feat: apply_updates handles stable-url sha256 rewrites"
```

---

## Task 7: Add `update_strategy: "stable-url"` to the 5 manifest entries

**Files:**
- Modify: `plugins.json` (5 entries)

The current `--check-updates` output identifies these entries as `manual`:
- Valhalla Supermassive (effects)
- Valhalla FreqEcho (effects)
- OTT (effects)
- TAL-Vocoder (effects)
- TAL-NoiseMaker (synths)

- [ ] **Step 1: Locate the 5 entries**

Run: `grep -n '"name":' plugins.json | grep -iE 'valhalla|ott|tal-'`

Expected: 5 line numbers. Note them.

- [ ] **Step 2: Add `update_strategy: "stable-url"` to each entry**

For each of the 5 plugins, add a new `update_strategy: "stable-url"` field. The field can go on the line immediately after `"version"` to match the convention used for github/u-he plugins (read an existing github plugin like Surge XT to confirm the field placement).

Edit each entry — example for Valhalla Supermassive:

From:
```json
{
  "name": "Valhalla Supermassive",
  "version": "5.0.0",
  "urls": { ... }
}
```

To:
```json
{
  "name": "Valhalla Supermassive",
  "version": "5.0.0",
  "update_strategy": "stable-url",
  "urls": { ... }
}
```

Apply the same edit to: Valhalla FreqEcho, OTT, TAL-Vocoder, TAL-NoiseMaker.

- [ ] **Step 3: Validate the schema**

Run: `python3 -c "
import json, jsonschema
schema = json.load(open('schemas/plugins.schema.json'))
data = json.load(open('plugins.json'))
jsonschema.validate(data, schema)
print('schema OK')
"`

Expected output: `schema OK`

- [ ] **Step 4: Run all tests**

Run: `pytest tests/ -v`

Expected: all tests PASS (the manifest change shouldn't break any existing test since none assert specific strategies on real entries).

- [ ] **Step 5: Run `--check-updates` against real CDNs to smoke-test**

> **Note for the orchestrator:** This step requires real network access. Subagents executing this plan should NOT run this step themselves — instead, surface to the orchestrator with the requested smoke-test command. The orchestrator runs the network call locally and feeds back the output.

Command (orchestrator-only):
```bash
python3 scripts/download-plugins.py --check-updates 2>&1 | tail -30
```

Expected: the 5 entries now show `no update` (or `⬆ CONTENT DRIFT` if upstream has actually changed since hashes were last refreshed). They should no longer appear as `manual`.

- [ ] **Step 6: If the smoke test reports drift on any of the 5 plugins, run `--apply` (orchestrator-only)**

```bash
python3 scripts/download-plugins.py --check-updates --apply
```

Expected: plugins.json is rewritten with new sha256 fields. Re-run schema validation:
```bash
python3 -c "
import json, jsonschema
schema = json.load(open('schemas/plugins.schema.json'))
data = json.load(open('plugins.json'))
jsonschema.validate(data, schema)
print('schema OK')
"
```

Expected: `schema OK`.

- [ ] **Step 7: Commit**

```bash
git add plugins.json
git commit -m "feat: enable stable-url drift detection for Valhalla, OTT, TAL plugins"
```

If Step 6 ran and modified hashes, those changes will be in the same commit. Note in the commit message body that hashes were refreshed.

---

## Task 8: Final integration check

**Files:** none (verification-only task)

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v`

Expected: all tests PASS (count should be original_count + ~6 new tests from this plan).

- [ ] **Step 2: Run schema validation**

Run: `python3 -c "
import json, jsonschema
schema = json.load(open('schemas/plugins.schema.json'))
data = json.load(open('plugins.json'))
jsonschema.validate(data, schema)
print('schema OK')
"`

Expected: `schema OK`.

- [ ] **Step 3: Run `--check-updates` and confirm 5 fewer manual entries (orchestrator-only)**

Command (orchestrator-only):
```bash
python3 scripts/download-plugins.py --check-updates 2>&1 | tail -30
```

Expected: the report should show 4 manual entries (Sitala, Helm, MeldaProduction, TDR Nova) — down from the original 9. The 5 stable-URL entries should appear as `no update` or `⬆ CONTENT DRIFT`.

- [ ] **Step 4: Verify CI workflow passes locally if possible**

Run: `ruff check scripts/ tests/ 2>&1 | tail -5`

Expected: no errors.

---

## Summary of new test count

This plan adds:
- 2 schema tests (positive `stable-url`, negative `stable-url:foo`)
- 2 parser tests (positive `stable-url`, negative `stable-url:foo`)
- 2 detector tests (drift, no-drift)
- 2 integration tests (drift dispatcher, no-drift dispatcher)
- 1 apply integration test
- 0 formatter tests (covered by manual smoke and downstream integration)

Total: **9 new tests**.

If the existing suite is at 31 tests, post-implementation count should be 40.
