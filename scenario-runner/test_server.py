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
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scenario-runner"))

import child_benefit_federator  # noqa: E402
from server import ScenarioRunnerHandler  # noqa: E402
from scenarios import child_benefit, citizen, common, pension_survivor  # noqa: E402
from scenarios.common import StepHttpResult  # noqa: E402
from scenarios import service_config  # noqa: E402


def b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


AUTHORITY_KEYS = {authority: ec.generate_private_key(ec.SECP256R1()) for authority in service_config.AUTHORITY_DIRECTORY}


def public_jwk(private_key) -> dict[str, str]:
    numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "EC",
        "alg": "ES256",
        "crv": "P-256",
        "x": common.b64url_nopad(numbers.x.to_bytes(32, "big")),
        "y": common.b64url_nopad(numbers.y.to_bytes(32, "big")),
    }
    jwk["kid"] = common._jwk_thumbprint(jwk)
    return jwk


def install_authority_keys() -> None:
    common._JWKS_CACHE.clear()
    for authority, private_key in AUTHORITY_KEYS.items():
        service_id = next(key for key, value in service_config.REQUIREMENT_DIRECTORY.items() if value["authority"] == authority)
        url = service_config.service_url(service_id, "/.well-known/evidence/jwks.json")
        common._JWKS_CACHE[url] = (time.monotonic() + 300, (public_jwk(private_key),))


