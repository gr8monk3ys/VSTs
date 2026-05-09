# Self-Updating Manifest (Phase 1) — Design

**Status:** Approved (design phase)
**Date:** 2026-05-09
**Scope:** `scripts/download-plugins.py`, `plugins.json`, `schemas/plugins.schema.json`, `tests/`. New CLI mode `--check-updates` (with optional `--apply`). Initial coverage: GitHub-released plugins only.
**Out of scope:** Vendor-website scraping (u-he, Tokyo Dawn, Klanghelm, MeldaProduction, TAL, Decomposer). Publisher-tier hash promotion. CI-bot PR creation.

## Problem

The `feature/checksum-verification` work that just landed exposed how badly the registry rots: 21 of ~50 URLs were dead, several plugins serve HTML/JSON instead of binaries, and version pins drift silently. Strict CI now fails loudly when this happens — but loud failure is not a fix. Without a tool that *detects* upstream version drift, the maintainer either manually re-audits the registry every few months (the path that produced the rot we just healed) or watches the URL-check cron go red and ignores it.

Today's manifest pins specific versions (e.g., Surge XT 1.3.4) by exact GitHub release tag. When upstream ships 1.3.5, the manifest stays at 1.3.4 forever unless someone manually edits `plugins.json`. Most affected plugins are GitHub-hosted with clean APIs — there is no reason this can't be detected automatically.

## Goals

1. A maintainer running one command can see whether any plugin's pinned version has drifted from upstream.
2. A maintainer running the same command with `--apply` can update `plugins.json` (URL, filename, sha256, version) for every entry whose update is automatable, in a single atomic write.
3. The mode is additive: existing entries without an automatable update path are reported as "manual" and otherwise untouched. No plugin is silently dropped.
4. CI can run `--check-updates` on a cron and surface drift via failing build.

## Non-goals

- **Vendor-website scraping.** Plugins hosted on vendor sites (u-he, Tokyo Dawn, Klanghelm, MeldaProduction, TAL, Decomposer) require per-vendor scraping logic. Each vendor reorganizes their CDN every few years. Treating them all in one feature is too much surface; they will be added incrementally in later phases as their patterns are documented.
- **Publisher-tier hash promotion.** Several GitHub-hosted projects publish `artifact_md5sum.txt` sidecars; bridging from those to a `hash_source: "publisher"` SHA-256 promotion needs a real threat-model review (MD5 vs SHA-256, what counts as "publisher-controlled," etc.). Deferred to its own design pass.
- **Auto-PR creation.** A future phase could wrap `--check-updates --apply` in a GitHub Actions cron that opens a PR. Out of scope here.
- **Pinning to specific tags vs. floating to latest at runtime.** This design maintains pin-then-update — the runtime always uses the pinned URL. `--check-updates` is the only thing that ever consults the GitHub API.

## Design

### 1. Data shape (`plugins.json`)

Each plugin entry gains an optional field:

```json
"name": "Surge XT",
"update_strategy": "github:surge-synthesizer/releases-xt",
"urls": { ... }
```

The field is optional. When omitted, the plugin has no automatable update path — `--check-updates` reports it under a "no strategy" header and otherwise leaves it alone.

`update_strategy` values, Phase 1:

- `"github:<owner>/<repo>"` — the manifest's URLs come from this GitHub repository's releases. Detection uses `GET /repos/{owner}/{repo}/releases/latest`.

The format is intentionally extensible. Future phases will add e.g. `"u-he"`, `"tokyodawn:nova"`, etc. — but those need their own designs and are not included here.

### 2. Initial coverage

The Phase 1 PR backfills `update_strategy` for every plugin whose existing URLs point at `github.com/<owner>/<repo>/releases/download/`:

| Plugin | Strategy |
|---|---|
| Surge XT | `github:surge-synthesizer/releases-xt` |
| Dexed | `github:asb2m10/dexed` |
| OB-Xd | `github:reales/OB-Xd` |
| Dragonfly Reverb | `github:michaelwillis/dragonfly-reverb` |
| BYOD | `github:Chowdhury-DSP/BYOD` |
| Airwindows Consolidated | `github:baconpaul/airwin2rack` |

Every other plugin (Helm, TAL-*, Tyrell N6, Zebralette, Valhalla, OTT, TDR Nova, Sitala, MeldaProduction MFreeFXBundle) has no `update_strategy` — they remain manually maintained.

### 3. Detection algorithm (`detect_latest_for_github`)

```python
def detect_latest_for_github(repo: str) -> dict:
    """Return {'tag': str, 'assets': [{'name': str, 'url': str, 'size': int}]}.

    Calls GET https://api.github.com/repos/{repo}/releases/latest with the same
    User-Agent the rest of the script uses. Network errors propagate.
    """
```

