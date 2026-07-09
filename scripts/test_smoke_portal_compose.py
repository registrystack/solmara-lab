from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke-portal-compose.py"
SPEC = importlib.util.spec_from_file_location("smoke_portal_compose", SCRIPT)
smoke_portal_compose = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["smoke_portal_compose"] = smoke_portal_compose
SPEC.loader.exec_module(smoke_portal_compose)


class StubServer:
    def __init__(self, routes: dict[tuple[str, str], tuple[int, Any]]) -> None:
        self.routes = routes
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "StubServer":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self._handle("GET")

            def do_POST(self) -> None:
                self._handle("POST")

            def _handle(self, method: str) -> None:
                route = outer.routes.get((method, self.path))
                if route is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                status, payload = route
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, fmt: str, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        assert self.server is not None
        self.server.shutdown()
        self.server.server_close()
        assert self.thread is not None
        self.thread.join(timeout=5)

    @property
    def url(self) -> str:
        assert self.server is not None
        host, port = self.server.server_address
        return f"http://{host}:{port}"


@contextmanager
def patched_env(**values: str) -> Iterator[None]:
    old_values = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def portal_routes(evaluate_status: int, evaluate_body: dict[str, Any]) -> dict[tuple[str, str], tuple[int, Any]]:
    return {
        ("GET", "/"): (200, {"ok": True}),
        ("GET", "/auth/login"): (200, {"ok": True}),
        ("POST", "/api/evaluate"): (evaluate_status, evaluate_body),
    }


class PortalSmokeTests(unittest.TestCase):
    def test_auth_required_mode_accepts_unauthenticated_bff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            smoke_portal_compose.OUTPUT = Path(tmpdir) / "portal-compose.json"
            with StubServer(portal_routes(401, {"message": "not signed in"})) as server:
                with patched_env(
                    SOLMARA_PORTAL_URL=server.url,
                    SOLMARA_PORTAL_EXPECT_AUTH_REQUIRED="1",
                    SOLMARA_SMOKE_READY_TIMEOUT_SECONDS="2",
                ):
                    self.assertEqual(smoke_portal_compose.main(), 0)

    def test_default_mode_requires_verified_evaluate_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            smoke_portal_compose.OUTPUT = Path(tmpdir) / "portal-compose.json"
            with StubServer(portal_routes(401, {"message": "not signed in"})) as server:
                with patched_env(
                    SOLMARA_PORTAL_URL=server.url,
                    SOLMARA_PORTAL_EXPECT_AUTH_REQUIRED="0",
                    SOLMARA_SMOKE_READY_TIMEOUT_SECONDS="2",
                ):
                    self.assertEqual(smoke_portal_compose.main(), 1)


if __name__ == "__main__":
    unittest.main()
