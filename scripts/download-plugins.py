#!/usr/bin/env python3
"""
Free VST Plugins Downloader - Cross-Platform
Downloads high-quality free VST plugins for macOS, Windows, and Linux.
All plugins are legally free from their official sources.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

# ANSI colors (disabled on Windows unless in modern terminal)
class Colors:
    ENABLED = sys.stdout.isatty() and (platform.system() != 'Windows' or os.environ.get('WT_SESSION'))

    RED = '\033[0;31m' if ENABLED else ''
    GREEN = '\033[0;32m' if ENABLED else ''
    YELLOW = '\033[1;33m' if ENABLED else ''
    BLUE = '\033[0;34m' if ENABLED else ''
    CYAN = '\033[0;36m' if ENABLED else ''
    NC = '\033[0m' if ENABLED else ''

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
    if system == 'darwin':
        return 'macos'
    elif system == 'windows':
        return 'windows'
    elif system == 'linux':
        return 'linux'
    return system

def get_default_download_dir():
    """Get default download directory based on platform."""
    home = Path.home()
    plat = get_platform()

    if plat == 'macos':
        return home / 'Downloads' / 'VST-Plugins'
    elif plat == 'windows':
        return home / 'Downloads' / 'VST-Plugins'
    else:  # Linux
        return home / 'Downloads' / 'VST-Plugins'

def load_plugins(json_path):
    """Load plugins from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def print_header():
    """Print script header."""
    print()
    print(f"{C.CYAN}{'='*64}{C.NC}")
    print(f"{C.CYAN}  {C.GREEN}Free VST Plugins Downloader{C.NC}")
    print(f"{C.CYAN}  {C.NC}Cross-platform: macOS | Windows | Linux")
    print(f"{C.CYAN}{'='*64}{C.NC}")
    print()

def print_section(title):
    """Print section header."""
    print()
    print(f"{C.BLUE}{'─'*64}{C.NC}")
    print(f"{C.BLUE}  {title}{C.NC}")
    print(f"{C.BLUE}{'─'*64}{C.NC}")

def download_file(url, filepath, name, expected_sha256, hash_source):
    """Download `url` to `filepath`, verifying SHA-256 in a single I/O pass.

    On hash mismatch, removes the partial/cached file and raises
    ChecksumMismatch. On a cached-file hit (filepath already exists), the
    file is re-hashed before being trusted; if it doesn't match, the cached
    file is deleted and the download proceeds normally.
    """
    if filepath.exists():
        h_existing = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h_existing.update(chunk)
        if h_existing.hexdigest() == expected_sha256:
            print(f"  {C.YELLOW}⏭{C.NC}  {name} - already verified ({hash_source})")
            return True
        # Cached file is bad — delete and fall through to re-download.
        filepath.unlink()
        print(f"  {C.YELLOW}⚠{C.NC}  {name} - cached file failed verification, redownloading")

    print(f"  {C.CYAN}⬇{C.NC}  Downloading {name}...")

    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; VST-Downloader/1.0)'
    })

    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(req, timeout=60) as response, open(filepath, 'wb') as f:
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
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; VST-Downloader/1.0)'
    })
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as response:
        ct = (response.getheader('Content-Type') or '').lower()
        if ct.startswith('text/html') or ct.startswith('application/json'):
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
    for category_plugins in plugins_data.get('plugins', {}).values():
        for plugin in category_plugins:
            urls = plugin.get('urls', {})
            for plat, entry in urls.items():
                if not isinstance(entry, dict) or 'url' not in entry:
                    continue
                if entry.get('sha256') and not force:
                    continue
                digest = compute_hash_for_url(entry['url'])
                entry['sha256'] = digest
                entry['hash_source'] = 'self'
    return plugins_data

def detect_latest_for_github(repo: str, tag: str | None = None,
                             api_base: str = "https://api.github.com") -> dict:
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
        'User-Agent': 'Mozilla/5.0 (compatible; VST-Downloader/1.0)',
        'Accept': 'application/vnd.github+json',
    }
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {token}'

    req = urllib.request.Request(api_base + path, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode('utf-8'))

    return {
        'tag': data.get('tag_name', ''),
        'assets': [
            {
                'name': a.get('name', ''),
                'url': a.get('browser_download_url', ''),
                'size': a.get('size', 0),
            }
            for a in data.get('assets', [])
        ],
    }