The Airwindows entry is a special case: its `update_strategy` is `github:baconpaul/airwin2rack`, but its release is pinned to a *rolling* tag (`DAWPlugin`) rather than `/latest`. The detection function takes an optional `tag` argument:

```python
def detect_latest_for_github(repo: str, tag: str | None = None) -> dict:
```

When `tag` is None, it queries `/releases/latest`. When `tag` is set, it queries `/releases/tags/{tag}`. The strategy field encodes both forms:

- `"github:owner/repo"` → `/releases/latest`
- `"github:owner/repo@tag"` → `/releases/tags/tag` (Airwindows uses `"github:baconpaul/airwin2rack@DAWPlugin"`)

### 4. Asset-matching algorithm (`find_matching_asset`)

Given a current per-platform `filename` and a list of `{name, url, size}` from a new release, find the asset that should replace it.

**Strategy A (exact-substitution):** if current name is `Surge-XT-macOS-1.3.4.dmg` and the detected tag bumped from `1.3.4` to `1.3.5`, replace `1.3.4` in the current name with `1.3.5` and look for that exact asset.

**Strategy B (token overlap):** split current filename on `-_.`, count overlap with each candidate asset's tokens, return the highest scorer (ties broken by smallest size delta from current — installers within an order of magnitude of each other are presumed to be the same artifact in different versions).

**Order:** try (A) first; if the exact substitution doesn't appear in the asset list, fall back to (B). Always print the matched asset name so a maintainer running with `--apply` can spot a wrong match before committing.

If neither strategy finds a match, the plugin is reported as `"DETECTION FAILED — please update manually"` and is left untouched.

### 5. CLI behavior

**Read-only (`--check-updates`):**

```
$ python3 scripts/download-plugins.py --check-updates

Checking 13 plugins (6 with github strategy, 7 manual)...

Synths
  Surge XT             1.3.4  → 1.3.4    no update
  Dexed                1.0.1  → 1.0.1    no update
  OB-Xd                2.19   → 2.19     no update
  Helm                 0.9.0  → ?        manual
  TAL-NoiseMaker       5.0.6  → ?        manual
  Tyrell N6            3.0.0  → ?        manual
  Zebralette           2.9.4  → ?        manual

Effects
  Valhalla Supermassive 5.0.0 → ?        manual
  Valhalla FreqEcho    1.2.8  → ?        manual
  OTT                  1.37   → ?        manual
  Dragonfly Reverb     3.2.10 → 3.2.11  ⬆ NEW VERSION
    macos:   dragonfly-reverb-3.2.11-macos-universal.dmg
    windows: dragonfly-reverb-3.2.11-win64.zip
    linux:   dragonfly-reverb-3.2.11-linux-x86_64.tar.xz
  BYOD                 1.3.0  → 1.3.0    no update
  TDR Nova             2.2.2  → ?        manual
  Airwindows Consolidated  2026-05-02-dc0ed69 → 2026-05-02-dc0ed69  no update

Instruments
  Sitala               1.0    → ?        manual

Bundles
  MeldaProduction MFreeFXBundle 02.21 → ? manual

1 update available. Run with --apply to update plugins.json.
```

Exit 0 when no updates available *and* no detection failures. Exit 1 when at least one update is available *or* at least one plugin's detection failed (CI on cron wants to surface "something is wrong" of either kind). Exit 2 only on global failures (auth/rate-limit) that prevent the run from completing. CI can use this directly.

**Apply (`--check-updates --apply`):**

For each plugin with detected drift:
1. For each platform in `plugin['urls']`, find the matching asset via `find_matching_asset`.
2. If found: update `urls[plat].url` and `urls[plat].filename`, clear `urls[plat].sha256` and `urls[plat].hash_source` (so the next step is forced to recompute).
3. If not found for some platforms but matched for others: leave the unmatched platforms unchanged (with their old URL and hash) and warn — partial bumps are honest.
4. Update the plugin's top-level `version` field to the new tag.

After all plugins are processed in memory, call the existing `recompute_hashes(plugins_data, force=False)` — only the entries whose `sha256` was cleared get re-hashed. Then write `plugins.json`.

The atomic write is preserved: if `recompute_hashes` raises (HTTP error during hashing), the file on disk is unchanged, exactly as it is for `--compute-hashes`.

### 6. Schema additions

Add an optional `update_strategy` field to the `plugin` definition:

```json
"update_strategy": {
  "type": "string",
  "pattern": "^github:[\\w.-]+/[\\w.-]+(@[\\w.-]+)?$"
}
```

