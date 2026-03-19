"""Unit tests for compute_hash_for_url()."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load the script as a module (it has a hyphen in the name so we can't `import`).
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "download-plugins.py"
_spec = importlib.util.spec_from_file_location("dlp", _SCRIPT)
dlp = importlib.util.module_from_spec(_spec)
sys.modules["dlp"] = dlp
_spec.loader.exec_module(dlp)


def test_compute_hash_returns_sha256_of_stream(mock_server) -> None:
    body = b"the quick brown fox jumps over the lazy dog"
    url = mock_server.add("/file.bin", body)

    actual = dlp.compute_hash_for_url(url)

    assert actual == mock_server.sha256_of("/file.bin")
    # Sanity: matches the well-known SHA-256 of the test phrase.
    assert actual == "05c6e08f1d9fdafa03147fcb8f82f124c76d2f70e3d989dc8aadb5e7d7450bec"
