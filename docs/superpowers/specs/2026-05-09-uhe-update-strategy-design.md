# u-he Update Strategy (Phase 2 of Self-Updating Manifest) — Design

**Status:** Approved (design phase)
**Date:** 2026-05-09
**Scope:** `scripts/download-plugins.py`, `plugins.json`, `tests/`. Adds an `u-he:<ProductSlug>` value to `update_strategy` and the detection logic behind it. Initial coverage: TyrellN6, Zebralette.
**Out of scope:** Other vendor strategies (Tokyo Dawn, Klanghelm, MeldaProduction, TAL, Decomposer, Tytel). Auto-install. Asset-size storage. Filename-vs-version output relabel.

## Problem

Phase 1 added drift detection for GitHub-hosted plugins. The remaining "manual" entries in our `--check-updates` output include 2 u-he plugins (Tyrell N6, Zebralette). u-he is the cleanest of the remaining vendors to automate: their URL scheme is documented and their product pages display version+revision in a parseable form.

u-he does **not** expose a directory listing or version API. Both `dl.u-he.com/latest-builds/<Product>/` and `dl.u-he.com/release-archive/<Product>/` redirect to a Bunny CDN that returns 404 on directory access. Detection requires scraping the product page HTML for the version string.

Each u-he product has a slightly different URL template — TyrellN6 uses `_public_beta_` infix and ships Linux as `.tar.xz`; Zebralette uses `Zebra_Legacy_` prefix and ships Linux as `.zip`. A single vendor-wide template doesn't fit.

## Goals

1. Running `--check-updates` detects upstream version drift on the 2 u-he plugins, same as it does today for GitHub-hosted entries.
2. Running `--check-updates --apply` updates the URL/filename/version/sha256 of those entries.
3. Adding a new u-he product to our manifest requires (a) a new entry in `plugins.json` and (b) a new entry in a Python dict in the script. No new code paths.
4. The architecture extends to future vendors (`tokyodawn:`, `klanghelm:`, etc.) by repeating the same shape — vendor-specific detect function plus per-product template dict.

## Non-goals

- **Other vendor strategies.** Each is its own phase.
- **Auto-discovery of new u-he products.** A maintainer who wants to track a new u-he product must add it to `UHE_PRODUCTS` manually.
- **u-he wildcard / "all products" strategy.** Out of scope.
- **HTML scraping of arbitrary patterns.** This phase commits to two specific regex patterns (one per product).

## Design

### 1. Data shape

`update_strategy` gains a new accepted value family: `u-he:<ProductSlug>`.

```json
"name": "Tyrell N6",
"update_strategy": "u-he:TyrellN6",
```

The `ProductSlug` must be a key in `UHE_PRODUCTS` (defined in §3 below). The schema regex is extended to accept the new family. Future strategies will follow the same `vendor:<key>` shape.

Schema regex (final form):
```
^(github:[\w.-]+/[\w.-]+(@[\w.-]+)?|u-he:[\w.-]+)$
```

This allows either `github:owner/repo[@tag]` or `u-he:Product`. Future vendor strategies will extend this regex (adding new alternatives).

### 2. Initial coverage

| Plugin | Strategy value |
|---|---|
| Tyrell N6 | `"u-he:TyrellN6"` |
| Zebralette | `"u-he:Zebralette"` |

These are the only two u-he products in our current manifest. No backfill needed beyond these two entries.

### 3. The `UHE_PRODUCTS` dict

A new module-level constant in `scripts/download-plugins.py` that encodes per-product metadata:

