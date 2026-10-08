# VSTs

Python downloader (`src/free_vst_plugins/cli.py`, stdlib only) for the catalog in
`plugins.json`, validated by `schemas/plugins.schema.json`. See `README.md`.

## Checks

`uv run pytest` and `uv run ruff check` (plus `uv run ruff format --check src/ scripts/ tests/`).
Tests use a local mock HTTP server; never download real plugins or run installers to test.

## Security invariants

The manifest is the trust root, and downloads end up run as admin. Keep these true:

- All network access goes through `open_url`: HTTPS only (plain HTTP to loopback is for
  the test server), no redirect off HTTPS, no `Authorization` on a cross-host redirect.
- Downloads go through `resolve_target` (safe filename inside the download folder,
  well-formed sha256) and `download_file` (`.part` file, renamed only after the hash matches).
- Only archives verified in the current run are extracted, and zip members that escape
  the folder make the archive refused.
- Schema changes must keep URL, filename and sha256 rules at least as strict.

## Agent skills

### Issue tracker

GitHub Issues on `gr8monk3ys/VSTs`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles, label string equal to role name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
