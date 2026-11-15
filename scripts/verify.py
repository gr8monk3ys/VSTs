#!/usr/bin/env python3
"""Run exactly what CI gates on. CI calls this; run it locally before pushing.

    uv run python scripts/verify.py          # everything
    uv run python scripts/verify.py lint     # the "Lint & Validate" job
    uv run python scripts/verify.py test     # one "Test Script" matrix leg

Non-gating CI steps (upstream drift check, URL reachability) are not here:
they report on third-party state, not on this repo.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable

PLATFORM_CHECK = """
import platform
system = platform.system().lower()
expected = {'darwin': 'macos', 'windows': 'windows', 'linux': 'linux'}
detected = expected.get(system, system)
print(f'Detected platform: {detected}')
assert detected in ['macos', 'windows', 'linux'], f'Unknown platform: {detected}'
"""

STEPS = {
    "lint": [
        ("Validate plugins.json (JSON + schema)", [PY, "scripts/validate_manifest.py"]),
        ("Ruff lint", [PY, "-m", "ruff", "check", "src/", "scripts/", "tests/"]),
        (
            "Ruff format",
            [PY, "-m", "ruff", "format", "--check", "src/", "scripts/", "tests/"],
        ),
        (
            "Syntax check",
            [
                PY,
                "-m",
                "py_compile",
                "src/free_vst_plugins/cli.py",
                "scripts/download-plugins.py",
            ],
        ),
    ],
    "test": [
        ("CLI --help", [PY, "scripts/download-plugins.py", "--help"]),
        ("CLI --list", [PY, "scripts/download-plugins.py", "--list"]),
        ("Platform detection", [PY, "-c", PLATFORM_CHECK]),
        ("Unit + integration tests", [PY, "-m", "pytest", "tests/", "-v"]),
    ],
}


def main(argv: list[str]) -> int:
    groups = argv or list(STEPS)
    unknown = [g for g in groups if g not in STEPS]
    if unknown:
        print(
            f"unknown step group(s): {', '.join(unknown)}; choose from {', '.join(STEPS)}"
        )
        return 2
    for group in groups:
        for title, cmd in STEPS[group]:
            print(f"==> [{group}] {title}", flush=True)
            result = subprocess.run(cmd, cwd=REPO)
            if result.returncode != 0:
                print(
                    f"FAILED: [{group}] {title} (exit {result.returncode})", flush=True
                )
                return result.returncode
    print(f"verify: {' + '.join(groups)} passed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
