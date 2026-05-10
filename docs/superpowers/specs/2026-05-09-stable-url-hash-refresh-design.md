# Stable-URL Hash Refresh (Phase 3 of Self-Updating Manifest) — Design

**Status:** Approved (design phase)
**Date:** 2026-05-09
**Scope:** `scripts/download-plugins.py`, `plugins.json`, `schemas/plugins.schema.json`, `tests/`. Adds `stable-url` value to `update_strategy` and the byte-comparison logic behind it. Initial coverage: Valhalla Supermassive, Valhalla FreqEcho, OTT, TAL-Vocoder, TAL-NoiseMaker.
**Out of scope:** HEAD-first optimization (Content-Length / ETag short-circuit). Asset size storage. Auto-pruning abandoned plugins (Helm, Sitala). Notifications on drift.

## Problem

Phases 1 (GitHub) and 2 (u-he) automated drift detection for plugins where upstream exposes a discoverable version string. Five entries in our manifest still report `manual` because they don't fit that model:

| Plugin | Vendor pattern |
|---|---|
| Valhalla Supermassive, FreqEcho | Stable URL on `valhallaaudio.s3.amazonaws.com`. Vendor swaps content silently. |
| OTT | Stable URL on `xferrecords.com`. Vendor swaps content silently. |
| TAL-Vocoder, TAL-NoiseMaker | Stable URL on `tal-software.com`. Vendor swaps content silently. |

For all five, the URL is already canonical — fetching it tomorrow may return a newer build, but the URL string never changes. The existing strategies have nothing to detect: there's no GitHub release tag, no product page version string. The only signal that the upstream file has changed is its bytes.

## Goals

1. Running `--check-updates` detects content drift on the 5 stable-URL plugins, surfaced with the same drift line format as GitHub and u-he entries.
2. Running `--check-updates --apply` updates `sha256` fields in place. URL, filename, and version fields are unchanged because they didn't change upstream.
3. Adding a new stable-URL plugin to our manifest requires only setting `update_strategy: "stable-url"` on the entry. No code changes.
4. The architecture composes with Phases 1 and 2 — a single `--check-updates` run handles all three strategies.

## Non-goals

- **HEAD-first optimization.** Saves bandwidth in the no-drift case, but Content-Length / ETag aren't reliable across all CDNs (Valhalla S3 is, Xfer's CDN may not be). Add later if check times become a problem.
- **Asset size storage.** Same reason — would only be useful as a HEAD short-circuit.
- **Auto-pruning abandoned plugins.** Helm and Sitala stay manual; they're frozen upstream and tracking them adds no signal.
- **Notifications on drift.** CI surfaces drift via the existing `--check-updates` step exit code; that's enough.
- **Re-using `stable-url` for vendors with versioned-but-static URLs.** The strategy is exclusively for "URL never changes, content might." Plugins with versioned filenames (e.g. `MeldaProduction.13.21.exe`) need a Phase 4 strategy.

## Design

### 1. Data shape

