#!/usr/bin/env python3
"""Compatibility shim — the downloader now lives in src/free_vst_plugins/cli.py.

Kept so `python scripts/download-plugins.py` and the .sh/.ps1 wrappers keep
working from a plain checkout without installation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from free_vst_plugins.cli import main

if __name__ == "__main__":
    main()
