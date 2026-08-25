#!/usr/bin/env python3
"""
Free VST Plugins Downloader - Cross-Platform
Downloads high-quality free VST plugins for macOS, Windows, and Linux.
All plugins are legally free from their official sources.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


# ANSI colors (disabled on Windows unless in modern terminal)
class Colors:
    ENABLED = sys.stdout.isatty() and (
        platform.system() != "Windows" or os.environ.get("WT_SESSION")
    )

    RED = "\033[0;31m" if ENABLED else ""
    GREEN = "\033[0;32m" if ENABLED else ""
    YELLOW = "\033[1;33m" if ENABLED else ""
    BLUE = "\033[0;34m" if ENABLED else ""
    CYAN = "\033[0;36m" if ENABLED else ""
    NC = "\033[0m" if ENABLED else ""


C = Colors()


class ChecksumMismatch(Exception):
    """Raised when a downloaded file's SHA-256 does not match plugins.json."""

    def __init__(self, name: str, expected: str, actual: str) -> None:
        super().__init__(f"{name}: expected {expected}, got {actual}")
        self.name = name
        self.expected = expected
        self.actual = actual


def get_platform():
    """Detect current platform."""
    system = platform.system().lower()
    return {"darwin": "macos", "windows": "windows", "linux": "linux"}.get(
        system, system
    )


def get_default_download_dir():
    """Get default download directory based on platform."""
    return Path.home() / "Downloads" / "VST-Plugins"


def load_plugins(json_path):
    """Load plugins from JSON file."""
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/gr8monk3ys/free-vst-plugins/main/plugins.json"
)


def find_local_manifest() -> Path | None:
    """Find plugins.json in a repo checkout (walking up from this file), else CWD.

    Returns None when running as an installed package outside any checkout —
    the caller falls back to the canonical remote manifest.
    """
    here = Path(__file__).resolve()
    for parent in list(here.parents)[:4]:
        candidate = parent / "plugins.json"
        if candidate.exists():
            return candidate
    cwd_candidate = Path.cwd() / "plugins.json"
    if cwd_candidate.exists():
        return cwd_candidate
    return None


def fetch_remote_manifest(url: str = DEFAULT_MANIFEST_URL) -> dict:
    """Fetch the canonical plugins.json for installed (no-checkout) runs."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; VST-Downloader/1.0)"}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def print_header():
    """Print script header."""
    print()
    print(f"{C.CYAN}{'=' * 64}{C.NC}")
    print(f"{C.CYAN}  {C.GREEN}Free VST Plugins Downloader{C.NC}")
    print(f"{C.CYAN}  {C.NC}Cross-platform: macOS | Windows | Linux")
    print(f"{C.CYAN}{'=' * 64}{C.NC}")
    print()


def print_section(title):
    """Print section header."""
    print()
    print(f"{C.BLUE}{'─' * 64}{C.NC}")
    print(f"{C.BLUE}  {title}{C.NC}")
    print(f"{C.BLUE}{'─' * 64}{C.NC}")


def download_file(url, filepath, name, expected_sha256, hash_source):
    """Download `url` to `filepath`, verifying SHA-256 in a single I/O pass.

    On hash mismatch, removes the partial/cached file and raises
    ChecksumMismatch. On a cached-file hit (filepath already exists), the
    file is re-hashed before being trusted; if it doesn't match, the cached
    file is deleted and the download proceeds normally.
    """
    if filepath.exists():
        h_existing = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h_existing.update(chunk)
        if h_existing.hexdigest() == expected_sha256:
            print(f"  {C.YELLOW}⏭{C.NC}  {name} - already verified ({hash_source})")
            return True
        # Cached file is bad — delete and fall through to re-download.
        filepath.unlink()
        print(
            f"  {C.YELLOW}⚠{C.NC}  {name} - cached file failed verification, redownloading"
        )

    print(f"  {C.CYAN}⬇{C.NC}  Downloading {name}...")

    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; VST-Downloader/1.0)"}
    )

    h = hashlib.sha256()
    try:
        with (
            urllib.request.urlopen(req, timeout=60) as response,
            open(filepath, "wb") as f,
        ):
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
    except urllib.error.HTTPError as e:
        if filepath.exists():
            filepath.unlink()
        print(f"  {C.RED}✗{C.NC}  {name} - HTTP error {e.code}")
        return False
    except urllib.error.URLError as e:
        if filepath.exists():
            filepath.unlink()
        print(f"  {C.RED}✗{C.NC}  {name} - connection error: {e.reason}")
        return False

    actual = h.hexdigest()
    if actual != expected_sha256:
        filepath.unlink()
        print(f"  {C.RED}✗{C.NC}  {name} - HASH MISMATCH")
        print(f"      expected: {expected_sha256}")
        print(f"      actual:   {actual}")
        raise ChecksumMismatch(name, expected_sha256, actual)

    print(f"  {C.GREEN}✓{C.NC}  {name} - verified ({hash_source})")
    return True


def compute_hash_for_url(url: str, chunk_size: int = 65536) -> str:
    """Stream the URL and return the lowercase hex SHA-256 of its body.

    Used by the --compute-hashes maintainer mode. Does NOT write a file
    or perform any verification — it is the trust-on-first-use primitive.

    Refuses to hash text/html or application/json responses, since those
    typically indicate a download-gate page or API error rather than a
    real installer (the hash would be valid but verify the wrong content).
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; VST-Downloader/1.0)"}
    )
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as response:
        ct = (response.getheader("Content-Type") or "").lower()
        if ct.startswith(("text/html", "application/json")):
            raise ValueError(
                f"refusing to hash {url} — Content-Type is {ct!r}; "
                "this URL probably serves a download-gate page or API error, "
                "not a real installer. Move the entry to manual_download."
            )
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def recompute_hashes(plugins_data: dict, force: bool) -> dict:
    """Walk plugins_data, compute SHA-256 for every URL, return updated dict.

    By default, existing sha256 fields are preserved (so manually-set
    'publisher' hashes are not clobbered). With force=True, every URL is
    recomputed and tagged 'self'.
    """
    for category_plugins in plugins_data.get("plugins", {}).values():
        for plugin in category_plugins:
            urls = plugin.get("urls", {})
            for entry in urls.values():
                if not isinstance(entry, dict) or "url" not in entry:
                    continue
                if entry.get("sha256") and not force:
                    continue
                digest = compute_hash_for_url(entry["url"])
                entry["sha256"] = digest
                entry["hash_source"] = "self"
    return plugins_data


