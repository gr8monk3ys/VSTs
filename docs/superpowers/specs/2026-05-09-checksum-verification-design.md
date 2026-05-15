# Checksum Verification for Plugin Downloads — Design

**Status:** Approved (design phase)
**Date:** 2026-05-09
**Scope:** `plugins.json`, `scripts/download-plugins.py`, `.github/workflows/ci.yml`, plus a new JSON schema file.
**Out of scope:** auto-installing downloaded plugins, self-updating manifest (version bumps), the `.sh` and `.ps1` shell scripts (untouched — only Python is exercised in CI).

## Problem

`scripts/download-plugins.py` fetches installer binaries (`.dmg`, `.pkg`, `.exe`, `.deb`, `.zip`) from ~15 third-party domains and the user runs them with admin privileges. There is no integrity check between download and execution. A corrupted download, an MITM, or a compromised CDN would all silently produce installer files the user is encouraged to run.

The `SECURITY.md` file exists but the script's `download_file()` (`scripts/download-plugins.py:76-105`) has no SHA256 or signature step.

## Goals

1. Every binary the script downloads is checksum-verified before the script considers it "downloaded successfully."
2. The trust tier of each checksum is legible to users — a hash committed to the repo by a maintainer (TOFU) and a hash sourced from the publisher's signed release notes are both useful, but they are not equivalent, and the design must not pretend they are.
3. CI guarantees that `plugins.json` is well-formed before it lands. The script trusts the data is valid at runtime.
4. Failure modes are loud and unambiguous. Hash mismatch is treated as a stop-everything event.

## Non-goals

- Verifying the `manual_download` entries (these are not on the automated download path).
- Verifying the `.sh` and `.ps1` scripts' downloads (the README already recommends Python; these scripts are not exercised in CI and are out of scope for this work).
- Auto-promoting hashes from `self` to `publisher` tier (the act of verification is the security-meaningful step; automating it would just move the trust problem).
- Continuous version updates (a separate "self-updating manifest" feature, deferred).

## Design

### 1. Data shape (`plugins.json`)

Each per-platform URL entry gains two mandatory fields:

```json
"macos": {
  "url": "https://.../surge-xt-macOS-1.3.4.dmg",
  "filename": "surge-xt-macOS-1.3.4.dmg",
  "sha256": "<64 lowercase hex chars>",
  "hash_source": "publisher" | "self"
}
```

- `sha256`: lowercase hex SHA-256 of the binary at `url`. Required.
- `hash_source`: `"publisher"` if the hash was sourced from a publisher-controlled channel (`.sha256` sidecar, signed release notes, vendor download page); `"self"` if a maintainer computed it after a TOFU download. Required.

The current dynamic Airwindows entry (which fetches the latest release via the GitHub API in `scripts/download-plugins.py:107-151`) is replaced with a pinned entry following the same shape. The `download_airwindows()` function is deleted; Airwindows becomes a normal entry. The "always latest" behavior is deferred to a future self-updating-manifest feature, which will update URL and hash atomically across all entries.

The `manual_download` array is unchanged.

### 2. CI enforcement

A new step in the existing `lint` job in `.github/workflows/ci.yml` validates `plugins.json` against a JSON schema (committed to the repo). The schema requires:

- For every plugin, every `urls.{macos,windows,linux}` entry that is present has both `sha256` and `hash_source`.
- `sha256` matches `^[a-f0-9]{64}$`.
- `hash_source` is one of `"publisher"` or `"self"`.

This step **fails CI on violation** — no `|| true`.

Two existing CI weaknesses are corrected as part of this work because the runtime depends on CI being authoritative:

- `.github/workflows/ci.yml:31` — remove the `|| true` from `ruff check`. Lint failures fail the build.
- `.github/workflows/ci.yml:148` — uncomment the `sys.exit(1)` in the URL-check job. Unreachable URLs fail the build.

### 3. Verification flow in the script

`download_file()` is rewritten to verify as it streams.

```
def download_file(url, filepath, name, expected_sha256, hash_source):
    if filepath.exists():
        if sha256_of(filepath) == expected_sha256:
            print "skipped (already verified, {hash_source})"
            return True
        else:
            unlink filepath  # bad cached copy
            # fall through to redownload

    open response stream
    open filepath for write
    h = hashlib.sha256()
    for chunk in stream(64KB):
        write chunk to file
        h.update(chunk)
    actual = h.hexdigest()

    if actual != expected_sha256:
        unlink filepath
        raise ChecksumMismatch(name, expected_sha256, actual)

    print "verified ({hash_source})"
    return True
```

Properties:

