from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke-programme-acceptance.py"
SPEC = importlib.util.spec_from_file_location("smoke_programme_acceptance", SCRIPT)
smoke = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["smoke_programme_acceptance"] = smoke
SPEC.loader.exec_module(smoke)


class StubServer:
    def __init__(self, routes: dict[tuple[str, str], tuple[int, Any]]) -> None:
        self.routes = routes
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "StubServer":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.handle_request("GET")

            def do_POST(self) -> None:
                self.handle_request("POST")

            def handle_request(self, method: str) -> None:
                status, payload = outer.routes.get(
                    (method, self.path),
                    (404, {"canary": "private-not-found-detail"}),
                )
                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, fmt: str, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        assert self.server is not None and self.thread is not None
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def url(self) -> str:
        assert self.server is not None
        host, port = self.server.server_address
        return f"http://{host}:{port}"


def scenario_path(scenario: str, step: str) -> str:
    return f"/v1/scenarios/{scenario}/steps/{step}/run"


def success_payload(
    scenario: str,
    claims: dict[str, str],
    services: dict[str, tuple[str, str]],
    *,
    derived_decisions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    presentation_by_issuer = {
        issuer: {
            "authority": f"Public authority {index}",
            "issuer": issuer,
            "provider": f"provider-{index}",
            "source": source,
        }
        for index, (issuer, source) in enumerate(services.values(), start=1)
    }
    result: dict[str, Any] = {
        "response_source": {"status": 200, "code": "ok"},
        "results": [
            {
                "claim_id": claim,
                "concept_id": f"https://id.registrystack.org/solmara/concept/{claim}",
                "satisfied": True,
                "value": True,
                "presentation": presentation_by_issuer[issuer],
            }
            for claim, issuer in claims.items()
        ],
        "presentations": [
            presentation_by_issuer[issuer] for issuer, _ in services.values()
        ],
        "source_trace": [
            {
                "authority": f"Public authority {index}",
                "service_id": service,
                "issuer": issuer,
                "provider": f"provider-{index}",
                "source": source,
                "status": 200,
            }
            for index, (service, (issuer, source)) in enumerate(services.items(), start=1)
        ],
    }
    if derived_decisions is not None:
        result["derived_decisions"] = derived_decisions
    return {
        "schema_version": "solmara-scenario-runner/v1",
        "scenario_id": scenario,
        "result": result,
    }


def refusal_payload(scenario: str) -> dict[str, Any]:
    return {
        "schema_version": "solmara-scenario-runner/v1",
        "scenario_id": scenario,
        "result": {
            "response_source": {"status": 403, "code": "request_refused"},
            "results": [],
            "presentations": [],
            "source_trace": [],
        },
    }


def passing_routes() -> dict[tuple[str, str], tuple[int, Any]]:
    child_services = {
        "cra-evidence": (smoke.CRA, "immutable extract"),
        "nia-evidence": (smoke.NIA, "immutable extract"),
        "sro-evidence": (smoke.SRO, "immutable extract"),
        "mosd-programme-evidence": (smoke.MOSD, "Relay lookup"),
    }
    pension_services = {
        "cra-evidence": (smoke.CRA, "Relay lookup"),
        "sipf-evidence": (smoke.SIPF, "Relay lookup"),
    }
    sipf_services = {"sipf-evidence": (smoke.SIPF, "Relay lookup")}
    nagdi_services = {"nagdi-evidence": (smoke.NAGDI, "Relay lookup")}
    return {
        ("GET", "/health"): (200, {"service": "scenario-runner", "status": "ok"}),
        ("POST", scenario_path("birth-to-child-benefit", "positive")): (
            200,
            success_payload("birth-to-child-benefit", smoke.CHILD_CLAIMS, child_services),
        ),
        ("POST", scenario_path("death-to-pension-survivor", "stop-payment")): (
            200,
            success_payload(
                "death-to-pension-survivor",
                smoke.PENSION_CLAIMS,
                pension_services,
                derived_decisions={
                    "pension-payment-should-stop": True,
                    "owner": "pension-review-application",
                },
            ),
        ),
        ("POST", scenario_path("death-to-pension-survivor", "survivor-benefit")): (
            200,
            success_payload(
                "death-to-pension-survivor",
                smoke.SURVIVOR_CLAIMS,
                sipf_services,
            ),
        ),
        ("POST", scenario_path("farmer-climate-smart-voucher", "positive")): (
            200,
            success_payload(
                "farmer-climate-smart-voucher",
                smoke.VOUCHER_CLAIMS,
                nagdi_services,
            ),
        ),
        ("POST", scenario_path("farmer-climate-smart-voucher", "movement-permit")): (
            200,
            success_payload(
                "farmer-climate-smart-voucher",
                smoke.LIVESTOCK_CLAIMS,
                nagdi_services,
            ),
        ),
        ("POST", scenario_path("birth-to-child-benefit", "purpose-denial")): (
            200,
            refusal_payload("birth-to-child-benefit"),
        ),
        ("POST", scenario_path("death-to-pension-survivor", "cause-of-death-denial")): (
            200,
            refusal_payload("death-to-pension-survivor"),
        ),
        ("POST", scenario_path("farmer-climate-smart-voucher", "purpose-denial")): (
            200,
            refusal_payload("farmer-climate-smart-voucher"),
        ),
        ("GET", "/v1/claims"): (
            401,
            {
                "type": "https://id.registrystack.org/problems/solmara/authentication_required",
                "title": "Authentication Required",
                "status": 401,
                "code": "authentication_required",
                "detail": "A valid local application token is required.",
            },
        ),
    }


class ProgrammeAcceptanceSmokeTests(unittest.TestCase):
    def run_main(self, routes: dict[tuple[str, str], tuple[int, Any]]) -> tuple[int, str, str]:
        with StubServer(routes) as server:
            previous_runner = smoke.RUNNER_URL
            previous_federator = smoke.FEDERATOR_URL
            previous_timeout = smoke.READY_TIMEOUT_SECONDS
            smoke.RUNNER_URL = server.url
            smoke.FEDERATOR_URL = server.url
            smoke.READY_TIMEOUT_SECONDS = 0.2
            stdout = io.StringIO()
            stderr = io.StringIO()
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = smoke.main()
            finally:
                smoke.RUNNER_URL = previous_runner
                smoke.FEDERATOR_URL = previous_federator
                smoke.READY_TIMEOUT_SECONDS = previous_timeout
        return result, stdout.getvalue(), stderr.getvalue()

    def test_all_programme_and_generic_refusal_checks_pass(self) -> None:
        status, stdout, stderr = self.run_main(passing_routes())
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertEqual(len(lines), 10)
        self.assertTrue(
            all(re.fullmatch(r"programme-acceptance: PASS [a-z0-9-]+", line) for line in lines)
        )

    def test_failure_output_never_echoes_response_values(self) -> None:
        routes = passing_routes()
        routes[("POST", scenario_path("birth-to-child-benefit", "positive"))] = (
            500,
            {
                "selector": "PRIVATE-SELECTOR-CANARY",
                "token": "PRIVATE-TOKEN-CANARY",
                "source_row": "PRIVATE-ROW-CANARY",
                "detail": "PRIVATE-DEPENDENCY-CANARY",
            },
        )
        status, stdout, stderr = self.run_main(routes)
        self.assertEqual(status, 1)
        self.assertEqual(stderr, "")
        self.assertIn(
            "programme-acceptance: FAIL child-benefit-four-authorities-five-concepts",
            stdout,
        )
        self.assertNotIn("CANARY", stdout)
        self.assertTrue(
            all(
                re.fullmatch(r"programme-acceptance: (?:PASS|FAIL) [a-z0-9-]+", line)
                for line in stdout.splitlines()
            )
        )

    def test_child_acceptance_requires_four_distinct_expected_issuers(self) -> None:
        routes = passing_routes()
        payload = routes[("POST", scenario_path("birth-to-child-benefit", "positive"))][1]
        payload["result"]["source_trace"][0]["issuer"] = smoke.NIA
        status, stdout, _ = self.run_main(routes)
        self.assertEqual(status, 1)
        self.assertIn("FAIL child-benefit-four-authorities-five-concepts", stdout)

    def test_pension_acceptance_refuses_cause_of_death_disclosure(self) -> None:
        routes = passing_routes()
        payload = routes[("POST", scenario_path("death-to-pension-survivor", "survivor-benefit"))][1]
        payload["result"]["cause_of_death"] = "PRIVATE-CAUSE-CANARY"
        status, stdout, _ = self.run_main(routes)
        self.assertEqual(status, 1)
        self.assertIn("FAIL pension-survivor-minimized-assertion", stdout)
        self.assertNotIn("PRIVATE-CAUSE-CANARY", stdout)

    def test_generic_refusal_must_not_release_results(self) -> None:
        routes = passing_routes()
        payload = routes[("POST", scenario_path("farmer-climate-smart-voucher", "purpose-denial"))][1]
        payload["result"]["results"] = [{"claim_id": "private", "value": True}]
        status, stdout, _ = self.run_main(routes)
        self.assertEqual(status, 1)
        self.assertIn("FAIL agriculture-wrong-purpose-generic-refusal", stdout)


if __name__ == "__main__":
    unittest.main()
