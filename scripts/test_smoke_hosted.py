from __future__ import annotations

import importlib.util
import json
import sys
import threading
import unittest
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke-hosted.py"
SPEC = importlib.util.spec_from_file_location("smoke_hosted", SCRIPT)
smoke_hosted = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["smoke_hosted"] = smoke_hosted
SPEC.loader.exec_module(smoke_hosted)


class StubServer:
    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
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
                status, payload, *header_items = route
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for key, value in dict(header_items[0] if header_items else {}).items():
                    self.send_header(key, value)
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


def hosted_routes() -> dict[tuple[str, str], Any]:
    return {
        ("GET", "/api/scenarios"): (
            200,
            {
                "default_scenario_id": "birth-to-child-benefit",
                "scenarios": [
                    {"id": "birth-to-child-benefit"},
                    {"id": "death-to-pension-survivor"},
                    {"id": "farmer-climate-smart-voucher"},
                    {"id": "citizen-self-service"},
                ],
            },
        ),
        ("POST", "/api/scenarios/birth-to-child-benefit/steps/positive/run"): (
            200,
            {
                "result": {
                    "response_source": {"status": 200, "body": {"results": []}},
                    "credential": {"status": "issued"},
                }
            },
        ),
        ("POST", "/api/scenarios/birth-to-child-benefit/steps/purpose-denial/run"): (
            200,
            {
                "result": {
                    "response_source": {
                        "status": 403,
                        "body": {"code": "pdp.purpose_not_permitted"},
                    }
                }
            },
        ),
    }


def oid4vci_routes(issuer_url: str, esignet_url: str, esignet_ui_url: str) -> dict[tuple[str, str], Any]:
    config_id = "citizen_status_sd_jwt"
    return {
        ("GET", "/.well-known/openid-credential-issuer"): (
            200,
            {
                "credential_issuer": issuer_url,
                "credential_endpoint": f"{issuer_url}/oid4vci/credential",
                "token_endpoint": f"{issuer_url}/oid4vci/token",
                "nonce_endpoint": f"{issuer_url}/oid4vci/nonce",
                "authorization_servers": [esignet_url],
                "credential_configurations_supported": {
                    config_id: {
                        "format": "dc+sd-jwt",
                        "scope": "citizen-self-service-status",
                        "cryptographic_binding_methods_supported": ["did:jwk"],
                        "credential_signing_alg_values_supported": ["EdDSA"],
                        "proof_types_supported": {
                            "jwt": {"proof_signing_alg_values_supported": ["EdDSA"]},
                        },
                        "vct": f"{issuer_url}/credentials/citizen-status/v1",
                    }
                },
            },
        ),
        ("GET", "/.well-known/vct/credentials/citizen-status/v1"): (
            200,
            {"vct": f"{issuer_url}/credentials/citizen-status/v1", "name": "Solmara Citizen Status"},
        ),
        ("GET", f"/oid4vci/credential-offer?credential_configuration_id={config_id}"): (
            200,
            {"credential_configuration_ids": [config_id]},
        ),
        ("GET", "/oid4vci/credential-offer?credential_configuration_id=unknown"): (
            400,
            {"error": "invalid_request"},
        ),
        ("POST", "/oid4vci/nonce"): (
            200,
            {"c_nonce": "nonce-1", "c_nonce_expires_in": 300},
        ),
        ("GET", f"/oid4vci/offer/start?credential_configuration_id={config_id}"): (
            303,
            {},
            {"Location": f"{esignet_ui_url}/authorize?state=state-1"},
        ),
        ("POST", "/oid4vci/credential"): (
            401,
            {"error": "invalid_token"},
        ),
    }


