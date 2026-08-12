#!/usr/bin/env python3
"""Contract tests for the Evidence-backed scenario runner and collector."""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scenario-runner"))

import child_benefit_federator  # noqa: E402
from server import ScenarioRunnerHandler  # noqa: E402
from scenarios import child_benefit, citizen, common, farmer_voucher, pension_survivor  # noqa: E402
from scenarios.common import StepHttpResult  # noqa: E402


def b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def signed_evidence(values: list[tuple[str, Any]]) -> dict[str, str]:
    payload = {
        "supportedValues": [
            {"providesValueFor": f"https://id.registrystack.org/solmara/concept/{name}", "value": value}
            for name, value in values
        ]
    }
    return {
        "protected": common.b64url_nopad(b"{}"),
        "payload": common.b64url_nopad(json.dumps(payload).encode()),
        "signature": common.b64url_nopad(b"test-signature"),
    }


class ScenarioRunnerServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["SCENARIO_RUNNER_HOST"] = "127.0.0.1"
        os.environ.pop("SOLMARA_EVIDENCE_ACCESS_TOKEN", None)
        os.environ.pop("SOLMARA_EVIDENCE_CLIENT_KEY", None)
        os.environ.pop("CHILD_BENEFIT_FEDERATOR_TOKEN", None)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ScenarioRunnerHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()

    def test_lists_all_local_evidence_scenarios(self) -> None:
        payload = self.fetch_json("/v1/scenarios")
        self.assertEqual(payload["default_scenario_id"], "birth-to-child-benefit")
        self.assertEqual(len(payload["scenarios"]), 4)
        self.assertTrue(all(item["availability"] == "local" for item in payload["scenarios"]))
        self.assertTrue(all(item["runnable"] for item in payload["scenarios"]))

    def test_detail_previews_evidence_requirements(self) -> None:
        payload = self.fetch_json("/v1/scenarios/citizen-self-service")
        positive = next(step for step in payload["story"]["steps"] if step["id"] == "positive")
        preview = positive["request_preview"]
        self.assertEqual(preview["method"], "MULTI")
        self.assertEqual(len(preview["requests"]), 2)
        self.assertTrue(all(item["url"].endswith("/v1/evidence") for item in preview["requests"]))
        requirements = {item["body"]["requirement"] for item in preview["requests"]}
        self.assertEqual(requirements, {citizen.requirement_id(client) for client in citizen.CLIENTS})

    def test_missing_mint_credentials_is_stable_and_safe(self) -> None:
        first = self.post_json("/v1/scenarios/citizen-self-service/steps/positive/run", {})
        second = self.post_json("/v1/scenarios/citizen-self-service/steps/positive/run", {})
        self.assertEqual(first["result"]["friendly"]["status"], "needs_attention")
        self.assertEqual(first["result"]["response_source"], second["result"]["response_source"])
        serialized = json.dumps(first)
        self.assertIn("Bearer [runtime token hidden]", serialized)
        self.assertNotIn("Bearer runtime-token", serialized)

    def test_purpose_overrides_reach_evidence_request_bodies(self) -> None:
        purpose = "pension-payment-review"
        payload = self.post_json(
            "/v1/scenarios/farmer-climate-smart-voucher/steps/positive/run",
            {"config": {"purpose_override": purpose}},
        )
        self.assertEqual(payload["result"]["request_source"]["body"]["purpose"], purpose)

    def test_denial_steps_ignore_purpose_overrides(self) -> None:
        citizen_result = self.post_json(
            "/v1/scenarios/citizen-self-service/steps/purpose-denial/run",
            {"config": {"purpose_override": common.PURPOSES["citizen_self_service"]}},
        )["result"]
        farmer_result = self.post_json(
            "/v1/scenarios/farmer-climate-smart-voucher/steps/purpose-denial/run",
            {"config": {"purpose_override": common.PURPOSES["livestock"]}},
        )["result"]
        self.assertEqual(citizen_result["request_source"]["purpose"], "unsupported-demo-purpose")
        self.assertEqual(farmer_result["request_source"]["body"]["purpose"], common.PURPOSES["voucher"])

    def test_unknown_scenario_returns_404(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.fetch_json("/v1/scenarios/not-a-story")
        self.assertEqual(raised.exception.code, 404)
        raised.exception.close()

    def fetch_json(self, path: str) -> dict[str, Any]:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as response:
            return json.loads(response.read())

    def post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())