def signed_evidence(service_id: str, request: dict[str, Any], values: list[tuple[str, Any]], *, private_key=None, claims: dict[str, Any] | None = None) -> dict[str, str]:
    config = service_config.requirement_config(service_id)
    private_key = private_key or AUTHORITY_KEYS[config["authority"]]
    jwk = public_jwk(private_key)
    now = datetime_now = time.time()
    payload = {
        "schema": "registry.assertion-evidence/v1",
        "assuranceProfile": "production",
        "subjectBinding": "audience-scoped",
        "requestNonce": request["requestNonce"],
        "id": f"urn:uuid:{uuid.uuid4()}",
        "type": "Evidence",
        "supportsRequirement": request["requirement"],
        "isConformantTo": config["evidence_type"],
        "issuedBy": config["issuer"],
        "providedBy": config["provider"],
        "issuedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(datetime_now)),
        "observedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(datetime_now)),
        "validUntil": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 300)),
        "purpose": request["purpose"],
        "audience": common.EVIDENCE_AUDIENCE,
        "configurationRevision": f"sha256:{'a' * 64}",
        "subjects": [{"role": "subject", "binding": f"urn:evidence:subject:v1_{'A' * 43}"}],
        "supportedValues": [
            {"providesValueFor": f"https://id.registrystack.org/solmara/concept/{name}", "value": value}
            for name, value in values
        ],
    }
    payload.update(claims or {})
    protected = common.b64url_nopad(json.dumps({**common.EVIDENCE_JWS_HEADER, "kid": jwk["kid"]}, separators=(",", ":")).encode())
    payload_segment = common.b64url_nopad(json.dumps(payload, separators=(",", ":")).encode())
    der_signature = private_key.sign(f"{protected}.{payload_segment}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_signature)
    return {
        "protected": protected,
        "payload": payload_segment,
        "signature": common.b64url_nopad(r.to_bytes(32, "big") + s.to_bytes(32, "big")),
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
        self.assertTrue(all("body" not in item for item in preview["requests"]))
        self.assertNotIn("2300018263", json.dumps(preview))

    def test_missing_mint_credentials_is_stable_and_safe(self) -> None:
        first = self.post_json("/v1/scenarios/citizen-self-service/steps/positive/run", {})
        second = self.post_json("/v1/scenarios/citizen-self-service/steps/positive/run", {})
        self.assertEqual(first["result"]["friendly"]["status"], "needs_attention")
        self.assertEqual(first["result"]["response_source"], second["result"]["response_source"])
        serialized = json.dumps(first)
        self.assertIn("Bearer [runtime token hidden]", serialized)
        self.assertNotIn("Bearer runtime-token", serialized)

    def test_purpose_overrides_are_not_exposed_in_request_traces(self) -> None:
        purpose = "pension-payment-review"
        payload = self.post_json(
            "/v1/scenarios/farmer-climate-smart-voucher/steps/positive/run",
            {"config": {"purpose_override": purpose}},
        )
        self.assertNotIn("body", payload["result"]["request_source"])
        self.assertNotIn(purpose, json.dumps(payload["result"]["request_source"]))

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
        self.assertNotIn("body", farmer_result["request_source"])

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
    def setUp(self) -> None:
        install_authority_keys()

    def tearDown(self) -> None:
        common._TOKEN_CACHE = ("", 0.0)
        common._JWKS_CACHE.clear()
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
        request = common.evidence_body("2300109568", service_config.requirement_id("cra-pension"), common.PURPOSES["pension_payment"])
        signed = signed_evidence("cra-pension", request, [("person-is-deceased", True)])
        result = common.normalized_evidence_result(StepHttpResult(200, signed, {"content-type": common.EVIDENCE_JWS_MEDIA_TYPE}), request=request, service_id="cra-pension")
        self.assertEqual([entry["satisfied"] for entry in result.body["results"]], [True])
        self.assertEqual(result.body["signed_evidence"], signed)
        self.assertEqual(result.body["presentation"]["source"], "Relay lookup")

    def test_safe_projection_omits_jws_and_assertion_payloads(self) -> None:
        presentation = {
            "authority": "Civil Registration Authority",
            "issuer": "did:web:id.registrystack.org:solmara:authority:cra",
            "provider": "https://id.registrystack.org/solmara/evidence/cra",
            "source": "Relay lookup",
        }
        projection = common.safe_evidence_projection(
            StepHttpResult(
                200,
                {
                    "results": [
                        {
                            "claim_id": "person-is-deceased",
                            "concept_id": "https://id.registrystack.org/solmara/concept/person-is-deceased",
                            "satisfied": True,
                            "value": True,
                            "presentation": presentation,
                        }
                    ],
                    "presentation": presentation,
                    "assertion": {"secret": "must-not-leave-server"},
                    "signed_evidence": {"payload": "must-not-leave-server"},
                },
                {},
            )
        )
        self.assertEqual(projection["presentations"], [presentation])
        self.assertEqual(projection["results"][0]["value"], True)
        rendered = json.dumps(projection)
        self.assertNotIn("must-not-leave-server", rendered)
        self.assertNotIn("assertion", rendered)
        self.assertNotIn("signed_evidence", rendered)

    def test_safe_projection_attributes_single_authority_results(self) -> None:
        presentation = {
            "authority": "National Agricultural Data Institute",
            "issuer": "did:web:id.registrystack.org:solmara:authority:nagdi",
            "provider": "https://id.registrystack.org/solmara/evidence/nagdi",
            "source": "Relay lookup",
        }
        projection = common.safe_evidence_projection(
            StepHttpResult(
                200,
                {
                    "results": [
                        {
                            "claim_id": "farmer-registered",
                            "concept_id": "https://id.registrystack.org/solmara/concept/farmer-registered",
                            "satisfied": True,
                            "value": True,
                        }
                    ],
                    "presentation": presentation,
                },
                {},
            )
        )
        self.assertEqual(projection["results"][0]["presentation"], presentation)

    def test_child_scenario_deduplicates_authority_presentations(self) -> None:
        presentation = {
            "authority": "Civil Registration Authority",
            "issuer": "did:web:id.registrystack.org:solmara:authority:cra",
            "provider": "https://id.registrystack.org/solmara/evidence/cra",
            "source": "immutable extract",
        }
        original = child_benefit.http_json
        child_benefit.http_json = lambda *args, **kwargs: StepHttpResult(
            200,
            {
                "results": [
                    {"claim_id": "birth-is-registered", "satisfied": True, "presentation": presentation},
                    {"claim_id": "child-age-under-5", "satisfied": True, "presentation": presentation},
                ],
                "source_trace": [],
            },
            {},
        )
        try:
            os.environ[service_config.service_token_env(child_benefit.SERVICE_ID)] = "collector-token"
            result = child_benefit.run_step({}, "positive")
        finally:
            child_benefit.http_json = original
            os.environ.pop(service_config.service_token_env(child_benefit.SERVICE_ID), None)
        self.assertEqual(result["presentations"], [presentation])

    def test_cross_authority_key_is_rejected(self) -> None:
        request = common.evidence_body("2300010248", service_config.requirement_id("cra-child-benefit"), common.PURPOSES["child_benefit"])
        signed = signed_evidence("cra-child-benefit", request, [("birth-is-registered", True), ("child-age-under-5", True)], private_key=AUTHORITY_KEYS["nia"])
        result = common.normalized_evidence_result(StepHttpResult(200, signed, {"content-type": common.EVIDENCE_JWS_MEDIA_TYPE}), request=request, service_id="cra-child-benefit")
        self.assertEqual(result.status, 502)
        self.assertEqual(common.source_response(result), {"status": 502, "code": "assertion_verification_failed"})

    def test_signature_tamper_is_rejected(self) -> None:
        request = common.evidence_body("2300010248", service_config.requirement_id("nia-child-benefit"), common.PURPOSES["child_benefit"])
        signed = signed_evidence("nia-child-benefit", request, [("population-record-active", True)])
        signed["signature"] = ("A" if signed["signature"][0] != "A" else "B") + signed["signature"][1:]
        result = common.normalized_evidence_result(StepHttpResult(200, signed, {"content-type": common.EVIDENCE_JWS_MEDIA_TYPE}), request=request, service_id="nia-child-benefit")
        self.assertEqual(result.status, 502)
        self.assertNotIn("signature", json.dumps(common.source_response(result)))

    def test_claim_mismatch_is_rejected(self) -> None:
        request = common.evidence_body("2300010248", service_config.requirement_id("sro-child-benefit"), common.PURPOSES["child_benefit"])
        signed = signed_evidence("sro-child-benefit", request, [("household-below-poverty-threshold", True)], claims={"requestNonce": "B" * 43})
        result = common.normalized_evidence_result(StepHttpResult(200, signed, {"content-type": common.EVIDENCE_JWS_MEDIA_TYPE}), request=request, service_id="sro-child-benefit")
        self.assertEqual(result.status, 502)
        self.assertNotIn(request["requestNonce"], json.dumps(result.body))

    def test_relay_assertion_above_five_minutes_is_rejected(self) -> None:
        request = common.evidence_body("2300109568", service_config.requirement_id("cra-pension"), common.PURPOSES["pension_payment"])
        issued = int(time.time())
        claims = {
            "issuedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(issued)),
            "observedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(issued)),
            "validUntil": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(issued + 301)),
        }
        signed = signed_evidence("cra-pension", request, [("person-is-deceased", True)], claims=claims)
        result = common.normalized_evidence_result(StepHttpResult(200, signed, {"content-type": common.EVIDENCE_JWS_MEDIA_TYPE}), request=request, service_id="cra-pension")
        self.assertEqual(result.status, 502)

    def test_request_and_problem_traces_are_value_free(self) -> None:
        selector = "2300010248"
        request = common.evidence_body(selector, service_config.requirement_id("cra-child-benefit"), common.PURPOSES["child_benefit"])
        trace = common.request_source("POST", f"https://cra.example/v1/evidence?uin={selector}", {"Authorization": "Bearer secret", "X-Selector": selector}, request)
        response = common.source_response(StepHttpResult(403, {"detail": selector, "source": "private"}, {}, "canary-error"))
        rendered = json.dumps({"request": trace, "response": response})
        self.assertNotIn(selector, rendered)
        self.assertNotIn("private", rendered)
        self.assertNotIn("canary-error", rendered)


class AuthorityRoutingTest(unittest.TestCase):
    def tearDown(self) -> None:
        common._TOKEN_CACHE = ("", 0.0)
        for config in service_config.AUTHORITY_DIRECTORY.values():
            os.environ.pop(config["env"], None)
        for name in (
            "SOLMARA_EVIDENCE_URL",
            "SOLMARA_MINT_URL",
            "SOLMARA_MINT_ASSERTION_AUDIENCE",
            "SOLMARA_EVIDENCE_CLIENT_ID",
            "SOLMARA_EVIDENCE_CLIENT_KEY",
        ):
            os.environ.pop(name, None)

    def test_all_requirement_aliases_route_to_their_authority_cell(self) -> None:
        expected_hosts = {
            "cra": "cra-evidence.solmara.registrystack.org",
            "nia": "nia-evidence.solmara.registrystack.org",
            "sro": "sro-evidence.solmara.registrystack.org",
            "mosd-programme": "mosd-programme-evidence.solmara.registrystack.org",
            "sipf": "sipf-evidence.solmara.registrystack.org",
            "nagdi": "nagdi-evidence.solmara.registrystack.org",
        }
        self.assertEqual(len(service_config.REQUIREMENT_DIRECTORY), 11)
        for service_id, route in service_config.REQUIREMENT_DIRECTORY.items():
            with self.subTest(service_id=service_id):
                self.assertEqual(urllib.parse.urlsplit(service_config.service_url(service_id)).hostname, expected_hosts[route["authority"]])
                self.assertEqual(service_config.authority_service_id(service_id), f"{route['authority']}-evidence")

    def test_source_labels_match_the_requirement_acquisition_path(self) -> None:
        immutable = {"cra-child-benefit", "nia-child-benefit", "nia-citizen", "sro-child-benefit"}
        self.assertEqual(
            {service_id for service_id, route in service_config.REQUIREMENT_DIRECTORY.items() if route["source"] == "immutable extract"},
            immutable,
        )
        self.assertTrue(all(route["maximum_validity_seconds"] == (3600 if service_id in immutable else 300) for service_id, route in service_config.REQUIREMENT_DIRECTORY.items()))

    def test_authority_override_is_local_and_singleton_setting_is_ignored(self) -> None:
        os.environ["SOLMARA_CRA_EVIDENCE_URL"] = "http://cra-evidence:8080"
        os.environ["SOLMARA_EVIDENCE_URL"] = "https://must-not-be-used.example"
        self.assertEqual(service_config.service_url("cra-citizen"), "http://cra-evidence:8080/v1/evidence")
        self.assertEqual(service_config.service_url("nia-citizen"), "https://nia-evidence.solmara.registrystack.org/v1/evidence")

    def test_private_key_jwt_and_mint_token_request(self) -> None:
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import ec, utils
        except ModuleNotFoundError:
            self.skipTest("cryptography is not installed")

        private_key = ec.generate_private_key(ec.SECP256R1())
        numbers = private_key.private_numbers()
        public = numbers.public_numbers
        jwk = {
            "kty": "EC", "crv": "P-256", "alg": "ES256",
            "kid": "A" * 43,
            "x": common.b64url_nopad(public.x.to_bytes(32, "big")),
            "y": common.b64url_nopad(public.y.to_bytes(32, "big")),
            "d": common.b64url_nopad(numbers.private_value.to_bytes(32, "big")),
        }
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
        self.assertEqual(header, {"alg": "ES256", "typ": "JWT", "kid": "A" * 43})
        self.assertEqual(claims["iss"], "solmara-scenario-runner")
        self.assertEqual(claims["sub"], "solmara-scenario-runner")
        self.assertEqual(
            claims["aud"], "https://mint.evidence.solmara.invalid/token"
        )
        self.assertEqual(claims["exp"] - claims["iat"], 120)
        signature = b64url_decode(signature_segment)
        self.assertEqual(len(signature), 64)
        der_signature = utils.encode_dss_signature(
            int.from_bytes(signature[:32], "big"),
            int.from_bytes(signature[32:], "big"),
        )
        private_key.public_key().verify(
            der_signature,
            f"{header_segment}.{claims_segment}".encode(),
            ec.ECDSA(hashes.SHA256()),
        )

    def test_invalid_private_key_fails_closed_before_mint_request(self) -> None:
        original = urllib.request.urlopen

        def fail_if_called(*_args, **_kwargs):
            raise AssertionError("Mint must not be called with an invalid assertion key")

        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "client.jwk"
            key_path.write_text('{"kty":"EC","crv":"P-256","alg":"ES256","kid":"invalid"}')
            os.environ.update(
                SOLMARA_MINT_URL="https://localhost:4341",
                SOLMARA_EVIDENCE_CLIENT_ID="solmara-scenario-runner",
                SOLMARA_EVIDENCE_CLIENT_KEY=str(key_path),
            )
            urllib.request.urlopen = fail_if_called
            try:
                self.assertEqual(common.evidence_access_token(), "")
            finally:
                urllib.request.urlopen = original


class EvidenceScenarioTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["SOLMARA_EVIDENCE_ACCESS_TOKEN"] = "runtime-token"
        install_authority_keys()

    def tearDown(self) -> None:
        os.environ.pop("SOLMARA_EVIDENCE_ACCESS_TOKEN", None)
        common._JWKS_CACHE.clear()

    def test_pension_combines_two_signed_requirements_in_the_application(self) -> None:
        calls: list[dict[str, Any]] = []
        original = pension_survivor.http_json

        def fake_http_json(method, url, headers, body=None, timeout=8.0):
            calls.append(body)
            requirement = body["requirement"]
            service_id = "cra-pension" if "cra-pension-death" in requirement else "sipf-pension"
            concept = "person-is-deceased" if service_id == "cra-pension" else "pension-payment-active"
            return StepHttpResult(200, signed_evidence(service_id, body, [(concept, True)]), {"content-type": common.EVIDENCE_JWS_MEDIA_TYPE})

        pension_survivor.http_json = fake_http_json
        try:
            result = pension_survivor.run_step({}, "stop-payment")
        finally:
            pension_survivor.http_json = original
        self.assertEqual(len(calls), 2)
        self.assertTrue(result["derived_decisions"]["pension-payment-should-stop"])
        self.assertEqual({trace["service_id"] for trace in result["source_trace"]}, {"cra-evidence", "sipf-evidence"})
        self.assertEqual(result["response_source"], {"status": 200, "code": "ok"})

    def test_citizen_requests_cra_and_nia_requirements(self) -> None:
        calls: list[str] = []
        original = citizen.http_json

        def fake_http_json(method, url, headers, body=None, timeout=8.0):
            calls.append(body["requirement"])
            service_id = "cra-citizen" if "cra-citizen" in body["requirement"] else "nia-citizen"
            concept = "civil-record-linked" if service_id == "cra-citizen" else "citizen-population-record-active"
            return StepHttpResult(200, signed_evidence(service_id, body, [(concept, True)]), {"content-type": common.EVIDENCE_JWS_MEDIA_TYPE})

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

    def setUp(self) -> None:
        os.environ["SOLMARA_EVIDENCE_ACCESS_TOKEN"] = "runtime-token"
        install_authority_keys()

    def tearDown(self) -> None:
        os.environ.pop("SOLMARA_EVIDENCE_ACCESS_TOKEN", None)
        common._JWKS_CACHE.clear()

    def request(self, path: str, *, token: str = "collector-token", body: dict[str, Any] | None = None):
        headers = {"x-api-key": token}
        data = None
        method = "GET"
        if body is not None:
            headers.update({"Content-Type": "application/json"})
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
        raised.exception.close()

    def test_rejects_duplicate_or_unknown_concepts_before_evidence(self) -> None:
        base = {"purpose": common.PURPOSES["child_benefit"], "target": {"identifiers": [{"scheme": "solmara_uin", "value": "2300010248"}]}}
        for claims in (["birth-is-registered", "birth-is-registered"], ["not-a-concept"]):
            with self.subTest(claims=claims), self.assertRaises(urllib.error.HTTPError) as raised:
                self.request("/v1/evaluations", body={**base, "claims": claims})
            self.assertEqual(raised.exception.code, 400)
            raised.exception.close()

    def test_composes_only_four_independently_verified_assertions(self) -> None:
        original = child_benefit_federator.http_json

        def fake_http_json(method, url, headers, body=None, timeout=8.0):
            config = service_config.config_for_requirement(body["requirement"])
            values = [(concept, True) for concept in config["concepts"]]
            return StepHttpResult(200, signed_evidence(config["service_id"], body, values), {"content-type": common.EVIDENCE_JWS_MEDIA_TYPE})

        child_benefit_federator.http_json = fake_http_json
        try:
            body = {
                "purpose": common.PURPOSES["child_benefit"],
                "target": {"identifiers": [{"scheme": "solmara_uin", "value": "2300010248"}]},
                "claims": child_benefit.CLAIMS,
            }
            with self.request("/v1/evaluations", body=body) as response:
                payload = json.loads(response.read())
        finally:
            child_benefit_federator.http_json = original
        self.assertEqual(len(payload["signed_evidence"]), 4)
        self.assertEqual({item["presentation"]["source"] for item in payload["results"]}, {"immutable extract", "Relay lookup"})
        self.assertEqual({item["service_id"] for item in payload["source_trace"]}, {"cra-evidence", "nia-evidence", "sro-evidence", "mosd-programme-evidence"})
        self.assertNotIn("requirement", json.dumps(payload["source_trace"]))

    def test_purpose_comes_from_json_body_not_header(self) -> None:
        body = {
            "purpose": "unsupported-purpose",
            "target": {"identifiers": [{"scheme": "solmara_uin", "value": "2300010248"}]},
            "claims": child_benefit.CLAIMS,
        }
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request("/v1/evaluations", body=body)
        self.assertEqual(raised.exception.code, 403)
        raised.exception.close()


if __name__ == "__main__":
    unittest.main()
