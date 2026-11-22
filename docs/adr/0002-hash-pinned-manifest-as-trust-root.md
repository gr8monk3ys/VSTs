# Hash-pinned manifest is the trust root for downloads

Status: accepted

The downloader (`src/free_vst_plugins/cli.py`) is stdlib-only and fetches installers that users then run as admin. Every Entry in `plugins.json` pins a `sha256` per platform URL (schema in `schemas/plugins.schema.json`). A file is kept only after its hash matches (`download_file` writes a `.part` file and renames on success), network access goes through `open_url` (HTTPS only, no redirect off HTTPS), filenames go through `resolve_target`, and only archives verified in the current run are extracted. Version bumps are re-pinned by `--check-updates` / `--compute-hashes` rather than trusting upstream at download time.

Consequence: adding or updating an Entry means hashing the real bytes first, and schema changes must keep URL, filename and sha256 rules at least as strict.