def detect_latest_for_github(
    repo: str, tag: str | None = None, api_base: str = "https://api.github.com"
) -> dict:
    """Fetch a release from the GitHub API.

    repo: 'owner/name'.
    tag: if None, queries /releases/latest. If set, queries /releases/tags/{tag}
         (used for plugins pinned to a rolling tag like Airwindows's DAWPlugin).
    api_base: defaults to the public GitHub API. Tests override with a mock-server URL.

    Returns {'tag': str, 'assets': [{'name': str, 'url': str, 'size': int}, ...]}.

    Reads GITHUB_TOKEN from the environment when set and adds it as a Bearer
    Authorization header (raises the rate limit from 60/hr to 5000/hr).
    HTTP errors propagate to the caller.
    """
    if tag:
        path = f"/repos/{repo}/releases/tags/{tag}"
    else:
        path = f"/repos/{repo}/releases/latest"

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; VST-Downloader/1.0)",
        "Accept": "application/vnd.github+json",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(api_base + path, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    return {
        "tag": data.get("tag_name", ""),
        "assets": [
            {
                "name": a.get("name", ""),
                "url": a.get("browser_download_url", ""),
                "size": a.get("size", 0),
            }
            for a in data.get("assets", [])
        ],
    }


UHE_PRODUCTS = {
    "TyrellN6": {
        "page_url": "https://u-he.com/products/tyrelln6/",
        "version_re": re.compile(
            r"TyrellN6\s+(?:Beta\s+)?(\d+)\.(\d+)\.(\d+)\s*\(revision\s+(\d+)\)"
        ),
        "asset_template": "{dl_base}/releases/TyrellN6_{vcode}_public_beta_{rev}_{platform}.{ext}",
        "platforms": {
            "macos": ("Mac", "zip"),
            "windows": ("Win", "zip"),
            "linux": ("Linux", "tar.xz"),
        },
    },
    "Zebralette": {
        "page_url": "https://u-he.com/products/zebralette/",
        "version_re": re.compile(
            r"Zebralette\s+(\d+)\.(\d+)\.(\d+)\s*\(revision\s+(\d+)\)"
        ),
        "asset_template": "{dl_base}/releases/Zebra_Legacy_{vcode}_{rev}_{platform}.{ext}",
        "platforms": {
            "macos": ("Mac", "zip"),
            "windows": ("Win", "zip"),
            "linux": ("Linux", "zip"),
        },
    },
}


def detect_latest_for_uhe(
    product: str, page_url: str | None = None, dl_base: str | None = None
) -> dict:
    """Fetch a u-he product page and return the latest release as
    {'tag': str, 'assets': [{'name', 'url', 'size': 0}, ...]}.

    The 'tag' is f'{major}.{minor}.{patch}-r{rev}', stable string-comparable.
    Asset 'size' is 0 — u-he doesn't expose sizes from a list endpoint.

    page_url and dl_base override the values from UHE_PRODUCTS for testing.

    Raises:
      ValueError if `product` is not in UHE_PRODUCTS.
      RuntimeError if the page doesn't contain a recognizable version string.
      urllib.error.HTTPError / URLError on network problems (propagated).
    """
    if product not in UHE_PRODUCTS:
        raise ValueError(f"unknown u-he product: {product!r}")

    cfg = UHE_PRODUCTS[product]
    url = page_url or cfg["page_url"]
    base = dl_base or "https://dl.u-he.com"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; VST-Downloader/1.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read().decode("utf-8", errors="replace")

    m = cfg["version_re"].search(body)
    if not m:
        raise RuntimeError(
            f"u-he page does not contain a recognizable version string for {product}"
        )
    major, minor, patch, rev = m.group(1), m.group(2), m.group(3), m.group(4)
    vcode = f"{major}{minor}{patch}"
    tag = f"{major}.{minor}.{patch}-r{rev}"

    assets = []
    for plat_name, ext in cfg["platforms"].values():
        asset_url = cfg["asset_template"].format(
            dl_base=base,
            vcode=vcode,
            rev=rev,
            platform=plat_name,
            ext=ext,
        )
        # Strip the dl_base prefix to derive the asset filename.
        name = asset_url.rsplit("/", 1)[-1]
        assets.append({"name": name, "url": asset_url, "size": 0})

    return {"tag": tag, "assets": assets}


def detect_drift_for_stable_url(entry: dict) -> dict:
    """Re-hash each platform URL in `entry` and report which platforms drifted.

    Used by the 'stable-url' update strategy. The vendor URL is assumed to be
    canonical (it never changes); the only signal that the upstream file has
    been swapped is its sha256 differing from what we stored.

    Returns:
      {
        'drift': bool,            # True if any platform's hash changed
        'platforms': {
          '<plat>': {
            'url': str,
            'old_sha256': str,
            'new_sha256': str,
            'changed': bool,
          },
          ...
        },
      }

    Raises:
      ValueError if `entry['urls']` is missing or empty, or if any URL serves
        text/html or application/json (the existing compute_hash_for_url guard
        — vendors sometimes replace a binary URL with a download-gate page,
        and silently re-hashing that HTML would be wrong).
      urllib.error.HTTPError / URLError on network failure.
    """
    urls = entry.get("urls") or {}
    platforms_with_url = {
        p: e for p, e in urls.items() if isinstance(e, dict) and e.get("url")
    }
    if not platforms_with_url:
        raise ValueError(
            f"stable-url entry {entry.get('name', '<unknown>')!r} has no platforms with URLs"
        )

    out = {"drift": False, "platforms": {}}
    for plat, urlentry in platforms_with_url.items():
        url = urlentry["url"]
        stored = urlentry.get("sha256")
        if not stored:
            raise ValueError(
                f"stable-url entry {entry.get('name', '<unknown>')!r} platform "
                f"{plat!r} has no stored sha256 to compare against"
            )
        new_hash = compute_hash_for_url(url)
        changed = new_hash != stored
        if changed:
            out["drift"] = True
        out["platforms"][plat] = {
            "url": url,
            "old_sha256": stored,
            "new_sha256": new_hash,
            "changed": changed,
        }
    return out


def find_matching_asset(
    current_filename: str,
    candidates: list[dict],
    current_url: str | None = None,
    old_tag: str | None = None,
    new_tag: str | None = None,
) -> dict | None:
    """Pick the candidate asset that should replace `current_filename`.

    Strategy A (exact substitution): if old_tag and new_tag are both set and differ
      and old_tag appears as a substring of current_filename, build the expected
      new name by substituting and look for an exact match in candidates.

    Strategy B (token-overlap fallback): split current and each candidate name on
      `-_.`, lowercase, count shared tokens. Highest score wins; ties broken by
      iteration order (the GitHub API returns assets in a deterministic order
      per release, so this is reproducible).

    If `current_url` is provided, its tokens are merged with the filename tokens —
    useful when the maintainer's filename field is a shortened form of the upstream
    asset name (e.g., `-macos.dmg` vs `-macos-universal.dmg`).

    Returns the matched candidate dict or None if no candidate scores at least 2
    shared tokens (prevents matching purely on file extension).
    """
    if old_tag and new_tag and old_tag != new_tag and old_tag in current_filename:
        expected = current_filename.replace(old_tag, new_tag)
        for cand in candidates:
            if cand["name"] == expected:
                return cand

    def tokens(name: str) -> set[str]:
        # Splits on URL/path separators too (`/`, `:`) so a current_url can
        # contribute its repo path components as discrete tokens.
        return {t for t in re.split(r"[-_./:]", name.lower()) if t}

    filename_toks = tokens(current_filename)
    url_toks = tokens(current_url) if current_url else set()

    best = None
    # Two-tier score: (filename-overlap, url-overlap). Prefers candidates that
    # match the current filename's tokens (which carry platform/extension info)
    # over candidates that only match URL path components.
    best_score = (1, 0)  # filename-overlap floor of 2 (must beat 1)
    for cand in candidates:
        cand_toks = tokens(cand["name"])
        score = (len(filename_toks & cand_toks), len(url_toks & cand_toks))
        if score > best_score:
            best = cand
            best_score = score

    return best


def _parse_update_strategy(strategy: str):
    """Parse known update_strategy values.

    Returns one of:
      ('github', repo: str, tag: str | None)
      ('u-he', product: str)
      ('stable-url',)
      None  if the value is missing or unrecognized.
    """
    if not strategy:
        return None
    if strategy.startswith("github:"):
        rest = strategy[len("github:") :]
        if not rest:
            return None
        if "@" in rest:
            repo, tag = rest.rsplit("@", 1)
            if not repo or not tag:
                return None
            return ("github", repo, tag)
        return ("github", rest, None)
    if strategy.startswith("u-he:"):
        product = strategy[len("u-he:") :]
        if not product:
            return None
        return ("u-he", product)
    if strategy == "stable-url":
        return ("stable-url",)
    return None


def check_updates(plugins_data: dict, api_base: str = "https://api.github.com") -> dict:
    """Walk the manifest, return a structured drift report.

    Returns:
      {
        'updates': [   # plugins where every platform matched and at least one filename differs
          {'name': str, 'category': str, 'old_version': str, 'new_version': str,
           'platforms': [{'plat': str, 'old_filename': str, 'new_asset': {...}}]},
          ...
        ],
        'no_updates': [{'name', 'category', 'version'}, ...],
        'manual': [{'name', 'category', 'version'}, ...],
        'failures': [{'name', 'category', 'reason'}, ...],
      }
    """
    report = {"updates": [], "no_updates": [], "manual": [], "failures": []}

    for category, plugins in plugins_data.get("plugins", {}).items():
        for plugin in plugins:
            name = plugin.get("name", "Unknown")
            current_version = plugin.get("version", "?")
            strategy = plugin.get("update_strategy")

            if not strategy:
                report["manual"].append(
                    {
                        "name": name,
                        "category": category,
                        "version": current_version,
                    }
                )
                continue

            parsed = _parse_update_strategy(strategy)
            if not parsed:
                report["failures"].append(
                    {
                        "name": name,
                        "category": category,
                        "reason": f"malformed update_strategy: {strategy}",
                    }
                )
                continue

            # stable-url is its own pipeline — no asset matching, just rehash + compare.
            if parsed[0] == "stable-url":
                try:
                    drift_result = detect_drift_for_stable_url(plugin)
                except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as e:
                    report["failures"].append(
                        {
                            "name": name,
                            "category": category,
                            "reason": f"detection failed: {e}",
                        }
                    )
                    continue
                if drift_result["drift"]:
                    platform_rows = [
                        {
                            "plat": plat,
                            "changed": info["changed"],
                            "old_sha256": info["old_sha256"],
                            "new_sha256": info["new_sha256"],
                        }
                        for plat, info in drift_result["platforms"].items()
                    ]
                    report["updates"].append(
                        {
                            "name": name,
                            "category": category,
                            "strategy": "stable-url",
                            "old_version": current_version,
                            "new_version": current_version,  # vendor didn't bump a label
                            "platforms": platform_rows,
                        }
                    )
                else:
                    report["no_updates"].append(
                        {
                            "name": name,
                            "category": category,
                            "version": current_version,
                        }
                    )
                continue

            try:
                if parsed[0] == "github":
                    _, repo, tag = parsed
                    release = detect_latest_for_github(repo, tag=tag, api_base=api_base)
                    old_tag = tag if tag else current_version
                elif parsed[0] == "u-he":
                    _, product = parsed
                    # Test-only env-var overrides; production uses UHE_PRODUCTS defaults.
                    # VST_DLP_UHE_PAGE_URL_<Product>: alternate product-page URL (e.g. mock server)
                    # VST_DLP_UHE_DL_BASE: alternate download base URL
                    page_url = os.environ.get(f"VST_DLP_UHE_PAGE_URL_{product}")
                    dl_base = os.environ.get("VST_DLP_UHE_DL_BASE")
                    release = detect_latest_for_uhe(
                        product, page_url=page_url, dl_base=dl_base
                    )
                    # u-he tags carry a revision (e.g. "3.0.1-r17000") that won't
                    # substring-match current_version (e.g. "3.0.0"); Strategy A
                    # skips and Strategy B does the matching.
                    old_tag = current_version
                    tag = None  # for the rolling-tag display logic later
                else:
                    raise RuntimeError(f"unknown strategy kind: {parsed[0]}")
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                ValueError,
                RuntimeError,
            ) as e:
                report["failures"].append(
                    {
                        "name": name,
                        "category": category,
                        "reason": f"detection failed: {e}",
                    }
                )
                continue

            new_tag = release["tag"]

            platform_updates = []
            any_drift = False
            any_failure = False
            for plat, entry in plugin.get("urls", {}).items():
                if not isinstance(entry, dict) or "filename" not in entry:
                    continue
                cur_filename = entry["filename"]
                matched = find_matching_asset(
                    cur_filename,
                    release["assets"],
                    current_url=entry.get("url"),
                    old_tag=old_tag,
                    new_tag=new_tag,
                )
                if matched is None:
                    any_failure = True
                    platform_updates.append(
                        {
                            "plat": plat,
                            "old_filename": cur_filename,
                            "new_asset": None,
                        }
                    )
                    continue
                if matched["name"] != cur_filename:
                    any_drift = True
                platform_updates.append(
                    {
                        "plat": plat,
                        "old_filename": cur_filename,
                        "new_asset": matched,
                    }
                )

            if any_failure:
                missing = [
                    p["plat"] for p in platform_updates if p["new_asset"] is None
                ]
                report["failures"].append(
                    {
                        "name": name,
                        "category": category,
                        "reason": f"no matching asset for: {', '.join(missing)}",
                    }
                )
            elif any_drift:
                # When the strategy pins a rolling tag (e.g. github:owner/repo@DAWPlugin),
                # the tag string never changes — display old_version on both sides so the
                # report shows "filename changed" rather than a misleading version diff.
                shown_new = current_version if (tag and new_tag == tag) else new_tag
                report["updates"].append(
                    {
                        "name": name,
                        "category": category,
                        "old_version": current_version,
                        "new_version": shown_new,
                        "platforms": platform_updates,
                    }
                )
            else:
                report["no_updates"].append(
                    {
                        "name": name,
                        "category": category,
                        "version": current_version,
                    }
                )

    return report


