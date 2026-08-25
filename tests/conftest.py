"""Shared fixtures for the test suite."""

from __future__ import annotations

import hashlib
import http.server
import socketserver
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class MockServer:
    """A running mock HTTP server. Use `add(path, body)` to register responses."""

    host: str
    port: int
    _routes: dict[str, bytes]

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def url_for(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def add(self, path: str, body: bytes) -> str:
        """Register a response body for the given path. Returns the full URL."""
        if not path.startswith("/"):
            path = "/" + path
        self._routes[path] = body
        return self.url_for(path)

    def sha256_of(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return hashlib.sha256(self._routes[path]).hexdigest()


@pytest.fixture
def mock_server() -> Iterator[MockServer]:
    routes: dict[str, bytes] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = routes.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            pass  # silence stderr access logs during tests

    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    host, port = httpd.server_address
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield MockServer(host=host, port=port, _routes=routes)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
