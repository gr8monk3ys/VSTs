# Free VST Plugins

A manifest of 17 free, legally redistributable VST plugins (7 synths, 8
effects, a drum sampler, a 37-effect bundle), each pinned to a download URL
and a SHA-256 hash, plus a downloader that refuses any file whose hash
doesn't match.

Browse the catalog: https://gr8monk3ys.github.io/VSTs/

The point is the pin, not the list. Vendors move files, re-upload installers
under the same URL, and occasionally get compromised; a plain link list can't
tell you which of those happened. Every entry in `plugins.json` records where
its hash came from (`hash_source: publisher` when the vendor publishes one,
`self` when it was computed at pin time, trust-on-first-use), and the
downloader re-hashes cached files too, so a file that changed on disk is
deleted rather than installed. A weekly workflow checks upstream releases and
opens a PR when a URL or hash drifts; that diff is the moment a new binary
gets trusted. 9 more plugins that sit behind account walls are listed in the
manifest under `manual_download` with no URL.

Runs on macOS, Windows and Linux with Python 3.9+ and no dependencies.

## Install and run

```bash
pipx install git+https://github.com/gr8monk3ys/VSTs.git
free-vst-plugins --list          # fetches the latest manifest from this repo
free-vst-plugins --synths        # downloads to ~/Downloads/VST-Plugins
```

Or from a checkout, no install:

```bash
git clone https://github.com/gr8monk3ys/VSTs.git
cd VSTs
python3 scripts/download-plugins.py --list
python3 scripts/download-plugins.py               # everything (~1.5 GB)
python3 scripts/download-plugins.py --effects --dir ~/Music/Plugins
python3 scripts/download-plugins.py --only surge --only dexed
python3 scripts/download-plugins.py --verify      # re-hash what's on disk, no downloads
python3 scripts/download-plugins.py --platform windows
```

`scripts/download-plugins.sh` and `scripts/download-plugins.ps1` wrap the same
script for macOS and Windows shells.

Installers land in `~/Downloads/VST-Plugins/` (`%USERPROFILE%\Downloads\VST-Plugins\`
on Windows). Run each `.dmg`/`.pkg`/`.exe`/`.msi`, or unpack archives into
`~/.vst3/` on Linux, then rescan plugins in your DAW.

## What's in the manifest

| Category | Plugins |
|---|---|
| Synths | Surge XT, Dexed, OB-Xd, Helm, TAL-NoiseMaker, Tyrell N6, Zebralette |
| Effects | Valhalla Supermassive, Valhalla FreqEcho, OTT, Dragonfly Reverb, BYOD, TDR Nova, Airwindows Consolidated, TAL-Vocoder |
| Instruments | Sitala |
| Bundles | MeldaProduction MFreeFXBundle |

Not every plugin ships for every platform; `--list` shows what's available for
yours. The catalog page has links and per-platform details.

## Maintaining the manifest

```bash
pip install ruff pytest jsonschema
python scripts/validate_manifest.py                    # JSON + schema
ruff check src/ scripts/ tests/ && ruff format --check src/ scripts/ tests/
pytest tests/                                          # 45 tests, local mock HTTP server, no network
```

Adding a plugin: add an entry to `plugins.json` with URLs for each platform it
ships on, then `python3 scripts/download-plugins.py --compute-hashes --in-place`
to pin the hashes, and run the checks above. `--check-updates` reports upstream
drift for entries with an `update_strategy` (GitHub releases, u-he, or a stable
URL whose content is re-hashed); `--apply` writes the new pins back.

Layout: `plugins.json` (the manifest), `schemas/plugins.schema.json`,
`src/free_vst_plugins/cli.py` (the downloader), `scripts/build_site.py`
(generates the catalog page), `scripts/validate_urls.py` (CI reachability check).

## License

MIT for this repo. Each plugin keeps its own license; nothing is hosted here,
every download comes from the vendor.