def print_check_updates_report(report: dict) -> None:
    """Pretty-print the drift report grouped by category."""
    by_cat: dict[str, list] = {}
    for kind in ("updates", "no_updates", "manual", "failures"):
        for item in report[kind]:
            by_cat.setdefault(item["category"], []).append((kind, item))

    total_with_strategy = (
        len(report["updates"]) + len(report["no_updates"]) + len(report["failures"])
    )
    total_manual = len(report["manual"])
    print(
        f"\nChecking {total_with_strategy + total_manual} plugins ({total_with_strategy} with update_strategy, {total_manual} manual)...\n"
    )

    for cat in sorted(by_cat):
        print(f"{cat.title()}")
        for kind, item in by_cat[cat]:
            name = item["name"]
            if kind == "updates":
                if item.get("strategy") == "stable-url":
                    print(
                        f"  {name:<30} {item['old_version']:<8} → {item['new_version']:<8} {C.YELLOW}⬆ CONTENT DRIFT{C.NC}"
                    )
                    for pu in item["platforms"]:
                        if pu.get("changed"):
                            short_old = pu["old_sha256"][:8]
                            short_new = pu["new_sha256"][:8]
                            print(
                                f"    {pu['plat']:8} sha256 {short_old} → {short_new}"
                            )
                        else:
                            print(f"    {pu['plat']:8} unchanged")
                else:
                    print(
                        f"  {name:<30} {item['old_version']:<8} → {item['new_version']:<8} {C.YELLOW}⬆ NEW VERSION{C.NC}"
                    )
                    for pu in item["platforms"]:
                        print(f"    {pu['plat']:8} {pu['new_asset']['name']}")
            elif kind == "no_updates":
                print(
                    f"  {name:<30} {item['version']:<8} → {item['version']:<8} no update"
                )
            elif kind == "manual":
                print(f"  {name:<30} {item['version']:<8} → ?       manual")
            elif kind == "failures":
                print(f"  {name:<30} {C.RED}DETECTION FAILED{C.NC} — {item['reason']}")
        print()

    n_up = len(report["updates"])
    n_fail = len(report["failures"])
    if n_up:
        print(f"{n_up} update(s) available. Run with --apply to update plugins.json.")
    if n_fail:
        print(
            f"{n_fail} detection failure(s). See lines marked DETECTION FAILED above."
        )
    if not n_up and not n_fail:
        print("Everything up to date.")