class HostedSmokeTests(unittest.TestCase):
    def test_default_targets_use_public_solmara_domains(self) -> None:
        targets = smoke_hosted.default_targets("https://solmara.registrystack.org/")
        self.assertEqual(targets.home_url, "https://solmara.registrystack.org")
        self.assertEqual(targets.portal_url, "https://portal.solmara.registrystack.org")
        self.assertEqual(targets.esignet_url, "https://esignet.solmara.registrystack.org")
        self.assertEqual(targets.esignet_ui_url, "https://esignet-ui.solmara.registrystack.org")
        self.assertEqual(targets.wallet_url, "https://wallet.solmara.registrystack.org")
        self.assertIn("https://cra-relay.solmara.registrystack.org", {relay.base_url for relay in targets.relays})
        self.assertIn(
            "https://child-benefit-notary.solmara.registrystack.org",
            {notary.base_url for notary in targets.notaries},
        )
        self.assertIn(
            "https://citizen-issuer-notary.solmara.registrystack.org",
            {notary.base_url for notary in targets.notaries},
        )

    def test_hosted_env_overrides_public_service_urls_without_tokens(self) -> None:
        targets = smoke_hosted.default_targets("solmara.registrystack.org")
        env = smoke_hosted.hosted_env({"CHILD_BENEFIT_NOTARY_TOKEN": "keep-local"}, targets)
        self.assertEqual(env["CHILD_BENEFIT_NOTARY_URL"], "https://child-benefit-notary.solmara.registrystack.org")
        self.assertEqual(env["SOLMARA_CRA_RELAY_URL"], "https://cra-relay.solmara.registrystack.org")
        self.assertEqual(env["SOLMARA_PORTAL_URL"], "https://portal.solmara.registrystack.org")
        self.assertEqual(env["SOLMARA_ESIGNET_PUBLIC_BASE_URL"], "https://esignet.solmara.registrystack.org")
        self.assertEqual(env["SOLMARA_ESIGNET_UI_PUBLIC_BASE_URL"], "https://esignet-ui.solmara.registrystack.org")
        self.assertEqual(env["SOLMARA_WALLET_URL"], "https://wallet.solmara.registrystack.org")
        self.assertEqual(
            env["CITIZEN_ISSUER_NOTARY_URL"],
            "https://citizen-issuer-notary.solmara.registrystack.org",
        )
        self.assertEqual(env["SOLMARA_PORTAL_EXPECT_AUTH_REQUIRED"], "1")
        self.assertEqual(env["CHILD_BENEFIT_NOTARY_TOKEN"], "keep-local")

    def test_normalize_argv_accepts_just_separator(self) -> None:
        self.assertEqual(smoke_hosted.normalize_argv(["--", "--browser"]), ["--browser"])
        self.assertEqual(smoke_hosted.normalize_argv(["--browser"]), ["--browser"])

    def test_home_demo_accepts_expected_scenario_flow(self) -> None:
        with StubServer(hosted_routes()) as server:
            smoke_hosted.check_home_demo(server.url, timeout=2)

    def test_home_demo_requires_stable_denial_code(self) -> None:
        routes = hosted_routes()
        routes[("POST", "/api/scenarios/birth-to-child-benefit/steps/purpose-denial/run")] = (
            200,
            {"result": {"response_source": {"status": 403, "body": {}}}},
        )
        with StubServer(routes) as server:
            with self.assertRaises(smoke_hosted.SmokeFailure):
                smoke_hosted.check_home_demo(server.url, timeout=2)

    def test_oid4vci_issuer_accepts_expected_metadata_and_redirect(self) -> None:
        with StubServer({}) as server:
            targets = smoke_hosted.HostedTargets(
                home_url=server.url,
                portal_url=server.url,
                metadata_url=server.url,
                esignet_url=f"{server.url}/esignet",
                esignet_ui_url=f"{server.url}/esignet-ui",
                wallet_url=server.url,
                relays=(),
                notaries=(
                    smoke_hosted.ServiceTarget(
                        "citizen OID4VCI issuer notary",
                        server.url,
                        env_name="CITIZEN_ISSUER_NOTARY_URL",
                    ),
                ),
            )
            server.routes.update(oid4vci_routes(server.url, targets.esignet_url, targets.esignet_ui_url))
            smoke_hosted.check_oid4vci_issuer(targets, timeout=2)


if __name__ == "__main__":
    unittest.main()
