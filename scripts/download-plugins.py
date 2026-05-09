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
import sys
import urllib.request
import urllib.error
import shutil
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

def download_file(url, filepath, name):
    """Download a file with progress indication."""
    if filepath.exists():
        print(f"  {C.YELLOW}⏭{C.NC}  {name} - already downloaded")
        return True

    print(f"  {C.CYAN}⬇{C.NC}  Downloading {name}...")

    try:
        # Create request with browser-like headers
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; VST-Downloader/1.0)'
        })

        with urllib.request.urlopen(req, timeout=60) as response:
            with open(filepath, 'wb') as f:
                shutil.copyfileobj(response, f)

        print(f"  {C.GREEN}✓{C.NC}  {name} - downloaded successfully")
        return True

    except urllib.error.HTTPError as e:
        print(f"  {C.RED}✗{C.NC}  {name} - HTTP error {e.code}")
        return False
    except urllib.error.URLError as e:
        print(f"  {C.RED}✗{C.NC}  {name} - connection error: {e.reason}")
        return False
    except Exception as e:
        print(f"  {C.RED}✗{C.NC}  {name} - error: {e}")
        return False

def compute_hash_for_url(url: str, chunk_size: int = 65536) -> str:
    """Stream the URL and return the lowercase hex SHA-256 of its body.

    Used by the --compute-hashes maintainer mode. Does NOT write a file
    or perform any verification — it is the trust-on-first-use primitive.
    """
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; VST-Downloader/1.0)'
    })
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as response:
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
    """Get the download URL for a plugin on the current platform."""
    # Check for platform-specific URL
    url_key = f"url_{plat}"
    if url_key in plugin:
        return plugin[url_key], plugin.get(f"filename_{plat}", plugin.get('filename'))

    # Check for 'urls' dict
    if 'urls' in plugin and plat in plugin['urls']:
        url_info = plugin['urls'][plat]
        if isinstance(url_info, dict):
            return url_info.get('url'), url_info.get('filename')
        return url_info, plugin.get('filename')

    # Fall back to default URL (usually macOS)
    url = plugin.get('url')
    filename = plugin.get('filename')

    # Skip if URL is clearly for a different platform
    if url:
        url_lower = url.lower()
        if plat == 'macos' and ('win' in url_lower or 'linux' in url_lower):
            return None, None
        if plat == 'windows' and ('macos' in url_lower or 'osx' in url_lower or 'linux' in url_lower):
            return None, None
        if plat == 'linux' and ('macos' in url_lower or 'osx' in url_lower or 'win' in url_lower):
            return None, None

    return url, filename

def download_category(plugins_data, category, download_dir, plat):
    """Download all plugins in a category."""
    if category not in plugins_data.get('plugins', {}):
        return 0

    plugins = plugins_data['plugins'][category]
    failed = 0

    print_section(category.title())

    for plugin in plugins:
        name = plugin.get('name', 'Unknown')
        url, filename = get_plugin_url(plugin, plat)

        if not url:
            print(f"  {C.YELLOW}⏭{C.NC}  {name} - not available for {plat}")
            continue

        if not filename:
            filename = url.split('/')[-1].split('?')[0]
            filename = urllib.request.unquote(filename)

        filepath = download_dir / filename

        if not download_file(url, filepath, name):
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
        print(f"     1. Extract archives to plugin directories:")
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
            url, _ = get_plugin_url(plugin, plat)

            if url:
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

    # Download each category
    for category in categories:
        failed += download_category(plugins_data, category, download_dir, plat)

    # Extract archives
    extract_archives(download_dir)

    # Print summary
    print_summary(download_dir, plat)

    if failed > 0:
        print(f"{C.YELLOW}⚠ {failed} download(s) failed. Check the output above.{C.NC}")
        sys.exit(1)

if __name__ == '__main__':
    main()