def apply_updates(plugins_data: dict, report: dict) -> None:
    """Mutate plugins_data in place.

    For github/u-he updates: rewrite urls[plat].url + filename, clear sha256 +
    hash_source (recompute_hashes will re-fill them), bump version.

    For stable-url updates: write the pre-computed new sha256 directly (no
    re-fetch needed — detect_drift_for_stable_url already paid that cost), set
    hash_source to 'self' (we just hashed it ourselves), leave url/filename/
    version untouched (they didn't change).
    """
    index = {}
    for cat, plugins in plugins_data.get("plugins", {}).items():
        for p in plugins:
            index[(cat, p.get("name"))] = p

    for upd in report["updates"]:
        plugin = index.get((upd["category"], upd["name"]))
        if plugin is None:
            continue

        if upd.get("strategy") == "stable-url":
            for pu in upd["platforms"]:
                if not pu.get("changed"):
                    continue
                entry = plugin["urls"][pu["plat"]]
                entry["sha256"] = pu["new_sha256"]
                entry["hash_source"] = "self"
            continue  # url/filename/version unchanged for stable-url

        # github/u-he path
        for pu in upd["platforms"]:
            asset = pu["new_asset"]
            if asset is None:
                continue
            entry = plugin["urls"][pu["plat"]]
            entry["url"] = asset["url"]
            entry["filename"] = asset["name"]
            entry.pop("sha256", None)
            entry.pop("hash_source", None)
        # Bump version unless the tag is rolling (same string before and after).
        if upd["old_version"] != upd["new_version"]:
            plugin["version"] = upd["new_version"]

    # Keep the manifest's own freshness stamp honest.
    if report["updates"] and isinstance(plugins_data.get("meta"), dict):
        plugins_data["meta"]["updated"] = datetime.date.today().isoformat()