`update_strategy` gains a new accepted value: `stable-url` (no slug — there's no per-vendor logic to encode).

```json
"name": "OTT",
"update_strategy": "stable-url",
```

Schema regex extends to:
```
^(github:[\w.-]+/[\w.-]+(@[\w.-]+)?|u-he:[\w.-]+|stable-url)$
```

The schema accepts exactly the literal `stable-url` for this strategy. There is no slug because the URLs in the entry already identify the assets unambiguously.

### 2. Initial coverage

| Plugin | Strategy value |
|---|---|
| Valhalla Supermassive | `"stable-url"` |
| Valhalla FreqEcho | `"stable-url"` |
| OTT | `"stable-url"` |
| TAL-Vocoder | `"stable-url"` |
| TAL-NoiseMaker | `"stable-url"` |

These are the 5 currently-`manual` entries that fit the stable-URL pattern. No other entries qualify.

### 3. Detection algorithm (`detect_drift_for_stable_url`)

```python
def detect_drift_for_stable_url(entry: dict) -> dict:
    """Fetch each platform URL in `entry`, hash the response, and report
    drift relative to the entry's stored sha256.

    Returns a dict shaped:
      {
          'drift': bool,
          'platforms': {
              'macos':   {'url': str, 'old_sha256': str, 'new_sha256': str, 'changed': bool},
              'windows': {...},
              'linux':   {...},
          },
      }

    Raises:
      urllib.error.URLError / HTTPError on network failure.
      ValueError if any URL serves non-binary content (text/html, application/json),
        which indicates the vendor URL has been replaced with a download-gate page
        and silent re-hashing would be wrong.
    """
```

Behavior:
1. For each platform present in `entry['platforms']`, fetch the URL and stream-hash with `compute_hash_for_url` (the existing primitive — already enforces the content-type guard).
2. Compare the computed sha256 to the entry's `platforms[<plat>].sha256`.
3. Set `changed = True` for any platform whose hash differs.
4. Set top-level `drift = any(changed)`.
5. Return the structure for use by both reporting and `apply_updates`.

The reason new hashes are carried in the return value (rather than recomputed in `--apply`): we already paid the bandwidth cost during detection. Re-fetching during apply doubles the cost and introduces a TOCTOU window where the vendor could have swapped the file again between the two requests.

### 4. Strategy parsing & dispatch

`_parse_update_strategy(strategy)` extends to recognize the literal:

```python
def _parse_update_strategy(strategy: str):
    if not strategy:
        return None
    if strategy.startswith('github:'):
        # ... existing logic ...
    if strategy.startswith('u-he:'):
        return ('u-he', strategy[len('u-he:'):])
    if strategy == 'stable-url':
        return ('stable-url',)
    return None
```

`check_updates` dispatches a third branch:

```python
elif parsed[0] == 'stable-url':
    try:
        result = detect_drift_for_stable_url(entry)
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as e:
        report['failures'].append({...})
        continue

    if result['drift']:
        report['updates'].append({
            'name': entry['name'],
            'strategy': 'stable-url',
            'old_version': current_version,
            'new_version': current_version,  # version unchanged for stable-URL
            'platforms': result['platforms'],  # carries new sha256 values
        })
```

The branch builds a different report-entry shape than the github/u-he branches because there are no URLs/filenames/versions to swap — only sha256 values.

### 5. Apply for stable-URL

`apply_updates` gains a per-strategy code path:

```python
if update.get('strategy') == 'stable-url':
    target_entry = _find_entry(plugins_data, update['name'])
    for platform, info in update['platforms'].items():
        if info['changed']:
            target_entry['platforms'][platform]['sha256'] = info['new_sha256']
            # hash_source stays 'self' — we computed this hash ourselves
            target_entry['platforms'][platform]['hash_source'] = 'self'
    continue  # skip the github/u-he URL-and-filename rewrite path
```

What does *not* change for stable-URL applies:
- URL (unchanged upstream)
- filename (unchanged — vendor reuses the same name)
- version (unchanged — vendor didn't bump a version label)
- hash_source — stays `self`. We re-hashed; that's a TOFU acknowledgment, not a publisher checksum.

### 6. Reporting

The existing report formatter handles github/u-he by showing `version → new_version` followed by a yellow `⬆ NEW VERSION` marker. For stable-URL, both versions are equal but the row is still actionable. To keep the visual convention, the marker becomes `⬆ CONTENT DRIFT` and the per-platform detail line shows the sha256 prefix change instead of a filename:

```
OTT                            1.37     → 1.37     ⬆ CONTENT DRIFT
    macos    sha256 abc12345 → def67890
    windows  unchanged
```

For the no-drift case, the row matches the existing `no_updates` formatting:
```
OTT                            1.37     → 1.37     no update
```

### 7. Failure modes

| Trigger | Action |
|---|---|
| `update_strategy: "stable-url"` set but `entry['platforms']` missing or empty | report failure with reason "stable-url entry has no platforms" |
| HTTP error fetching any platform URL | report failure with HTTP status (existing pattern) |
| URL serves `text/html` or `application/json` (download-gate page replaced binary) | report failure with reason "URL serves non-binary content" — same guard `compute_hash_for_url` already enforces |
| `sha256` field missing on a platform entry | should be impossible post-checksum-phase (schema-required); but if present, report failure with reason "missing stored sha256 for comparison" |

The schema requires every platform to carry `sha256` and `hash_source`, so the last failure mode is a defense-in-depth check, not an expected path.

### 8. Testing

Three new tests in `tests/test_check_updates.py`:

1. **`test_detect_drift_for_stable_url_plugin`** — fixture with a `stable-url` plugin and one platform. Mock-serve bytes that differ from the stored sha256. Run `--check-updates`, assert exit 1, drift line printed with `*` marker.

2. **`test_no_drift_for_stable_url_plugin`** — same fixture. Mock-serve bytes that match the stored sha256. Run `--check-updates`, assert exit 0, no-update line printed.

3. **`test_apply_for_stable_url_plugin`** — drift fixture + `--apply`. Mock the new bytes, run, assert plugins.json sha256 updated, URL/filename/version unchanged.

Plus schema-test extension in `tests/test_schema.py`: `update_strategy: "stable-url"` validates; `update_strategy: "stable-url:foo"` does not (no slug allowed).

### 9. CI integration

No CI changes needed. The existing "Check for upstream version drift" step (Phase 1, Task 7) automatically picks up the new strategy because it just runs `--check-updates`. CI run time will increase by however long it takes to GET the 5 stable-URL files (~few hundred MB total). If this becomes a problem, the HEAD-first optimization in "Out of scope" is the lever.

## File changes summary

| File | Change |
|---|---|
| `plugins.json` | Add `update_strategy: "stable-url"` to Valhalla Supermassive, Valhalla FreqEcho, OTT, TAL-Vocoder, TAL-NoiseMaker. |
| `schemas/plugins.schema.json` | Extend `update_strategy.pattern` to also match `stable-url`. |
| `scripts/download-plugins.py` | Add `detect_drift_for_stable_url()`. Update `_parse_update_strategy` to recognize `stable-url`. Update `check_updates` dispatcher for the new shape. Update `apply_updates` to handle the per-platform sha256 rewrite. Update report formatter for the `*` marker. |
| `tests/test_check_updates.py` | Add 3 tests. |
| `tests/test_schema.py` | Add 1 positive and 1 negative test for `stable-url`. |

## Open questions

None — all design decisions made and approved.

## Out-of-scope follow-ups

- **Phase 4: MeldaProduction** — versioned-filename URLs that change with each release. Different shape: HTML scrape page for current version, build URL from template.
- **Phase 5: Tokyo Dawn (TDR Nova)** — same shape as u-he Phase 2 (HTML scrape product page).
- **HEAD-first optimization** — store asset size; on `--check-updates`, do a HEAD first and skip the GET when Content-Length matches. Saves bandwidth but heuristic.
- **Auto-prune** — sweep entries flagged as abandoned (Helm) and remove them; needs a separate "abandonment policy" decision.
