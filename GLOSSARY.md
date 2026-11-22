# Glossary

Terms as used in `plugins.json`, `schemas/plugins.schema.json` and `src/free_vst_plugins/cli.py`.

**Manifest**
The catalog file `plugins.json` (`meta`, `plugins`, `manual_download`). It is the trust root: every URL and hash the downloader acts on comes from it. Validated by `schemas/plugins.schema.json`.

**Entry**
One plugin or sample library in the Manifest, with `name`, `description`, per-platform `urls`, and optional `version`, `formats`, `website`, `github`, `open_source`, `update_strategy`.

**Category**
A key under `plugins`: `synths`, `effects`, `instruments`, `bundles`, `samples`. The first four are `DEFAULT_CATEGORIES` (downloaded by default); `samples` is in `OPT_IN_CATEGORIES` and needs `--samples`.
_Avoid_: type, group.

**Sample library**
An Entry in the `samples` Category: an SFZ library distributed as an archive. Listed as "Sample Libraries (SFZ)".

**Platform**
One of `macos`, `windows`, `linux` (`get_platform`). An Entry may have no URL for a Platform; `--list` marks it "(not available for <platform>)".

**Download target**
The resolved result for one Entry on one Platform (`DownloadTarget`, built by `resolve_target`): url, safe filename inside the download folder, sha256, hash source.

**Download folder**
Where files land: `--dir`, default `~/Downloads/VST-Plugins` (`get_default_download_dir`).

**Hash source**
`hash_source` on a per-platform URL record: where its `sha256` came from. `self` means the maintainer hashed the downloaded bytes (`--compute-hashes`).

**Verified download**
A file whose sha256 matched the Manifest in the current run. Written as a `.part` file and renamed only after the hash matches; a mismatch raises `ChecksumMismatch`, deletes the file and exits 1.

**Verify mode**
`--verify`: re-hash files already in the Download folder against the Manifest without downloading (`verify_downloads`).

**Manual download**
An item in the Manifest's `manual_download` list: a plugin the tool never fetches (`reason` says why, e.g. a login or licence wall). Only listed by `--list`.

**Update strategy**
`update_strategy` on an Entry, e.g. `github:<owner>/<repo>`: how `--check-updates` finds a newer upstream version (`check_updates`, `_parse_update_strategy`).

**Drift**
An upstream release or stable URL whose content differs from what the Manifest pins; reported by `--check-updates` (`detect_drift_for_stable_url`).

**Catalog page**
The static HTML site generated from the Manifest by `scripts/build_site.py` and published by `pages.yml`.