def extract_archives(download_dir):
    """Extract zip files."""
    print_section("Extracting Archives")

    for zip_path in download_dir.glob("*.zip"):
        extract_dir = download_dir / zip_path.stem

        if extract_dir.exists():
            print(f"  {C.YELLOW}⏭{C.NC}  {zip_path.name} - already extracted")
            continue

        print(f"  {C.CYAN}📦{C.NC}  Extracting {zip_path.name}...")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            print(f"  {C.GREEN}✓{C.NC}  Extracted {zip_path.name}")
        except (zipfile.BadZipFile, OSError) as e:
            print(f"  {C.RED}✗{C.NC}  Failed to extract {zip_path.name}: {e}")


def get_plugin_url(plugin, plat):
    """Get the URL entry dict for the current platform.

    Returns a dict with keys 'url', 'filename', 'sha256', 'hash_source'
    or None if the plugin is unavailable for this platform.
    """
    urls = plugin.get("urls", {})
    entry = urls.get(plat)
    if isinstance(entry, dict) and entry.get("url"):
        return entry
    return None


def matches_only(name: str, only: list[str] | None) -> bool:
    """True when `name` matches any --only filter (case-insensitive substring).

    No filters means everything matches.
    """
    if not only:
        return True
    lowered = name.lower()
    return any(needle.lower() in lowered for needle in only)


