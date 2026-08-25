"""Unit tests for compute_hash_for_url()."""

from __future__ import annotations

from free_vst_plugins import cli as dlp


def test_compute_hash_returns_sha256_of_stream(mock_server) -> None:
    body = b"the quick brown fox jumps over the lazy dog"
    url = mock_server.add("/file.bin", body)

    actual = dlp.compute_hash_for_url(url)

    assert actual == mock_server.sha256_of("/file.bin")
    # Sanity: matches the well-known SHA-256 of the test phrase.
    assert actual == "05c6e08f1d9fdafa03147fcb8f82f124c76d2f70e3d989dc8aadb5e7d7450bec"