```python
UHE_PRODUCTS = {
    'TyrellN6': {
        'page_url': 'https://u-he.com/products/tyrelln6/',
        'version_re': re.compile(r'TyrellN6\s+(?:Beta\s+)?(\d+)\.(\d+)\.(\d+)\s*\(revision\s+(\d+)\)'),
        'asset_template': 'https://dl.u-he.com/releases/TyrellN6_{vcode}_public_beta_{rev}_{platform}.{ext}',
        'platforms': {
            'macos':   ('Mac',   'zip'),
            'windows': ('Win',   'zip'),
            'linux':   ('Linux', 'tar.xz'),
        },
    },
    'Zebralette': {
        'page_url': 'https://u-he.com/products/zebralette/',
        'version_re': re.compile(r'Zebralette\s+(\d+)\.(\d+)\.(\d+)\s*\(revision\s+(\d+)\)'),
        'asset_template': 'https://dl.u-he.com/releases/Zebra_Legacy_{vcode}_{rev}_{platform}.{ext}',
        'platforms': {
            'macos':   ('Mac',   'zip'),
            'windows': ('Win',   'zip'),
            'linux':   ('Linux', 'zip'),
        },
    },
}
```

The `vcode` template variable is the concatenated `major+minor+patch` (e.g., `3.0.0` → `300`, `2.9.4` → `294`). This matches the observed pattern.

### 4. Detection algorithm (`detect_latest_for_uhe`)

```python
def detect_latest_for_uhe(product: str, page_url: str | None = None,
                          dl_base: str | None = None) -> dict:
    """Fetch a u-he product page and return the latest release as
    {'tag': str, 'assets': [{'name': str, 'url': str, 'size': 0}, ...]}.

    The 'tag' is f'{vmajor}.{vminor}.{vpatch}-r{rev}' so it's stable
    string-comparable across runs.

    Asset 'size' is 0 — u-he doesn't expose sizes from a list endpoint;
    the actual size is determined when the binary is fetched.

    page_url and dl_base override the values from UHE_PRODUCTS for testing.
    """
```

Behavior:
1. Look up `product` in `UHE_PRODUCTS`. Raise `ValueError` if unknown.
2. Fetch the product's `page_url` (override allowed for tests).
3. Apply `version_re`. If no match: raise `RuntimeError("u-he page does not contain a recognizable version string")`.
4. Extract `(major, minor, patch, rev)`.
5. Construct per-platform asset URLs from the template, substituting `{vcode}` (concat), `{rev}`, `{platform}` (from per-platform tuple), `{ext}` (from per-platform tuple). Optionally use `dl_base` override (replace `https://dl.u-he.com` with the test-supplied base) for test isolation.
6. Build the `tag` as `f'{major}.{minor}.{patch}-r{rev}'`.
7. Return the standard shape.

### 5. Strategy parsing & dispatch

`_parse_update_strategy(strategy)` is extended:

```python
def _parse_update_strategy(strategy: str):
    """Parse known strategy strings.

    Returns one of:
      ('github', repo: str, tag: str | None)
      ('u-he', product: str)
      None  (unknown / malformed)
    """
    if not strategy:
        return None
    if strategy.startswith('github:'):
        rest = strategy[len('github:'):]
        if '@' in rest:
            repo, tag = rest.rsplit('@', 1)
            return ('github', repo, tag)
        return ('github', rest, None)
    if strategy.startswith('u-he:'):
        return ('u-he', strategy[len('u-he:'):])
    return None
```

Note the return shape changed from `(repo, tag) | None` (Phase 1) to a tagged tuple `(kind, *args) | None`. This is a breaking change for the function's signature and requires updating its callers (`check_updates` is the only one). The Phase 1 tests on `_parse_update_strategy` are not asserting the old shape directly (they assert through `check_updates` integration), so the test surface is small.

`check_updates` dispatches:

```python
            parsed = _parse_update_strategy(strategy)
            if not parsed:
                report['failures'].append({...})
                continue

            try:
                if parsed[0] == 'github':
                    _, repo, tag = parsed
                    release = detect_latest_for_github(repo, tag=tag, api_base=api_base)
                    # For substitution-Strategy A: if the strategy pinned a
                    # rolling tag (e.g. @DAWPlugin), use it; otherwise use the
                    # current version field as the substitution source.
                    old_tag = tag if tag else current_version
                elif parsed[0] == 'u-he':
                    _, product = parsed
                    release = detect_latest_for_uhe(product)
                    # u-he tags include a revision (e.g. "3.0.1-r17000"); the
                    # current_version field is just the dotted version, so it
                    # won't substring-match the new tag. Strategy A will skip
                    # and Strategy B (token-overlap) does the actual matching.
                    old_tag = current_version
                else:
                    raise RuntimeError(f"unknown strategy kind: {parsed[0]}")
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError, RuntimeError) as e:
                report['failures'].append({...})
                continue

            new_tag = release['tag']
```