def download_category(plugins_data, category, download_dir, plat, only=None):
    """Download all plugins in a category (optionally filtered by --only)."""
    if category not in plugins_data.get("plugins", {}):
        return 0

    plugins = [
        p
        for p in plugins_data["plugins"][category]
        if matches_only(p.get("name", "Unknown"), only)
    ]
    if not plugins:
        return 0
    failed = 0

    print_section(category.title())

    for plugin in plugins:
        name = plugin.get("name", "Unknown")
        entry = get_plugin_url(plugin, plat)

        if entry is None:
            print(f"  {C.YELLOW}⏭{C.NC}  {name} - not available for {plat}")
            continue

        url = entry["url"]
        filename = entry.get("filename") or urllib.request.unquote(
            url.split("/")[-1].split("?")[0]
        )
        filepath = download_dir / filename

        if not download_file(
            url, filepath, name, entry["sha256"], entry["hash_source"]
        ):
            failed += 1

    return failed


def verify_downloads(plugins_data, download_dir, plat, only=None) -> int:
    """Re-hash already-downloaded files against the manifest. No downloads.

    Prints one line per plugin (verified / MISMATCH / not downloaded) and
    returns the number of hash mismatches found.
    """
    print_section("Verifying Downloads")
    mismatched = 0
    checked = 0

    for category_plugins in plugins_data.get("plugins", {}).values():
        for plugin in category_plugins:
            name = plugin.get("name", "Unknown")
            if not matches_only(name, only):
                continue
            entry = get_plugin_url(plugin, plat)
            if entry is None:
                continue
            filename = entry.get("filename") or urllib.request.unquote(
                entry["url"].split("/")[-1].split("?")[0]
            )
            filepath = download_dir / filename
            if not filepath.exists():
                print(f"  {C.YELLOW}⏭{C.NC}  {name} - not downloaded")
                continue

            checked += 1
            h = hashlib.sha256()
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            if h.hexdigest() == entry["sha256"]:
                print(f"  {C.GREEN}✓{C.NC}  {name} - verified ({entry['hash_source']})")
            else:
                mismatched += 1
                print(f"  {C.RED}✗{C.NC}  {name} - HASH MISMATCH ({filepath.name})")

    print()
    print(f"  {checked} file(s) checked, {mismatched} mismatch(es)")
    return mismatched


