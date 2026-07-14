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
                    "response_source": {
                        "status": 200,
                        "body": {
                            "orchestration": {
                                "service_id": "child-benefit-federator",
                                "decision": "not_composed",
                            },
                            "results": [
                                {
                                    "claim_id": "birth-is-registered",
                                    "satisfied": True,
                                    "notary_service_id": "cra-notary",
                                },
                                {
                                    "claim_id": "population-record-active",
                                    "satisfied": True,
                                    "notary_service_id": "nia-notary",
                                },
                                {
                                    "claim_id": "child-age-under-5",
                                    "satisfied": True,
                                    "notary_service_id": "cra-notary",
                                },
                                {
                                    "claim_id": "household-below-poverty-threshold",
                                    "satisfied": True,
                                    "notary_service_id": "sro-notary",
                                },
                                {
                                    "claim_id": "not-already-enrolled",
                                    "satisfied": True,
                                    "notary_service_id": "programme-notary",
                                },
                            ],
                            "source_trace": [
                                {"service_id": "cra-notary"},
                                {"service_id": "nia-notary"},
                                {"service_id": "sro-notary"},
                                {"service_id": "programme-notary"},
                            ],
                        },
                    },
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


class HostedSmokeTests(unittest.TestCase):
    def test_default_targets_use_public_solmara_domains(self) -> None:
        targets = smoke_hosted.default_targets("https://solmara.registrystack.org/")
        self.assertEqual(targets.home_url, "https://solmara.registrystack.org")
        self.assertEqual(targets.portal_url, "https://portal.solmara.registrystack.org")
        self.assertEqual(
            targets.esignet_url, "https://esignet.solmara.registrystack.org"
        )
        self.assertEqual(
            targets.esignet_ui_url, "https://esignet-ui.solmara.registrystack.org"
        )
        self.assertEqual(targets.wallet_url, "https://wallet.solmara.registrystack.org")
        self.assertIn(
            "https://cra-relay.solmara.registrystack.org",
            {relay.base_url for relay in targets.relays},
        )
        authority_urls = {
            "https://cra-notary.solmara.registrystack.org",
            "https://nia-notary.solmara.registrystack.org",
            "https://sro-notary.solmara.registrystack.org",
            "https://programme-notary.solmara.registrystack.org",
            "https://sipf-notary.solmara.registrystack.org",
            "https://nagdi-notary.solmara.registrystack.org",
        }
        self.assertEqual(
            authority_urls,
            {notary.base_url for notary in targets.notaries},
        )
        self.assertEqual(
            {"https://child-benefit-federator.solmara.registrystack.org"},
            {application.base_url for application in targets.applications},
        )

    def test_hosted_env_overrides_public_service_urls_without_tokens(self) -> None:
        targets = smoke_hosted.default_targets("solmara.registrystack.org")
        env = smoke_hosted.hosted_env(
            {"CHILD_BENEFIT_FEDERATOR_TOKEN": "keep-local"}, targets
        )
        self.assertEqual(
            env["CHILD_BENEFIT_FEDERATOR_URL"],
            "https://child-benefit-federator.solmara.registrystack.org",
        )
        self.assertEqual(
            env["CRA_NOTARY_URL"], "https://cra-notary.solmara.registrystack.org"
        )
        self.assertEqual(
            env["NIA_NOTARY_URL"], "https://nia-notary.solmara.registrystack.org"
        )
        self.assertEqual(
            env["SRO_NOTARY_URL"], "https://sro-notary.solmara.registrystack.org"
        )
        self.assertEqual(
            env["PROGRAMME_NOTARY_URL"],
            "https://programme-notary.solmara.registrystack.org",
        )
        self.assertEqual(
            env["SIPF_NOTARY_URL"], "https://sipf-notary.solmara.registrystack.org"
        )
        self.assertEqual(
            env["NAGDI_NOTARY_URL"],
            "https://nagdi-notary.solmara.registrystack.org",
        )
        self.assertEqual(
            env["SOLMARA_CRA_RELAY_URL"], "https://cra-relay.solmara.registrystack.org"
        )
        self.assertEqual(
            env["SOLMARA_PORTAL_URL"], "https://portal.solmara.registrystack.org"
        )
        self.assertEqual(
            env["SOLMARA_ESIGNET_PUBLIC_BASE_URL"],
            "https://esignet.solmara.registrystack.org",
        )
        self.assertEqual(
            env["SOLMARA_ESIGNET_UI_PUBLIC_BASE_URL"],
            "https://esignet-ui.solmara.registrystack.org",
        )
        self.assertEqual(
            env["SOLMARA_WALLET_URL"], "https://wallet.solmara.registrystack.org"
        )
        self.assertEqual(env["SOLMARA_PORTAL_EXPECT_AUTH_REQUIRED"], "1")
        self.assertEqual(env["CHILD_BENEFIT_FEDERATOR_TOKEN"], "keep-local")

    def test_normalize_argv_accepts_just_separator(self) -> None:
        self.assertEqual(
            smoke_hosted.normalize_argv(["--", "--browser"]), ["--browser"]
        )
        self.assertEqual(smoke_hosted.normalize_argv(["--browser"]), ["--browser"])

    def test_home_demo_accepts_expected_scenario_flow(self) -> None:
        with StubServer(hosted_routes()) as server:
            smoke_hosted.check_home_demo(server.url, timeout=2)

    def test_home_demo_rejects_composed_child_benefit_decision(self) -> None:
        routes = hosted_routes()
        positive = routes[
            ("POST", "/api/scenarios/birth-to-child-benefit/steps/positive/run")
        ][1]
        positive["result"]["response_source"]["body"]["orchestration"]["decision"] = (
            "eligible"
        )
        with StubServer(routes) as server:
            with self.assertRaises(smoke_hosted.SmokeFailure):
                smoke_hosted.check_home_demo(server.url, timeout=2)

    def test_home_demo_requires_stable_denial_code(self) -> None:
        routes = hosted_routes()
        routes[
            ("POST", "/api/scenarios/birth-to-child-benefit/steps/purpose-denial/run")
        ] = (
            200,
            {"result": {"response_source": {"status": 403, "body": {}}}},
        )
        with StubServer(routes) as server:
            with self.assertRaises(smoke_hosted.SmokeFailure):
                smoke_hosted.check_home_demo(server.url, timeout=2)


if __name__ == "__main__":
    unittest.main()