Note the `except` clause widens to include `ValueError` (raised by `detect_latest_for_uhe` when the product is unknown) and `RuntimeError` (raised when version regex doesn't match).

### 6. Asset matching for u-he

The existing `find_matching_asset` already handles u-he correctly because its tokenizer splits on `-_./:` and the URL-token merge from Phase 1's late fix means tokens like `tyrelln6`, `linux`, `tar`, `xz` are all present in the comparison. No changes required.

### 7. Failure modes

| Trigger | Action |
|---|---|
| `update_strategy: "u-he:UnknownProduct"` (not in UHE_PRODUCTS) | `report['failures']` with reason "unknown u-he product: UnknownProduct" |
| u-he product page returns HTTP error | `report['failures']` with the HTTP status |
| Product page HTML doesn't match `version_re` | `report['failures']` with reason "u-he page does not contain a recognizable version string" |
| Detected `vcode` produces a URL that's 404 (e.g., u-he changed their template) | The asset gets stored, but `recompute_hashes` later fails on the mismatch when `--apply` runs. Atomic-write preserves plugins.json. |

### 8. Testing

Three new tests in `tests/test_check_updates.py`:

1. **`test_detect_latest_for_uhe_parses_version_and_builds_urls`** — mock-serve a fake TyrellN6 product page containing a version string. Call `detect_latest_for_uhe('TyrellN6', page_url=mock_url, dl_base=mock_dl_base)`. Assert returned tag, asset count, and that the constructed asset URLs use the mock dl_base + the templated names.

2. **`test_check_updates_drift_for_uhe_plugin`** — a fixture with one u-he plugin pinned at an old version+rev. Mock the product page to return a NEW version. Run `--check-updates`, assert exit 1, drift line printed.

3. **`test_check_updates_apply_for_uhe_plugin`** — same fixture, mock the new asset URL bodies, run `--check-updates --apply`, assert plugins.json updated with new URLs/hashes/version.

Plus one schema test extension: `update_strategy: "u-he:TyrellN6"` validates; `update_strategy: "u-he:"` (empty product) does not.

### 9. CI integration

No CI changes needed. The existing "Check for upstream version drift" step (added in Phase 1's Task 7) automatically picks up the new strategy because it just runs `--check-updates`.

## File changes summary

| File | Change |
|---|---|
| `plugins.json` | Add `update_strategy: "u-he:TyrellN6"` to Tyrell N6, `update_strategy: "u-he:Zebralette"` to Zebralette. |
| `schemas/plugins.schema.json` | Extend `update_strategy.pattern` to also match `u-he:<slug>`. |
| `scripts/download-plugins.py` | Add `UHE_PRODUCTS` dict. Add `detect_latest_for_uhe()`. Update `_parse_update_strategy` to return a tagged tuple. Update `check_updates` dispatcher. |
| `tests/test_check_updates.py` | Add 3 tests. |
| `tests/test_schema.py` | Add 1 negative test for `u-he:` (empty product). |

## Open questions

None — all design decisions made and approved.

## Out-of-scope follow-ups

- Tokyo Dawn vendor strategy (TDR Nova) — predictable URL but HTML scraping needed.
- Klanghelm — gated downloads, not automatable.
- MeldaProduction — version embedded in URL filename, requires page scraping.
- TAL Software (NoiseMaker, Vocoder) — stable URLs that change content silently. Better fit for a separate "stable-url hash refresh" feature.
- Decomposer (Sitala) — versioned URL but free version is frozen at 1.0; v2.0 is paid. Not worth tracking.
- Tytel (Helm) — abandoned upstream; tracking has no value.
