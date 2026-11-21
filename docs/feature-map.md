# Feature map

What a user (or the maintainer) can reach in this repo, one row per feature.
This is a CLI plus a generated static page, so rows are commands and entry
points. `P` below is `uv run python scripts/download-plugins.py` (from a
checkout) or `free-vst-plugins` (after `pipx install`); both run
`src/free_vst_plugins/cli.py`.

Download rows are checked against a local manifest (`--plugins-json`) whose
URLs point at `python3 -m http.server` on `127.0.0.1`: never download real
plugins to check a feature.

## Downloader (users)

| Feature | Where | How to reach it | How to check it works |
|---|---|---|---|
| List the catalog for my platform | `cli.py` `list_plugins` | `P --list [--platform macos\|windows\|linux]` | Prints Synths, Effects, Instruments, Bundles, "Sample Libraries (SFZ) - only with --samples" and "Manual Download Required" sections; entries missing for the platform are marked `(not available for <platform>)` |
| Download every plugin (no sample libraries) | `cli.py` `main` | `P` or `P --all` | Each file prints `✓ <name> - verified (<hash_source>)`; sample libraries are not fetched |
| Download one category | `cli.py` `select_categories` | `P --synths` / `--effects` / `--instruments` / `--bundles` | Only that category's files land in the download folder |
| Download SFZ sample libraries | `cli.py` `OPT_IN_CATEGORIES` | `P --samples` (alone or with a category flag) | Library archives download and `.zip`s are extracted next to them (`Extracted <file>`) |
| Download by name | `cli.py` `--only` | `P --only surge --only dexed` (case-insensitive substring, repeatable, also reaches sample libraries) | Only matching entries download |
| Choose the download folder | `cli.py` `--dir` | `P --dir ~/Music/Plugins` (default `~/Downloads/VST-Plugins`) | Output shows `Download directory: <dir>` and files land there |
| Refuse a file whose hash doesn't match | `cli.py` `download_file` | Any download | A mismatch prints `HASH MISMATCH`, expected/actual hashes, `Aborting. The bad file has been deleted.` and exits 1 |
| Re-check files already on disk | `cli.py` `verify_downloads` | `P --verify [--dir DIR]` | `N file(s) checked, 0 mismatch(es)` and exit 0; a changed file prints `HASH MISMATCH` and exits 1 |
| Use another manifest | `cli.py` `--plugins-json` | `P --plugins-json path/to/plugins.json` (default: the checkout's `plugins.json`, then the canonical remote one) | First line is `Using manifest: <path>` |
| Shell wrappers | `scripts/download-plugins.sh`, `scripts/download-plugins.ps1` | `./scripts/download-plugins.sh --list`, `pwsh scripts/download-plugins.ps1 --list` | Same output as `P` with the same arguments |

## Catalog page

| Feature | Where | How to reach it | How to check it works |
|---|---|---|---|
| Browse the catalog | `scripts/build_site.py` -> `_site/index.html`, published by `pages.yml` | https://gr8monk3ys.github.io/VSTs/, or locally `uv run python scripts/build_site.py --out _site` and open `_site/index.html` | Page shows plugin, sample-library and hash-verified counts, then one card per entry per category with platform, format and `sha256 ✓` badges |
| Filter the catalog | `#q` search box on the page | Type in "Filter plugins…" | Cards that don't contain the text are hidden (typing `surge` leaves Surge XT and OB-Xf) |

## Maintaining the manifest

| Feature | Where | How to reach it | How to check it works |
|---|---|---|---|
| Validate the manifest | `scripts/validate_manifest.py`, `schemas/plugins.schema.json` | `uv run python scripts/validate_manifest.py` | `plugins.json is valid JSON and conforms to the schema` |
| Pin hashes for new entries | `cli.py` `--compute-hashes` | `P --compute-hashes [--in-place] [--force-recompute]` | Emits the manifest with `sha256` filled from the downloaded bytes; existing hashes kept unless `--force-recompute` |
| Detect upstream drift | `cli.py` `--check-updates` | `P --check-updates [--apply]` (all entries with `update_strategy`; `--only` does not narrow it) | One row per entry (`current → latest`, `manual`, or `DETECTION FAILED`), then `N update(s) available`; `--apply` writes the new pins. Offline check: `uv run pytest tests/test_check_updates.py` |
| Check download URLs are still up | `scripts/validate_urls.py` (scheduled CI job) | `uv run python scripts/validate_urls.py` | `N URLs checked, M failed`; exit 1 when any URL is dead |
| Run every check CI gates on | `scripts/verify.py` | `uv run python scripts/verify.py` | Ends `verify: lint + test passed`, exit 0 |