def print_summary(download_dir, plat):
    """Print download summary."""
    print_section("Download Summary")

    files = list(download_dir.iterdir()) if download_dir.exists() else []
    total = len([f for f in files if f.is_file()])

    # Calculate size
    total_size = sum(f.stat().st_size for f in files if f.is_file())
    size_mb = total_size / (1024 * 1024)
    size_str = f"{size_mb:.1f} MB" if size_mb < 1024 else f"{size_mb / 1024:.2f} GB"

    print()
    print(f"  {C.GREEN}Downloads complete!{C.NC}")
    print()
    print(f"  📁 Location: {C.CYAN}{download_dir}{C.NC}")
    print(f"  📊 Files: {C.CYAN}{total}{C.NC}")
    print(f"  💾 Total size: {C.CYAN}{size_str}{C.NC}")
    print()

    # Platform-specific installation instructions
    print(f"  {C.YELLOW}To install:{C.NC}")

    if plat == "macos":
        print(f"     1. Open {C.CYAN}{download_dir}{C.NC}")
        print("     2. Double-click each .dmg or .pkg file")
        print("     3. Run the installer inside")
        print("     4. Rescan plugins in your DAW")
    elif plat == "windows":
        print(f"     1. Open {C.CYAN}{download_dir}{C.NC}")
        print("     2. Run each .exe or .msi installer as Administrator")
        print("     3. Follow installer prompts")
        print("     4. Rescan plugins in your DAW")
    else:  # Linux
        print("     1. Extract archives to plugin directories:")
        print(f"        VST3: {C.CYAN}~/.vst3{C.NC}")
        print(f"        VST:  {C.CYAN}~/.vst{C.NC} or {C.CYAN}/usr/lib/vst{C.NC}")
        print(f"        LV2:  {C.CYAN}~/.lv2{C.NC}")
        print("     2. Rescan plugins in your DAW")

    print()
    print(f"  {C.YELLOW}Manual downloads needed:{C.NC}")
    print(f"     • Vital           → {C.CYAN}https://vital.audio{C.NC}")
    print(f"     • Spitfire LABS   → {C.CYAN}https://labs.spitfireaudio.com{C.NC}")
    print(f"     • Analog Obsession → {C.CYAN}https://analogobsession.com{C.NC}")
    print()