def find_matching_asset(current_filename: str, candidates: list[dict],
                        old_tag: str | None = None,
                        new_tag: str | None = None,
                        target_size: int | None = None) -> dict | None:
    """Pick the candidate asset that should replace `current_filename`.

    Strategy A (exact substitution): if old_tag and new_tag are both set and differ
      and old_tag appears as a substring of current_filename, build the expected
      new name by substituting and look for an exact match in candidates.

    Strategy B (token-overlap fallback): split current and each candidate name on
      `-_.`, lowercase, count shared tokens. Highest score wins; ties broken by
      smallest absolute size delta from target_size if provided; further ties by
      iteration order.

    Returns the matched candidate dict or None if no candidate scores at least 2
    shared tokens (prevents matching purely on file extension).
    """
    if old_tag and new_tag and old_tag != new_tag and old_tag in current_filename:
        expected = current_filename.replace(old_tag, new_tag)
        for cand in candidates:
            if cand['name'] == expected:
                return cand

    def tokens(name: str) -> set[str]:
        return {t for t in re.split(r'[-_.]', name.lower()) if t}

    current_toks = tokens(current_filename)
    best = None
    best_score = 1
    best_size_delta = float('inf')
    for cand in candidates:
        score = len(current_toks & tokens(cand['name']))
        if score < best_score:
            continue
        if target_size is not None:
            size_delta = abs(cand.get('size', 0) - target_size)
        else:
            size_delta = 0
        if score > best_score or (score == best_score and size_delta < best_size_delta):
            best = cand
            best_score = score
            best_size_delta = size_delta

    return best

