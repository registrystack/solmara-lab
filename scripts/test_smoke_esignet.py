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
    def test_local_and_hosted_profiles_use_the_v020_authenticator_contract(self) -> None:
        local = yaml.safe_load((ROOT / "compose.esignet.yaml").read_text())
        hosted = yaml.safe_load((ROOT / "compose.coolify.esignet.yaml").read_text())
        local_env = local["services"]["esignet"]["environment"]
        hosted_env = hosted["services"]["esignet"]["environment"]
        self.assertEqual(
            local["services"]["portal"]["environment"]["PORTAL_ESIGNET_SUBJECT_CLAIM"],
            "sub",
        )

        for environment in (local_env, hosted_env):
            self.assertIn("REGISTRY_MINT_PRIVATE_JWK", environment)
            self.assertNotIn("REGISTRY_MINT_CLIENT_PRIVATE_JWK", environment)
            self.assertEqual(
                environment["MOSIP_ESIGNET_DATABASE_URL"],
                "jdbc:postgresql://esignet-database:5432/mosip_esignet?currentSchema=esignet",
            )
            self.assertEqual(
                environment["MOSIP_ESIGNET_INTEGRATION_AUTHENTICATOR"],
                "RelayAuthenticationService",
            )
            self.assertIn("esignet-relay-authenticator.jar", environment["plugin_name_env"])
            self.assertEqual(environment["REGISTRY_ESIGNET_ACCOUNT_CHECK_CLAIMS"], "individualId")
            scope_claims = environment["MOSIP_ESIGNET_OPENID_SCOPE_CLAIMS"]
            self.assertNotIn("'name'", scope_claims)
            for claim in (
                "'given_name'",
                "'family_name'",
                "'gender'",
                "'birthdate'",
                "'individual_id'",
            ):
                self.assertIn(claim, scope_claims)
            self.assertEqual(
                environment["REGISTRY_RELAY_DEFAULT_CLAIMS"],
                "individualId,givenName,familyName,birthdate,gender",
            )
            claim_map = json.loads(environment["SPRING_APPLICATION_JSON"])
            self.assertEqual(
                claim_map["registry"]["esignet"]["claim-map"],
                {
                    "sub": "$$psut",
                    "individual_id": "individualId",
                    "given_name": "givenName",
                    "family_name": "familyName",
                    "birthdate": "birthdate",
                    "gender": "gender",
                },
            )

        self.assertEqual(
            local_env["REGISTRY_MINT_TOKEN_ENDPOINT"],
            "https://mint.solmara.registrystack.org/token",
        )
        self.assertEqual(
            hosted_env["REGISTRY_MINT_TOKEN_ENDPOINT"],
            "https://mint-authority-cells.solmara.registrystack.org/token",
        )
        self.assertEqual(
            hosted_env["REGISTRY_RELAY_BASE_URL"],
            "https://nia-relay-authority-cells.solmara.registrystack.org",
        )

        mint = yaml.safe_load((ROOT / "evidence" / "mint.yaml").read_text())
        self.assertEqual(mint["clientAssertion"]["algorithms"], ["ES256", "RS256"])

    def test_browser_smoke_has_only_fixed_sanitized_output(self) -> None:
        source = (ROOT / "scripts" / "smoke-esignet-login.mjs").read_text()
        self.assertEqual(source.count("console.log("), 1)
        self.assertIn("console.log('smoke-esignet-login: PASS')", source)
        self.assertIn("getByRole('checkbox', { name: 'voluntary_claims' })", source)
        self.assertIn("allClaims.check({ force: true })", source)
        self.assertIn("url.pathname.endsWith('/consent')", source)
        self.assertIn("timeout: 60_000", source)
        self.assertNotIn("error.errorCode", source)
        self.assertNotIn("page.title()", source)

        seed_source = (ROOT / "scripts" / "seed-esignet.py").read_text()
        self.assertNotIn("Local static OTP", seed_source)
        self.assertNotIn("Demo subject available", seed_source)

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

    def test_discovery_requires_root_and_mosip_paths_to_share_issuer(self) -> None:
        with StubServer({}) as server:
            issuer_doc = {
                "issuer": server.url,
                "token_endpoint": f"{server.url}/v1/esignet/oauth/v2/token",
            }
            server.routes.update(
                {
                    ("GET", "/v1/esignet/oidc/.well-known/openid-configuration"): (200, issuer_doc),
                    ("GET", "/.well-known/openid-configuration"): (200, issuer_doc),
                    ("GET", "/.well-known/oauth-authorization-server"): (200, issuer_doc),
                }
            )
            targets = smoke_esignet.SmokeTargets(server.url, server.url)
            smoke_esignet.check_esignet_discovery(targets, timeout=2)

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