- One I/O pass. The hash is computed during download, not in a second read.
- The cached-file short-circuit re-verifies. A previously-corrupted file does not stay trusted forever.
- Mismatch deletes the partial/bad file, so a retry actually re-downloads instead of short-circuiting on the bad cached copy.
- The trust tier is printed on success so users see whether they are getting publisher-tier or self-tier verification.

`main()` catches `ChecksumMismatch`, prints a clear failure summary, exits 1. No partial-success continuation: per the threat model, hash mismatch is a stop-everything event.

### 4. Backfill workflow

A new CLI mode is added: `python3 scripts/download-plugins.py --compute-hashes`.

- This mode does **not** call the verifying `download_file()` from section 3 (which requires a known expected hash and would reject the call). It uses a separate `compute_hash_for_url()` helper that streams a URL and returns the SHA-256 digest without writing a permanent file.
- For each plugin in `plugins.json`, for each platform that has a URL, the script computes the SHA-256 of the binary at that URL and emits an updated `plugins.json` (to stdout by default, or to `plugins.json` itself with `--in-place`).
- The mode is tolerant of plugins that already have a `sha256` field — it recomputes and reports any drift, but does not overwrite existing hashes unless `--force-recompute` is also passed. This protects against accidentally clobbering manually-curated `"publisher"` hashes.
- All hashes produced by this mode are tagged `"hash_source": "self"`. The mode does not produce `"publisher"` hashes — those are always added by hand.
- A maintainer runs this once on a trusted machine to backfill the existing ~20 plugins, sanity-checks the diff, and commits the result as part of the same PR that lands the verification feature.

Promotion from `self` to `publisher` is a manual `plugins.json` edit performed by a maintainer who has independently confirmed the hash from a publisher-controlled channel (release notes, signed `.sha256` sidecar, etc.). The script does not automate promotion. Reading a publisher's release notes is the trust event; automating it would defeat the purpose.

### 5. Testing

Three tests are added, all run in the existing matrix (Ubuntu / macOS / Windows × Python 3.9 / 3.11 / 3.12) in `.github/workflows/ci.yml`:

1. **Schema validation test** — `plugins.json` validates against the schema. Mirrors the lint job for visibility.
2. **Mismatch handling test** — mock a download response whose body hashes to something other than the value committed in a fixture `plugins.json`. Assert the script exits non-zero and the partial file is removed.
3. **Re-verification test** — pre-place a file on disk with content that hashes wrong relative to the fixture's `sha256`. Assert that the script's "already downloaded" short-circuit detects the mismatch instead of trusting the existing file.

No live-network download test is added — CI already has a URL-reachability job for that concern, and live downloads are flaky.

## Failure modes (single source of truth)

| Trigger | Action |
| --- | --- |
| `sha256` mismatch (fresh download) | Delete partial file. Print red error with name, expected, actual. Raise. `main()` catches, prints summary, exits 1. |
| `sha256` mismatch (cached file) | Delete cached file. Re-download. If the re-download mismatches, treat as fresh-download mismatch above. |
| `sha256` field missing in `plugins.json` | Cannot occur at runtime — CI rejects. If it somehow occurs, the script raises immediately with a clear message ("CI invariant violated: missing sha256 for ..."). |
| `hash_source` not in {`publisher`, `self`} | Same as above — CI rejects; runtime treats as a CI invariant violation. |
| Network error during download | Existing behavior preserved (no change). |

## File changes summary

| File | Change |
| --- | --- |
| `plugins.json` | Add `sha256` + `hash_source` to every per-platform URL entry. Replace dynamic Airwindows entry with a pinned one in the same shape. |
| `schemas/plugins.schema.json` (new) | JSON schema enforcing the field shape. |
| `scripts/download-plugins.py` | Rewrite `download_file()` to stream-verify. Delete `download_airwindows()`. Add `--compute-hashes`, `--in-place`, and `--force-recompute` flags. Add `compute_hash_for_url()` helper. |
| `.github/workflows/ci.yml` | Add schema validation step. Remove `\|\| true` from ruff. Uncomment `sys.exit(1)` in URL check. Add three new tests to the matrix. |
| `tests/` (new directory) | Three test files for the new behaviors. |

## Open questions

None. All design decisions have been made and approved during brainstorming.

## Out-of-scope follow-ups (for future work)

- **Self-updating manifest.** Replace pinned URLs with publisher-aware sources (GitHub releases API, etc.) so versions stay current automatically. This is the right home for re-introducing "always latest" behavior, and it would update URL and hash atomically.
- **Auto-installation.** Move beyond download to actually run installers per-OS (`installer -pkg`, `dpkg -i`, silent `.exe`).
- **Generate README tables from `plugins.json`.** Drift waiting to happen today; not in scope here.
