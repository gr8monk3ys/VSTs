#!/usr/bin/env python3
"""Check that every download URL in plugins.json is still reachable.

HEAD-requests each pinned URL. 403/405 responses count as reachable (some
vendors reject HEAD but serve GET). Used by the scheduled CI job; run
locally with:  python scripts/validate_urls.py

Exit status is 1 when any URL is dead so a local run is loud. In CI the
step is `continue-on-error` because this checks third-party uptime, not
this repo's code: rolling upstream tags (e.g. baconpaul/airwin2rack
`DAWPlugin`) replace their assets on every build, and a vendor outage
should not block unrelated merges. Failures are surfaced as workflow
annotations and in the job summary instead; `update-manifest.yml` is the
job that actually re-pins drifted URLs.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HEAD_OK_ERRORS = (403, 405)  # servers that reject HEAD but serve GET


def check_url(name: str, platform: str, url: str) -> str | None:
    """Return an error string if the URL looks dead, else None."""
    req = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "Mozilla/5.0 (compatible; CI-Check/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"✓ {name} ({platform}): {resp.status}")
            return None
    except urllib.error.HTTPError as e:
        if e.code in HEAD_OK_ERRORS:
            print(f"~ {name} ({platform}): {e.code} (may still work)")
            return None
        print(f"✗ {name} ({platform}): HTTP {e.code}")
        return f"{name} ({platform}): HTTP {e.code}"
    except urllib.error.URLError as e:
        print(f"✗ {name} ({platform}): {e.reason}")
        return f"{name} ({platform}): {e.reason}"


def main() -> int:
    data = json.loads((REPO / "plugins.json").read_text(encoding="utf-8"))

    checked = 0
    failures: list[str] = []
    for category in data.get("plugins", {}).values():
        for plugin in category:
            name = plugin.get("name", "Unknown")
            for platform, entry in plugin.get("urls", {}).items():
                url = entry.get("url") if isinstance(entry, dict) else entry
                if not url:
                    continue
                checked += 1
                error = check_url(name, platform, url)
                if error:
                    failures.append(error)

    print(f"\n{checked} URLs checked, {len(failures)} failed")
    if failures:
        print("\nFailed URLs:")
        for failure in failures:
            print(f"  - {failure}")
        report_to_actions(checked, failures)
        return 1
    return 0


def report_to_actions(checked: int, failures: list[str]) -> None:
    """Surface failures in the GitHub Actions UI (no-op outside Actions)."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    for failure in failures:
        print(f"::warning title=Dead plugin URL::{failure}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    with open(summary, "a", encoding="utf-8") as fh:
        fh.write(f"## Plugin URL check: {len(failures)} of {checked} dead\n\n")
        fh.writelines(f"- {failure}\n" for failure in failures)
        fh.write(
            "\nRe-pin via `python scripts/download-plugins.py --check-updates --apply`"
            " (or wait for the Monday `update-manifest` PR).\n"
        )


if __name__ == "__main__":
    sys.exit(main())
