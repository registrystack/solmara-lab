from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke-esignet.py"
SPEC = importlib.util.spec_from_file_location("smoke_esignet", SCRIPT)
smoke_esignet = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["smoke_esignet"] = smoke_esignet
SPEC.loader.exec_module(smoke_esignet)
LEGACY_SUBJECT = "NID" + "-1002"


class StubServer:
    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.seen_headers: dict[str, str] = {}
        self.seen_body: dict[str, Any] | None = None

    def __enter__(self) -> "StubServer":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self._handle("GET")

            def do_POST(self) -> None:
                length = int(self.headers.get("content-length", "0"))
                outer.seen_body = json.loads(self.rfile.read(length).decode("utf-8"))
                outer.seen_headers = {key.lower(): value for key, value in self.headers.items()}
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


class SmokeEsignetTests(unittest.TestCase):
    def test_load_env_file_handles_quoted_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("TOKEN='secret value'\nEMPTY=\n# comment\n", encoding="utf-8")
            self.assertEqual(smoke_esignet.load_env_file(path), {"TOKEN": "secret value", "EMPTY": ""})

    def test_attribute_release_posts_release_scope_request_without_printing_token(self) -> None:
        route = f"/v1/attribute-releases/{smoke_esignet.PROFILE_ID}/versions/{smoke_esignet.PROFILE_VERSION}/resolve"
        with StubServer(
            {
                ("POST", route): (
                    200,
                    {
                        "profile_id": smoke_esignet.PROFILE_ID,
                        "profile_version": smoke_esignet.PROFILE_VERSION,
                        "claims": {"individual_id": "2300018263", "name": "Elena Dela Cruz"},
                    },
                )
            }
        ) as server:
            targets = smoke_esignet.SmokeTargets(server.url, server.url, server.url)
            smoke_esignet.check_attribute_release(targets, "token-value", LEGACY_SUBJECT, "2300018263", timeout=2)
            self.assertEqual(server.seen_headers["data-purpose"], smoke_esignet.PURPOSE)
            self.assertEqual(server.seen_headers["authorization"], "Bearer token-value")
            self.assertEqual(server.seen_body["subject"], {"id_type": "national_id", "value": LEGACY_SUBJECT})

    def test_attribute_release_rejects_wrong_subject(self) -> None:
        route = f"/v1/attribute-releases/{smoke_esignet.PROFILE_ID}/versions/{smoke_esignet.PROFILE_VERSION}/resolve"
        with StubServer({("POST", route): (200, {"claims": {"individual_id": "2300010248"}})}) as server:
            targets = smoke_esignet.SmokeTargets(server.url, server.url, server.url)
            with self.assertRaises(smoke_esignet.SmokeFailure):
                smoke_esignet.check_attribute_release(targets, "token-value", LEGACY_SUBJECT, "2300018263", timeout=2)

    def test_discovery_requires_root_and_mosip_paths_to_share_issuer(self) -> None:
        issuer_doc = {"issuer": "https://esignet.solmara.registrystack.org"}
        routes = {
            ("GET", "/v1/esignet/oidc/.well-known/openid-configuration"): (200, issuer_doc),
            ("GET", "/.well-known/openid-configuration"): (200, issuer_doc),
            ("GET", "/.well-known/oauth-authorization-server"): (200, issuer_doc),
        }
        with StubServer(routes) as server:
            targets = smoke_esignet.SmokeTargets(server.url, server.url, server.url)
            smoke_esignet.check_esignet_discovery(targets, timeout=2)


if __name__ == "__main__":
    unittest.main()
