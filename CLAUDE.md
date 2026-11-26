# VSTs

Python downloader (`src/free_vst_plugins/cli.py`, stdlib only) for the catalog in
`plugins.json`, validated by `schemas/plugins.schema.json`. See `README.md`.

## How we work

`.claude/settings.json` loads four plugins from the `lorenzos-claude-code`
marketplace (gr8monk3ys/skills), in every clone and every cloud session. Use
them every time, not only when one happens to trigger:

- **Matt Pocock's skills** (`mattpocock-skills`) for the engineering process:
  `grilling` before building something new, `tdd` for any behaviour change,
  `diagnosing-bugs` for bugs, `code-review` before calling work done and `pr`
  for the PR body. Prefer them over overlapping skills from other plugins.
- **Impeccable** for any UI, layout, styling or on-screen copy: run
  `/impeccable critique` or `/impeccable audit` on it before you're done.
- **Ponytail** is always on: the simplest code that works, no unrequested
  abstractions or dependencies. Run `ponytail-review` on the diff before
  opening a PR and cut what the task didn't need.
- **Tests:** run `./scripts/verify` before finishing. A hook runs it anyway
  and won't let the session end while it fails. Never skip, weaken or delete a
  test to get it green.

## Checks

`make check` (= `uv run python scripts/verify.py`) runs exactly what CI gates on (`lint`: manifest schema,
ruff check, ruff format --check, py_compile; `test`: CLI `--help`/`--list`, platform
detection, pytest); CI calls the same script per job. Individual tools: `uv run pytest`,
`uv run ruff check`, `uv run ruff format --check src/ scripts/ tests/`.
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

Single-context: `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
