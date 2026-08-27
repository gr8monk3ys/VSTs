#!/usr/bin/env python3
"""Generate the static catalog site from plugins.json.

Stdlib-only, single self-contained HTML page. Used by the pages.yml workflow;
run locally with:  python scripts/build_site.py [--out _site]
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

REPO_URL = "https://github.com/gr8monk3ys/VSTs"

PLATFORM_LABELS = {"macos": "macOS", "windows": "Windows", "linux": "Linux"}

CATEGORY_ICONS = {
    "synths": "〜",
    "effects": "◈",
    "instruments": "♪",
    "bundles": "▣",
}

CSS = """
:root {
  --bg: #f6f5f2; --panel: #ffffff; --ink: #1f2328; --muted: #656d76;
  --line: #e3e0da; --accent: #b4541f; --accent-ink: #ffffff;
  --chip: #efece6; --good: #1a7f37;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14161a; --panel: #1c1f26; --ink: #e6e4df; --muted: #9aa1ab;
    --line: #2c313a; --accent: #e07a42; --accent-ink: #14161a;
    --chip: #262b33; --good: #4ac26b;
  }
}
* { box-sizing: border-box; margin: 0; }
body {
  background: var(--bg); color: var(--ink);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
  padding: 0 1.25rem 4rem;
}
main { max-width: 960px; margin: 0 auto; }
header.hero { padding: 3.5rem 0 1.5rem; }
header.hero h1 { font-size: 2rem; letter-spacing: -0.02em; }
header.hero p.tag { color: var(--muted); margin-top: 0.4rem; max-width: 46rem; }
.stats { display: flex; gap: 2rem; flex-wrap: wrap; margin: 1.4rem 0 0.5rem; }
.stats div strong { display: block; font-size: 1.4rem; }
.stats div span { color: var(--muted); font-size: 0.85rem; }
.controls { position: sticky; top: 0; background: var(--bg); padding: 0.8rem 0; z-index: 2; }
input#q {
  width: 100%; padding: 0.65rem 0.9rem; font-size: 1rem; color: var(--ink);
  background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
}
h2.cat { margin: 2.2rem 0 0.9rem; font-size: 1.15rem; }
h2.cat .icon { color: var(--accent); margin-right: 0.4rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.9rem; }
.card {
  background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 1rem 1.1rem; display: flex; flex-direction: column; gap: 0.5rem;
}
.card h3 { font-size: 1.02rem; }
.card h3 a { color: var(--ink); text-decoration: none; }
.card h3 a:hover { color: var(--accent); }
.card p.desc { color: var(--muted); font-size: 0.88rem; flex: 1; }
.badges { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.badge {
  font-size: 0.72rem; padding: 0.12rem 0.5rem; border-radius: 99px;
  background: var(--chip); color: var(--muted); border: 1px solid var(--line);
}
.badge.verified { color: var(--good); border-color: var(--good); background: transparent; }
.badge.oss { color: var(--accent); border-color: var(--accent); background: transparent; }
.meta { font-size: 0.78rem; color: var(--muted); }
section.manual .card { border-style: dashed; }
footer { margin-top: 3.5rem; padding-top: 1.2rem; border-top: 1px solid var(--line);
  color: var(--muted); font-size: 0.85rem; }
footer a { color: var(--accent); }
.hidden { display: none; }
a.cta {
  display: inline-block; margin-top: 1rem; background: var(--accent); color: var(--accent-ink);
  padding: 0.5rem 1rem; border-radius: 8px; text-decoration: none; font-weight: 600;
}
code.inline { background: var(--chip); padding: 0.1rem 0.4rem; border-radius: 5px; font-size: 0.85em; }
"""

JS = """
const q = document.getElementById('q');
q.addEventListener('input', () => {
  const needle = q.value.trim().toLowerCase();
  document.querySelectorAll('.card').forEach(card => {
    card.classList.toggle('hidden', !card.dataset.text.includes(needle));
  });
  document.querySelectorAll('section[data-cat]').forEach(sec => {
    const any = sec.querySelectorAll('.card:not(.hidden)').length > 0;
    sec.classList.toggle('hidden', !any);
  });
});
"""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_plugin_card(plugin: dict) -> str:
    name = esc(plugin.get("name", "Unknown"))
    desc = esc(plugin.get("description", ""))
    website = esc(plugin.get("website") or plugin.get("github") or REPO_URL)
    version = plugin.get("version")

    badges = []
    urls = plugin.get("urls", {})
    for plat in ("macos", "windows", "linux"):
        entry = urls.get(plat)
        if isinstance(entry, dict) and entry.get("url"):
            badges.append(f'<span class="badge">{PLATFORM_LABELS[plat]}</span>')
    badges.extend(
        f'<span class="badge">{esc(fmt)}</span>' for fmt in plugin.get("formats", [])
    )
    if any(
        isinstance(e, dict) and e.get("sha256")
        for e in urls.values()
        if isinstance(e, dict)
    ):
        badges.append('<span class="badge verified">sha256 ✓</span>')
    if plugin.get("open_source"):
        badges.append('<span class="badge oss">open source</span>')

    meta = f'<div class="meta">v{esc(version)}</div>' if version else ""
    search_text = esc(f"{name} {desc}".lower())

    return (
        f'<article class="card" data-text="{search_text}">'
        f'<h3><a href="{website}" rel="noopener">{name}</a></h3>'
        f'<p class="desc">{desc}</p>'
        f'<div class="badges">{"".join(badges)}</div>{meta}'
        f"</article>"
    )


def render_manual_card(item: dict) -> str:
    name = esc(item.get("name", "Unknown"))
    desc = esc(item.get("description", ""))
    website = esc(item.get("website", REPO_URL))
    badges = "".join(
        f'<span class="badge">{PLATFORM_LABELS.get(p, esc(p))}</span>'
        for p in item.get("platforms", [])
    )
    search_text = esc(f"{name} {desc}".lower())
    return (
        f'<article class="card" data-text="{search_text}">'
        f'<h3><a href="{website}" rel="noopener">{name}</a></h3>'
        f'<p class="desc">{desc}</p>'
        f'<div class="badges">{badges}</div>'
        f"</article>"
    )


def build_html(data: dict) -> str:
    meta = data.get("meta", {})
    plugins = data.get("plugins", {})
    manual = data.get("manual_download", [])

    n_plugins = sum(len(v) for v in plugins.values())
    n_verified = sum(
        1
        for cat in plugins.values()
        for p in cat
        if any(
            isinstance(e, dict) and e.get("sha256") for e in p.get("urls", {}).values()
        )
    )

    sections = []
    for category in ("synths", "effects", "instruments", "bundles"):
        items = plugins.get(category)
        if not items:
            continue
        icon = CATEGORY_ICONS.get(category, "•")
        cards = "".join(render_plugin_card(p) for p in items)
        sections.append(
            f'<section data-cat="{esc(category)}">'
            f'<h2 class="cat"><span class="icon">{icon}</span>{esc(category.title())}</h2>'
            f'<div class="grid">{cards}</div></section>'
        )
    for category in sorted(
        set(plugins) - {"synths", "effects", "instruments", "bundles"}
    ):
        cards = "".join(render_plugin_card(p) for p in plugins[category])
        sections.append(
            f'<section data-cat="{esc(category)}">'
            f'<h2 class="cat"><span class="icon">•</span>{esc(category.title())}</h2>'
            f'<div class="grid">{cards}</div></section>'
        )

    if manual:
        cards = "".join(render_manual_card(m) for m in manual)
        sections.append(
            '<section class="manual" data-cat="manual">'
            '<h2 class="cat"><span class="icon">↗</span>Manual Download</h2>'
            '<p class="meta" style="margin-bottom:0.9rem">These vendors gate their '
            "downloads behind accounts or unversioned URLs — grab them directly.</p>"
            f'<div class="grid">{cards}</div></section>'
        )

    updated = esc(meta.get("updated", ""))
    description = esc(
        meta.get(
            "description",
            "Curated collection of high-quality free VST plugins",
        )
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Free VST Plugins</title>
<meta name="description" content="{description}">
<style>{CSS}</style>
</head>
<body>
<main>
<header class="hero">
  <h1>Free VST Plugins</h1>
  <p class="tag">{description}. Every download is pinned to a URL and SHA-256
  hash in a version-controlled manifest, and installs with one command.</p>
  <div class="stats">
    <div><strong>{n_plugins}</strong><span>plugins</span></div>
    <div><strong>{n_verified}</strong><span>hash-verified</span></div>
    <div><strong>3</strong><span>platforms</span></div>
    <div><strong>{updated}</strong><span>manifest updated</span></div>
  </div>
  <a class="cta" href="{REPO_URL}">Get the downloader →</a>
  <p class="meta" style="margin-top:0.6rem">or
    <code class="inline">pipx install git+{REPO_URL}.git</code>
  </p>
</header>
<div class="controls"><input id="q" type="search" placeholder="Filter plugins…" aria-label="Filter plugins"></div>
{"".join(sections)}
<footer>
  Generated from <a href="{REPO_URL}/blob/main/plugins.json">plugins.json</a> ·
  <a href="{REPO_URL}">gr8monk3ys/VSTs</a> · MIT licensed catalog;
  each plugin keeps its own license.
</footer>
</main>
<script>{JS}</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the static catalog site")
    parser.add_argument("--manifest", default=None, help="Path to plugins.json")
    parser.add_argument("--out", default="_site", help="Output directory")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    manifest = Path(args.manifest) if args.manifest else repo_root / "plugins.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(build_html(data), encoding="utf-8")
    print(f"Wrote {out_dir / 'index.html'}")


if __name__ == "__main__":
    main()
