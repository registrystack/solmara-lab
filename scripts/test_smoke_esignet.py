from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import threading
import unittest
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke-esignet.py"
SPEC = importlib.util.spec_from_file_location("smoke_esignet", SCRIPT)
smoke_esignet = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["smoke_esignet"] = smoke_esignet
SPEC.loader.exec_module(smoke_esignet)


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
                outer.seen_headers = {
                    key.lower(): value for key, value in self.headers.items()
                }
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
    def test_local_and_hosted_profiles_select_native_breg_provider(self) -> None:
        for filename in ("compose.esignet.yaml", "compose.coolify.esignet.yaml", "compose.esignet-fixture.yaml"):
            compose = yaml.safe_load((ROOT / filename).read_text())
            environment = compose["services"]["esignet"]["environment"]
            self.assertEqual(environment["MOSIP_ESIGNET_AUTHN_PROVIDER"], "breg")
            self.assertEqual(environment["MOSIP_ESIGNET_AUTH_FLOW_ID"], "flow-breg-otp")
            self.assertIn("REGISTRY_ESIGNET_CONFIG_FILE", environment)
            self.assertNotIn("REGISTRY_MINT_PRIVATE_JWK", environment)
            self.assertNotIn("plugin_name_env", environment)
            self.assertNotIn("SPRING_APPLICATION_JSON", environment)

    def test_load_env_file_handles_quoted_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "TOKEN='secret value'\nEMPTY=\n# comment\n", encoding="utf-8"
            )
            self.assertEqual(
                smoke_esignet.load_env_file(path),
                {"TOKEN": "secret value", "EMPTY": ""},
            )

    def discovery_document(self, url: str) -> dict[str, Any]:
        return {
            "issuer": url,
            "authorization_endpoint": f"{url}/oauth2/authorize",
            "token_endpoint": f"{url}/oauth2/token",
            "userinfo_endpoint": f"{url}/oauth2/userinfo",
            "jwks_uri": f"{url}/oauth2/jwks",
            "token_endpoint_auth_methods_supported": ["private_key_jwt"],
        }

    def test_native_discovery_requires_public_endpoints_and_client_authentication(self) -> None:
        with StubServer({}) as server:
            document = self.discovery_document(server.url)
            server.routes.update({
                ("GET", "/.well-known/openid-configuration"): (200, document),
                ("GET", "/.well-known/oauth-authorization-server"): (200, document),
            })
            targets = smoke_esignet.SmokeTargets(server.url, server.url)
            smoke_esignet.check_esignet_discovery(targets, timeout=2)
            for key in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri", "userinfo_endpoint"):
                with self.subTest(key=key):
                    saved = document[key]
                    document[key] = "http://private-service.invalid/endpoint"
                    with self.assertRaises(smoke_esignet.SmokeFailure):
                        smoke_esignet.check_esignet_discovery(targets, timeout=2)
                    document[key] = saved
            document["token_endpoint_auth_methods_supported"] = ["client_secret_post"]
            with self.assertRaises(smoke_esignet.SmokeFailure):
                smoke_esignet.check_esignet_discovery(targets, timeout=2)

    def test_dependency_response_body_is_not_a_diagnostic(self) -> None:
        with StubServer({("GET", "/broken"): (500, {"secret": "sensitive-canary"})}) as server:
            with self.assertRaises(smoke_esignet.SmokeFailure) as caught:
                smoke_esignet.request_json("GET", f"{server.url}/broken")
            self.assertEqual(str(caught.exception), "discovery HTTP 500")
            self.assertIsNone(caught.exception.__cause__)

    def test_dependency_http_error_closes_its_response(self) -> None:
        body = io.BytesIO(b"sensitive-canary")
        error = smoke_esignet.urllib.error.HTTPError(
            "http://unused.invalid", 500, "failure", {}, body
        )
        with mock.patch.object(smoke_esignet.urllib.request, "urlopen", side_effect=error):
            with self.assertRaisesRegex(smoke_esignet.SmokeFailure, "^discovery HTTP 500$"):
                smoke_esignet.request_json("GET", "http://unused.invalid")
        self.assertTrue(body.closed)

    def test_main_does_not_require_a_static_relay_credential(self) -> None:
        with mock.patch.object(smoke_esignet, "check_esignet_discovery") as discovery:
            self.assertEqual(
                smoke_esignet.main(
                    [
                        "--env-file",
                        "/missing",
                        "--esignet-url",
                        "http://esignet.test",
                        "--esignet-ui-url",
                        "http://esignet-ui.test",
                    ]
                ),
                0,
            )
        discovery.assert_called_once()


if __name__ == "__main__":
    unittest.main()