def extract_archives(download_dir):
    """Extract zip files."""
    print_section("Extracting Archives")

    for zip_path in download_dir.glob('*.zip'):
        extract_dir = download_dir / zip_path.stem

        if extract_dir.exists():
            print(f"  {C.YELLOW}⏭{C.NC}  {zip_path.name} - already extracted")
            continue

        print(f"  {C.CYAN}📦{C.NC}  Extracting {zip_path.name}...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)
            print(f"  {C.GREEN}✓{C.NC}  Extracted {zip_path.name}")
        except Exception as e:
            print(f"  {C.RED}✗{C.NC}  Failed to extract {zip_path.name}: {e}")

def get_plugin_url(plugin, plat):
    """Get the URL entry dict for the current platform.

    Returns a dict with keys 'url', 'filename', 'sha256', 'hash_source'
    or None if the plugin is unavailable for this platform.
    """
    urls = plugin.get('urls', {})
    entry = urls.get(plat)
    if isinstance(entry, dict) and entry.get('url'):
        return entry
    return None

def download_category(plugins_data, category, download_dir, plat):
    """Download all plugins in a category."""
    if category not in plugins_data.get('plugins', {}):
        return 0

    plugins = plugins_data['plugins'][category]
    failed = 0

    print_section(category.title())

    for plugin in plugins:
        name = plugin.get('name', 'Unknown')
        entry = get_plugin_url(plugin, plat)

        if entry is None:
            print(f"  {C.YELLOW}⏭{C.NC}  {name} - not available for {plat}")
            continue

        url = entry['url']
        filename = entry.get('filename') or urllib.request.unquote(url.split('/')[-1].split('?')[0])
        filepath = download_dir / filename

        if not download_file(url, filepath, name, entry['sha256'], entry['hash_source']):
            failed += 1

    return failed

def print_summary(download_dir, plat):
    """Print download summary."""
    print_section("Download Summary")

    files = list(download_dir.iterdir()) if download_dir.exists() else []
    total = len([f for f in files if f.is_file()])

    # Calculate size
    total_size = sum(f.stat().st_size for f in files if f.is_file())
    size_mb = total_size / (1024 * 1024)
    size_str = f"{size_mb:.1f} MB" if size_mb < 1024 else f"{size_mb/1024:.2f} GB"

    print()
    print(f"  {C.GREEN}Downloads complete!{C.NC}")
    print()
    print(f"  📁 Location: {C.CYAN}{download_dir}{C.NC}")
    print(f"  📊 Files: {C.CYAN}{total}{C.NC}")
    print(f"  💾 Total size: {C.CYAN}{size_str}{C.NC}")
    print()

    # Platform-specific installation instructions
    print(f"  {C.YELLOW}To install:{C.NC}")

    if plat == 'macos':
        print(f"     1. Open {C.CYAN}{download_dir}{C.NC}")
        print("     2. Double-click each .dmg or .pkg file")
        print("     3. Run the installer inside")
        print("     4. Rescan plugins in your DAW")
    elif plat == 'windows':
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

    for category in ['synths', 'effects', 'instruments', 'bundles']:
        if category not in plugins_data.get('plugins', {}):
            continue

        print_section(category.title())

        for plugin in plugins_data['plugins'][category]:
            name = plugin.get('name', 'Unknown')
            entry = get_plugin_url(plugin, plat)

            if entry is not None:
                print(f"  • {name}")
            else:
                print(f"  • {name} {C.YELLOW}(not available for {plat}){C.NC}")

    print_section("Manual Download Required")
    for plugin in plugins_data.get('manual_download', []):
        print(f"  • {plugin.get('name')} - {plugin.get('website')}")

    print()

def main():
    parser = argparse.ArgumentParser(
        description='Download free VST plugins for music production',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                    # Download all plugins
  %(prog)s --synths           # Download synths only
  %(prog)s --dir ~/Music/VST  # Custom download location
  %(prog)s --list             # List available plugins
'''
    )

    parser.add_argument('-a', '--all', action='store_true', default=True,
                        help='Download all plugins (default)')
    parser.add_argument('-s', '--synths', action='store_true',
                        help='Download synths only')
    parser.add_argument('-e', '--effects', action='store_true',
                        help='Download effects only')
    parser.add_argument('-i', '--instruments', action='store_true',
                        help='Download instruments only')
    parser.add_argument('-b', '--bundles', action='store_true',
                        help='Download bundles only')
    parser.add_argument('-l', '--list', action='store_true',
                        help='List available plugins')
    parser.add_argument('-d', '--dir', type=str,
                        help='Download directory')
    parser.add_argument('--platform', choices=['macos', 'windows', 'linux'],
                        help='Override detected platform')
    parser.add_argument('--compute-hashes', action='store_true',
                        help='Maintainer mode: compute SHA-256 for every URL and emit updated plugins.json')
    parser.add_argument('--in-place', action='store_true',
                        help='With --compute-hashes: rewrite plugins.json instead of stdout')
    parser.add_argument('--force-recompute', action='store_true',
                        help='With --compute-hashes: overwrite existing sha256 fields (otherwise preserved)')
    parser.add_argument('--plugins-json', type=str,
                        help='Path to plugins.json (defaults to ../plugins.json relative to script)')

    args = parser.parse_args()

    # Determine platform
    plat = args.platform or get_platform()

    # Determine download directory
    download_dir = Path(args.dir) if args.dir else get_default_download_dir()

    # Load plugins data
    script_dir = Path(__file__).parent
    plugins_json = Path(args.plugins_json) if args.plugins_json else script_dir.parent / 'plugins.json'

    if not plugins_json.exists():
        print(f"{C.RED}Error: plugins.json not found at {plugins_json}{C.NC}")
        sys.exit(1)

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
            plugins_json.write_text(rendered, encoding='utf-8')
        else:
            sys.stdout.write(rendered)
        return

    # Determine which categories to download
    download_all = not (args.synths or args.effects or args.instruments or args.bundles)
    categories = []

    if download_all or args.synths:
        categories.append('synths')
    if download_all or args.effects:
        categories.append('effects')
    if download_all or args.instruments:
        categories.append('instruments')
    if download_all or args.bundles:
        categories.append('bundles')

    print_header()
    print(f"  Platform: {C.CYAN}{plat}{C.NC}")
    print(f"  Download directory: {C.CYAN}{download_dir}{C.NC}")

    # Create download directory
    download_dir.mkdir(parents=True, exist_ok=True)

    failed = 0
    try:
        for category in categories:
            failed += download_category(plugins_data, category, download_dir, plat)
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

if __name__ == '__main__':
    main()