The pattern admits `github:owner/repo` and `github:owner/repo@tag`. Future strategies will extend the pattern (or, if it grows unwieldy, refactor to `oneOf` with per-strategy schemas).

### 7. Failure modes

| Trigger | Action |
|---|---|
| Plugin has no `update_strategy` | Reported as "manual" in output; not modified by `--apply`. |
| GitHub API returns 404 (repo or release missing) | Plugin reported as `"DETECTION FAILED — repo or release not found"`; not modified. |
| GitHub API returns 401/403 (rate-limited or auth required) | Print a clear error, exit 2. The user should set `GITHUB_TOKEN` or wait. The implementation reads `GITHUB_TOKEN` from the environment and adds `Authorization: Bearer <token>` to API requests when it is set; this raises the rate limit from 60/hr to 5000/hr. |
| Asset-matching fails (no candidate asset matches current filename) | Plugin reported as `"DETECTION FAILED — no matching asset"`; not modified. |
| Network error mid-`--apply` (during `recompute_hashes`) | Existing behavior preserved — exception propagates, file unchanged on disk. |
| Schema rejects a malformed `update_strategy` value | CI fails the lint job. |

### 8. Testing

Five new tests in `tests/test_check_updates.py`, plus one schema test extension:

1. **`detect_latest_for_github` reads tag + assets** — mock the GitHub API endpoint via the existing mock-server fixture; assert the returned dict has the expected `tag` and asset list.
2. **`find_matching_asset` exact-substitution** — given a current filename `Surge-XT-1.3.4-mac.dmg` and a candidate list with `Surge-XT-1.3.5-mac.dmg`, return that asset.
3. **`find_matching_asset` falls through to token-overlap** — given a current filename whose pattern doesn't match any candidate exactly, returns the highest-scoring overlap.
4. **`--check-updates` read-only on drifted fixture** — fixture with one plugin whose pinned tag is one behind a mock release; assert exit code 1, drift line printed, plugins.json unchanged.
5. **`--check-updates --apply` on drifted fixture** — same fixture; assert exit code 0, plugins.json updated with new URL + filename + version + recomputed hash.

Schema test extension (add to existing `tests/test_schema.py`): assert that `"update_strategy": "not-a-valid-format"` is rejected by the schema.

The mock server already used in Tasks 1-3 of the verification work is reused. The `gh api` calls in detection are routed through `urllib.request.urlopen` exactly as the rest of the script does, so the same mock-server fixture works.

### 9. CI integration

A new step in the existing `lint` job:

```yaml
      - name: Check for upstream version drift
        run: |
          python3 scripts/download-plugins.py --check-updates
        continue-on-error: true
```

`continue-on-error: true` because drift is informational, not a build-blocker — the maintainer wants to know but doesn't want every PR to fail because Surge XT shipped 1.3.5 last night. The cron schedule (`'0 0 * * 0'` already in the workflow) will run weekly and surface drift via job-summary.

The URL-check job stays unchanged.

## File changes summary

| File | Change |
|---|---|
| `plugins.json` | Add `update_strategy` to 6 GitHub-hosted plugin entries (Surge XT, Dexed, OB-Xd, Dragonfly Reverb, BYOD, Airwindows). |
| `schemas/plugins.schema.json` | Add optional `update_strategy` field with pattern enforcement. |
| `scripts/download-plugins.py` | Add `detect_latest_for_github`, `find_matching_asset`, `--check-updates` flag, `--apply` flag, branch in `main()` for the new mode. |
| `tests/test_check_updates.py` (new) | 5 tests covering detection, matching, read-only, --apply, edge cases. |
| `tests/test_schema.py` | One additional negative test for malformed `update_strategy`. |
| `.github/workflows/ci.yml` | Add the `Check for upstream version drift` step in `lint` job. |

## Open questions

None — all design decisions have been made and approved during brainstorming.

## Out-of-scope follow-ups

- **Vendor-website scraping** for u-he, Tokyo Dawn, Klanghelm, etc. Each vendor needs its own `update_strategy` value and detection logic. Tackle one vendor per PR.
- **Publisher-tier hash promotion** for plugins that publish `artifact_md5sum.txt` (Surge XT, Airwindows, Dexed). Needs a separate threat-model design pass.
- **CI-bot auto-PR.** Wrap `--check-updates --apply` in a GitHub Actions cron that opens a PR. Once Phase 1 lands and proves stable, this is the obvious next move.
- **Hash-algorithm flexibility.** If publisher-tier promotion needs MD5 verification, the schema and runtime need to support an optional `md5` field alongside `sha256`. Not blocking; comes with the publisher-tier work.