class MintAndEvidenceContractTest(unittest.TestCase):
    def tearDown(self) -> None:
        common._TOKEN_CACHE = ("", 0.0)
        for name in (
            "SOLMARA_EVIDENCE_ACCESS_TOKEN",
            "SOLMARA_MINT_URL",
            "SOLMARA_MINT_ASSERTION_AUDIENCE",
            "SOLMARA_EVIDENCE_CLIENT_ID",
            "SOLMARA_EVIDENCE_CLIENT_KEY",
        ):
            os.environ.pop(name, None)

    def test_evidence_body_uses_bounded_selector_and_unique_nonce(self) -> None:
        first = common.evidence_body("2300018263", "requirement", "purpose")
        second = common.evidence_body("2300018263", "requirement", "purpose")
        self.assertEqual(first["subjects"][0]["selector"]["values"], {"uin": "2300018263"})
        self.assertEqual(len(first["requestNonce"]), 43)
        self.assertNotEqual(first["requestNonce"], second["requestNonce"])

    def test_signed_evidence_is_preserved_and_normalized(self) -> None:
        signed = signed_evidence([("person-is-deceased", True), ("pension-payment-active", False)])
        result = common.normalized_evidence_result(StepHttpResult(200, signed, {"content-type": common.EVIDENCE_JWS_MEDIA_TYPE}))
        self.assertEqual([entry["satisfied"] for entry in result.body["results"]], [True, False])
        self.assertEqual(result.body["signed_evidence"], signed)

    def test_private_key_jwt_and_mint_token_request(self) -> None:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
        except ModuleNotFoundError:
            self.skipTest("cryptography is not installed")

        private_key = Ed25519PrivateKey.generate()
        raw = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        jwk = {"kty": "OKP", "crv": "Ed25519", "kid": "scenario-client-1", "d": common.b64url_nopad(raw)}
        captured: dict[str, Any] = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps({"access_token": "minted-token", "expires_in": 120}).encode()

        original = urllib.request.urlopen

        def fake_urlopen(request, **kwargs):
            captured["url"] = request.full_url
            captured["form"] = urllib.parse.parse_qs(request.data.decode())
            captured["context"] = kwargs.get("context")
            return Response()

        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "client.jwk"
            key_path.write_text(json.dumps(jwk))
            os.environ.update(
                SOLMARA_MINT_URL="https://localhost:4341",
                SOLMARA_MINT_ASSERTION_AUDIENCE="https://mint.evidence.solmara.invalid/token",
                SOLMARA_EVIDENCE_CLIENT_ID="solmara-scenario-runner",
                SOLMARA_EVIDENCE_CLIENT_KEY=str(key_path),
            )
            urllib.request.urlopen = fake_urlopen
            try:
                token = common.evidence_access_token()
            finally:
                urllib.request.urlopen = original

        self.assertEqual(token, "minted-token")
        self.assertEqual(captured["url"], "https://localhost:4341/token")
        assertion = captured["form"]["client_assertion"][0]
        header_segment, claims_segment, signature_segment = assertion.split(".")
        header = json.loads(b64url_decode(header_segment))
        claims = json.loads(b64url_decode(claims_segment))
        self.assertEqual(header, {"alg": "EdDSA", "typ": "JWT", "kid": "scenario-client-1"})
        self.assertEqual(claims["iss"], "solmara-scenario-runner")
        self.assertEqual(claims["sub"], "solmara-scenario-runner")
        self.assertEqual(
            claims["aud"], "https://mint.evidence.solmara.invalid/token"
        )
        self.assertEqual(claims["exp"] - claims["iat"], 120)
        private_key.public_key().verify(b64url_decode(signature_segment), f"{header_segment}.{claims_segment}".encode())


class EvidenceScenarioTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["SOLMARA_EVIDENCE_ACCESS_TOKEN"] = "runtime-token"

    def tearDown(self) -> None:
        os.environ.pop("SOLMARA_EVIDENCE_ACCESS_TOKEN", None)

    def test_pension_combines_two_signed_requirements_in_the_application(self) -> None:
        calls: list[dict[str, Any]] = []
        original = pension_survivor.http_json

        def fake_http_json(method, url, headers, body=None, timeout=8.0):
            calls.append(body)
            requirement = body["requirement"]
            concept = "person-is-deceased" if "cra-pension-death" in requirement else "pension-payment-active"
            return StepHttpResult(200, signed_evidence([(concept, True)]), {})

        pension_survivor.http_json = fake_http_json
        try:
            result = pension_survivor.run_step({}, "stop-payment")
        finally:
            pension_survivor.http_json = original
        self.assertEqual(len(calls), 2)
        self.assertTrue(result["derived_decisions"]["pension-payment-should-stop"])
        self.assertEqual({trace["service_id"] for trace in result["source_trace"]}, {"registry-evidence"})
        self.assertEqual(len(result["response_source"]["body"]["signed_evidence"]), 2)

    def test_citizen_requests_cra_and_nia_requirements(self) -> None:
        calls: list[str] = []
        original = citizen.http_json

        def fake_http_json(method, url, headers, body=None, timeout=8.0):
            calls.append(body["requirement"])
            concept = "civil-record-linked" if "cra-citizen" in body["requirement"] else "citizen-population-record-active"
            return StepHttpResult(200, signed_evidence([(concept, True)]), {})

        citizen.http_json = fake_http_json
        try:
            result = citizen.run_step({}, "positive")
        finally:
            citizen.http_json = original
        self.assertEqual(calls, [citizen.requirement_id(client) for client in citizen.CLIENTS])
        self.assertEqual(len(result["source_trace"]), 2)


class ChildBenefitCollectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ[child_benefit_federator.FEDERATOR_TOKEN_ENV] = "collector-token"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), child_benefit_federator.ChildBenefitFederatorHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()
        os.environ.pop(child_benefit_federator.FEDERATOR_TOKEN_ENV, None)

    def request(self, path: str, *, token: str = "collector-token", body: dict[str, Any] | None = None):
        headers = {"x-api-key": token}
        data = None
        method = "GET"
        if body is not None:
            headers.update({"Content-Type": "application/json", "Data-Purpose": common.PURPOSES["child_benefit"]})
            data = json.dumps(body).encode()
            method = "POST"
        return urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=headers, method=method),
            timeout=5,
        )

    def test_catalog_lists_five_source_owned_concepts(self) -> None:
        with self.request("/v1/claims") as response:
            payload = json.loads(response.read())
        self.assertEqual({item["claim_id"] for item in payload["claims"]}, set(child_benefit.CLAIMS))
        self.assertNotIn("eligible-for-child-benefit", json.dumps(payload))

    def test_requires_local_application_auth(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request("/v1/claims", token="wrong")
        self.assertEqual(raised.exception.code, 401)
        self.assertEqual(
            raised.exception.headers.get_content_type(), "application/problem+json"
        )
        raised.exception.close()

    def test_rejects_duplicate_or_unknown_concepts_before_evidence(self) -> None:
        base = {"target": {"identifiers": [{"scheme": "solmara_uin", "value": "2300010248"}]}}
        for claims in (["birth-is-registered", "birth-is-registered"], ["not-a-concept"]):
            with self.subTest(claims=claims), self.assertRaises(urllib.error.HTTPError) as raised:
                self.request("/v1/evaluations", body={**base, "claims": claims})
            self.assertEqual(raised.exception.code, 400)
            self.assertEqual(
                raised.exception.headers.get_content_type(),
                "application/problem+json",
            )
            problem = json.loads(raised.exception.read())
            self.assertEqual(problem["code"], "invalid_request")
            self.assertNotIn("2300010248", json.dumps(problem))
            self.assertTrue(
                {"type", "title", "status", "code", "detail"}.issubset(problem)
            )
            raised.exception.close()

    def test_collects_central_evidence_with_exact_authority_trace(self) -> None:
        claims_by_requirement = {
            child_benefit_federator.requirement_id(route["client_id"]): route["claims"]
            for route in child_benefit_federator.SOURCE_ROUTES
        }
        calls: list[tuple[str, str, dict[str, str], dict[str, Any]]] = []
        original_http_json = child_benefit_federator.http_json
        original_service_token = child_benefit_federator.service_token

        def fake_http_json(method, url, headers, body=None, timeout=8.0):
            calls.append((method, url, headers, body))
            return StepHttpResult(
                200,
                signed_evidence(
                    [(claim, True) for claim in claims_by_requirement[body["requirement"]]]
                ),
                {"content-type": common.EVIDENCE_JWS_MEDIA_TYPE},
            )

        child_benefit_federator.http_json = fake_http_json
        child_benefit_federator.service_token = lambda _: "evidence-token"
        try:
            with self.request(
                "/v1/evaluations",
                body={
                    "target": {
                        "identifiers": [
                            {"scheme": "solmara_uin", "value": "2300010248"}
                        ]
                    },
                    "claims": list(child_benefit.CLAIMS),
                },
            ) as response:
                payload = json.loads(response.read())
        finally:
            child_benefit_federator.http_json = original_http_json
            child_benefit_federator.service_token = original_service_token

        self.assertEqual(len(calls), 4)
        self.assertTrue(all(method == "POST" for method, _, _, _ in calls))
        self.assertTrue(
            all(url.endswith("/v1/evidence") for _, url, _, _ in calls)
        )
        self.assertTrue(
            all(
                headers == {
                    "Authorization": "Bearer evidence-token",
                    "Accept": common.EVIDENCE_JWS_MEDIA_TYPE,
                }
                for _, _, headers, _ in calls
            )
        )
        self.assertEqual(
            [body["requirement"] for _, _, _, body in calls],
            [
                child_benefit_federator.requirement_id(route["client_id"])
                for route in child_benefit_federator.SOURCE_ROUTES
            ],
        )
        self.assertEqual(
            len({body["requestNonce"] for _, _, _, body in calls}),
            4,
        )
        self.assertEqual(
            [trace["authority"] for trace in payload["source_trace"]],
            [route["authority"] for route in child_benefit_federator.SOURCE_ROUTES],
        )
        self.assertEqual(
            [trace["requirement"] for trace in payload["source_trace"]],
            [
                child_benefit_federator.requirement_id(route["client_id"])
                for route in child_benefit_federator.SOURCE_ROUTES
            ],
        )
        self.assertEqual(
            {trace["service_id"] for trace in payload["source_trace"]},
            {"registry-evidence"},
        )
        self.assertEqual(len(payload["signed_evidence"]), 4)
        self.assertNotIn("2300010248", json.dumps(payload))

    def test_upstream_evidence_denial_returns_value_free_problem(self) -> None:
        original_http_json = child_benefit_federator.http_json
        original_service_token = child_benefit_federator.service_token
        child_benefit_federator.http_json = lambda *args, **kwargs: StepHttpResult(
            403,
            {"value": "2300010248", "source_record": {"private": True}},
            {"content-type": "application/problem+json"},
        )
        child_benefit_federator.service_token = lambda _: "evidence-token"
        try:
            with self.assertRaises(urllib.error.HTTPError) as raised:
                self.request(
                    "/v1/evaluations",
                    body={
                        "target": {
                            "identifiers": [
                                {"scheme": "solmara_uin", "value": "2300010248"}
                            ]
                        },
                        "claims": ["birth-is-registered"],
                    },
                )
            self.assertEqual(raised.exception.code, 502)
            self.assertEqual(
                raised.exception.headers.get_content_type(),
                "application/problem+json",
            )
            problem = json.loads(raised.exception.read())
            self.assertEqual(problem["code"], "evidence_unavailable")
            self.assertNotIn("2300010248", json.dumps(problem))
            self.assertNotIn("source_record", problem)
            raised.exception.close()
        finally:
            child_benefit_federator.http_json = original_http_json
            child_benefit_federator.service_token = original_service_token


if __name__ == "__main__":
    unittest.main()