def list_plugins(plugins_data, plat):
    """List all available plugins."""
    print_header()

    for category in ["synths", "effects", "instruments", "bundles"]:
        if category not in plugins_data.get("plugins", {}):
            continue

        print_section(category.title())

        for plugin in plugins_data["plugins"][category]:
            name = plugin.get("name", "Unknown")
            entry = get_plugin_url(plugin, plat)

            if entry is not None:
                print(f"  • {name}")
            else:
                print(f"  • {name} {C.YELLOW}(not available for {plat}){C.NC}")

    print_section("Manual Download Required")
    for plugin in plugins_data.get("manual_download", []):
        print(f"  • {plugin.get('name')} - {plugin.get('website')}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Download free VST plugins for music production",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Download all plugins
  %(prog)s --synths           # Download synths only
  %(prog)s --dir ~/Music/VST  # Custom download location
  %(prog)s --list             # List available plugins
""",
    )

    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        default=True,
        help="Download all plugins (default)",
    )
    parser.add_argument(
        "-s", "--synths", action="store_true", help="Download synths only"
    )
    parser.add_argument(
        "-e", "--effects", action="store_true", help="Download effects only"
    )
    parser.add_argument(
        "-i", "--instruments", action="store_true", help="Download instruments only"
    )
    parser.add_argument(
        "-b", "--bundles", action="store_true", help="Download bundles only"
    )
    parser.add_argument(
        "-l", "--list", action="store_true", help="List available plugins"
    )
    parser.add_argument("-d", "--dir", type=str, help="Download directory")
    parser.add_argument(
        "--platform",
        choices=["macos", "windows", "linux"],
        help="Override detected platform",
    )
    parser.add_argument(
        "--compute-hashes",
        action="store_true",
        help="Maintainer mode: compute SHA-256 for every URL and emit updated plugins.json",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="With --compute-hashes: rewrite plugins.json instead of stdout",
    )
    parser.add_argument(
        "--force-recompute",
        action="store_true",
        help="With --compute-hashes: overwrite existing sha256 fields (otherwise preserved)",
    )
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help="Detect upstream version drift on entries with update_strategy set",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="With --check-updates: write URL/filename/version/sha256 updates back to plugins.json",
    )
    parser.add_argument(
        "--plugins-json",
        type=str,
        help="Path to plugins.json (defaults to the repo checkout, then the canonical remote manifest)",
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="NAME",
        help="Only process plugins whose name contains NAME (case-insensitive; repeatable)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Re-hash already-downloaded files against the manifest; no downloads",
    )

    args = parser.parse_args()

    # Determine platform
    plat = args.platform or get_platform()

    # Determine download directory
    download_dir = Path(args.dir) if args.dir else get_default_download_dir()

    # Load plugins data: explicit flag > repo checkout > canonical remote manifest.
    plugins_json = (
        Path(args.plugins_json) if args.plugins_json else find_local_manifest()
    )

    if plugins_json is None:
        if args.compute_hashes or args.check_updates:
            print(
                f"{C.RED}Error: maintainer modes need a local plugins.json "
                f"(pass --plugins-json or run from a checkout){C.NC}"
            )
            sys.exit(1)
        print(f"  Using remote manifest: {C.CYAN}{DEFAULT_MANIFEST_URL}{C.NC}")
        try:
            plugins_data = fetch_remote_manifest()
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"{C.RED}Error: could not fetch remote manifest: {e}{C.NC}")
            sys.exit(1)
    elif not plugins_json.exists():
        print(f"{C.RED}Error: plugins.json not found at {plugins_json}{C.NC}")
        sys.exit(1)
    else:
        plugins_data = load_plugins(plugins_json)

    # List mode
    if args.list:
        list_plugins(plugins_data, plat)
        return

    # Compute hashes mode
    if args.compute_hashes:
        updated = recompute_hashes(plugins_data, args.force_recompute)
        rendered = json.dumps(updated, indent=2, ensure_ascii=False) + "\n"
        if args.in_place:
            plugins_json.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return

    if args.check_updates:
        api_base = os.environ.get("VST_DLP_GITHUB_API_BASE", "https://api.github.com")
        report = check_updates(plugins_data, api_base=api_base)
        print_check_updates_report(report)
        if args.apply:
            apply_updates(plugins_data, report)
            # Recompute hashes for entries whose sha256 was cleared.
            recompute_hashes(plugins_data, force=False)
            rendered = json.dumps(plugins_data, indent=2, ensure_ascii=False) + "\n"
            plugins_json.write_text(rendered, encoding="utf-8")
            print(
                f"\n{C.GREEN}Applied{C.NC} {len(report['updates'])} update(s). plugins.json updated."
            )
            sys.exit(0)
        n_up = len(report["updates"])
        n_fail = len(report["failures"])
        sys.exit(1 if (n_up or n_fail) else 0)

    # Verify mode: re-hash what's already on disk, download nothing.
    if args.verify:
        print_header()
        print(f"  Platform: {C.CYAN}{plat}{C.NC}")
        print(f"  Download directory: {C.CYAN}{download_dir}{C.NC}")
        mismatched = verify_downloads(plugins_data, download_dir, plat, only=args.only)
        sys.exit(1 if mismatched else 0)

    # Determine which categories to download
    download_all = not (args.synths or args.effects or args.instruments or args.bundles)
    categories = []

    if download_all or args.synths:
        categories.append("synths")
    if download_all or args.effects:
        categories.append("effects")
    if download_all or args.instruments:
        categories.append("instruments")
    if download_all or args.bundles:
        categories.append("bundles")

    print_header()
    print(f"  Platform: {C.CYAN}{plat}{C.NC}")
    print(f"  Download directory: {C.CYAN}{download_dir}{C.NC}")

    # Create download directory
    download_dir.mkdir(parents=True, exist_ok=True)

    failed = 0
    try:
        for category in categories:
            failed += download_category(
                plugins_data, category, download_dir, plat, only=args.only
            )
    except ChecksumMismatch as e:
        print(f"\n{C.RED}HASH MISMATCH detected for {e.name}.{C.NC}")
        print(f"{C.RED}Aborting. The bad file has been deleted.{C.NC}")
        sys.exit(1)

    # Extract archives
    extract_archives(download_dir)

    # Print summary
    print_summary(download_dir, plat)

    if failed > 0:
        print(f"{C.YELLOW}⚠ {failed} download(s) failed. Check the output above.{C.NC}")
        sys.exit(1)


if __name__ == "__main__":
    main()
