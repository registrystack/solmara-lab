#!/usr/bin/env python3
"""Contract tests for the scenario-runner API."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scenario-runner"))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402
import child_benefit_federator  # noqa: E402
from server import ScenarioRunnerHandler  # noqa: E402
from scenarios import child_benefit, citizen, common, farmer_voucher, pension_survivor  # noqa: E402
from scenarios.common import StepHttpResult  # noqa: E402


def b64url_decode(segment: str) -> bytes:
    padded = segment + "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(padded)


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class ScenarioRunnerServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["SCENARIO_RUNNER_HOST"] = "127.0.0.1"
        for name in (
            "CHILD_BENEFIT_FEDERATOR_TOKEN",
            "PENSION_NOTARY_TOKEN",
            "NAGDI_NOTARY_TOKEN",
            "PORTAL_CITIZEN_NOTARY_TOKEN",
        ):
            os.environ.pop(name, None)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ScenarioRunnerHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()

    def test_lists_scenarios_with_default(self) -> None:
        payload = self.fetch_json("/v1/scenarios")
        self.assertEqual(payload["default_scenario_id"], "birth-to-child-benefit")
        self.assertGreaterEqual(len(payload["scenarios"]), 3)
        self.assertTrue(all(item["runnable"] for item in payload["scenarios"]))

    def test_detail_contains_request_previews(self) -> None:
        payload = self.fetch_json("/v1/scenarios/birth-to-child-benefit")
        steps = payload["story"]["steps"]
        self.assertTrue(steps)
        self.assertIn("request_preview", steps[0])
        self.assertIn("Data-Purpose", steps[0]["request_preview"]["headers"])

    def test_run_step_is_idempotent_when_runtime_token_missing(self) -> None:
        first = self.post_json("/v1/scenarios/birth-to-child-benefit/steps/positive/run", {})
        second = self.post_json("/v1/scenarios/birth-to-child-benefit/steps/positive/run", {})
        self.assertEqual(first["result"]["friendly"]["status"], "needs_attention")
        self.assertEqual(first["result"]["response_source"], second["result"]["response_source"])

    def test_child_benefit_purpose_override_reaches_request_source(self) -> None:
        purpose = "https://id.registrystack.org/solmara/purpose/survivor-benefit-determination"
        payload = self.post_json(
            "/v1/scenarios/birth-to-child-benefit/steps/positive/run",
            {"config": {"purpose_override": purpose}},
        )
        self.assertEqual(payload["result"]["request_source"]["headers"]["Data-Purpose"], purpose)
        self.assertEqual(payload["result"]["request_source"]["headers"]["Content-Type"], "application/json")

    def test_child_benefit_denial_step_ignores_override(self) -> None:
        payload = self.post_json(
            "/v1/scenarios/birth-to-child-benefit/steps/purpose-denial/run",
            {"config": {"purpose_override": "https://id.registrystack.org/solmara/purpose/child-benefit-review"}},
        )
        self.assertEqual(
            payload["result"]["request_source"]["headers"]["Data-Purpose"],
            "https://id.registrystack.org/solmara/purpose/unsupported-demo-purpose",
        )

    def test_child_benefit_positive_calls_federator_without_credential_composition(self) -> None:
        calls: list[str] = []
        original_http_json = child_benefit.http_json
        os.environ["CHILD_BENEFIT_FEDERATOR_TOKEN"] = "runtime-token"

        def fake_http_json(method: str, url: str, headers: dict, body: dict | None = None, timeout: float = 8.0) -> StepHttpResult:
            calls.append(url)
            return StepHttpResult(
                200,
                {
                    "federator": {"service_id": "child-benefit-federator", "decision": "not_composed"},
                    "results": [
                        {"claim_id": "birth-is-registered", "satisfied": True},
                        {"claim_id": "population-record-active", "satisfied": True},
                    ],
                    "federation_trace": [{"authority": "Civil Registration Authority", "claim_id": "birth-is-registered"}],
                },
                {"content-type": "application/json"},
            )

        try:
            child_benefit.http_json = fake_http_json
            result = child_benefit.run_step({}, "positive")
        finally:
            child_benefit.http_json = original_http_json
            os.environ.pop("CHILD_BENEFIT_FEDERATOR_TOKEN", None)

        self.assertTrue(all(call.endswith("/v1/evaluations") for call in calls))
        self.assertNotIn("credential", result)
        self.assertEqual(
            result["request_source"]["body"]["format"],
            "application/vnd.solmara.federated-predicate-bundle+json",
        )
        self.assertIn("population-record-active", result["request_source"]["body"]["claims"])
        self.assertEqual(result["federation_trace"][0]["authority"], "Civil Registration Authority")

    def test_pension_survivor_purpose_override_reaches_request_source(self) -> None:
        purpose = "https://id.registrystack.org/solmara/purpose/voucher-eligibility-review"
        payload = self.post_json(
            "/v1/scenarios/death-to-pension-survivor/steps/stop-payment/run",
            {"config": {"purpose_override": purpose}},
        )
        self.assertEqual(payload["result"]["request_source"]["headers"]["Data-Purpose"], purpose)

    def test_farmer_voucher_purpose_override_reaches_request_source(self) -> None:
        purpose = "https://id.registrystack.org/solmara/purpose/citizen-self-service"
        payload = self.post_json(
            "/v1/scenarios/farmer-climate-smart-voucher/steps/positive/run",
            {"config": {"purpose_override": purpose}},
        )
        self.assertEqual(payload["result"]["request_source"]["headers"]["Data-Purpose"], purpose)

    def test_farmer_voucher_denial_step_ignores_override(self) -> None:
        payload = self.post_json(
            "/v1/scenarios/farmer-climate-smart-voucher/steps/purpose-denial/run",
            {"config": {"purpose_override": "https://id.registrystack.org/solmara/purpose/livestock-movement-control"}},
        )
        self.assertEqual(
            payload["result"]["request_source"]["headers"]["Data-Purpose"],
            "https://id.registrystack.org/solmara/purpose/voucher-eligibility-review",
        )

    def test_citizen_purpose_override_reaches_request_source(self) -> None:
        purpose = "https://id.registrystack.org/solmara/purpose/pension-payment-review"
        payload = self.post_json(
            "/v1/scenarios/citizen-self-service/steps/positive/run",
            {"config": {"purpose_override": purpose}},
        )
        self.assertEqual(payload["result"]["request_source"]["headers"]["Data-Purpose"], purpose)

    def test_citizen_denial_step_ignores_override(self) -> None:
        payload = self.post_json(
            "/v1/scenarios/citizen-self-service/steps/purpose-denial/run",
            {"config": {"purpose_override": "https://id.registrystack.org/solmara/purpose/citizen-self-service"}},
        )
        self.assertEqual(
            payload["result"]["request_source"]["headers"]["Data-Purpose"],
            "https://id.registrystack.org/solmara/purpose/unsupported-demo-purpose",
        )

    def test_unknown_scenario_returns_404(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.fetch_json("/v1/scenarios/not-a-story")
        self.assertEqual(raised.exception.code, 404)
        raised.exception.close()

    def fetch_json(self, path: str) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_json(self, path: str, body: dict) -> dict:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))


class HolderProofTest(unittest.TestCase):
    """Unit coverage for the did:jwk holder key-binding proof used at credential issuance."""

    def test_holder_keypair_produces_a_valid_did_jwk(self) -> None:
        keypair = common.holder_keypair()
        self.assertTrue(keypair.holder_id.startswith("did:jwk:"))
        jwk = json.loads(b64url_decode(keypair.holder_id.removeprefix("did:jwk:")))
        self.assertEqual(jwk["kty"], "OKP")
        self.assertEqual(jwk["crv"], "Ed25519")
        public_bytes = keypair.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.assertEqual(jwk["x"], common.b64url_nopad(public_bytes))

    def test_holder_proof_header_and_payload_bindings(self) -> None:
        keypair = common.holder_keypair()
        claim_ids = ["birth-is-registered", "child-age-under-5"]
        proof = common.holder_proof(
            keypair,
            audience="child-benefit-notary",
            evaluation_id="eval-123",
            credential_profile="child_benefit_eligibility_sd_jwt",
            disclosure="predicate",
            claim_ids=claim_ids,
        )
        header_b64, payload_b64, signature_b64 = proof.split(".")
        header = json.loads(b64url_decode(header_b64))
        payload = json.loads(b64url_decode(payload_b64))

        self.assertEqual(header, {"alg": "EdDSA", "typ": "kb+jwt", "kid": keypair.holder_id})
        self.assertEqual(payload["sub"], keypair.holder_id)
        self.assertEqual(payload["aud"], "child-benefit-notary")
        self.assertEqual(payload["evaluation_id"], "eval-123")
        self.assertEqual(payload["credential_profile"], "child_benefit_eligibility_sd_jwt")
        self.assertEqual(payload["claims"], claim_ids)
        self.assertEqual(payload["disclosure"], common.b64url_nopad(hashlib.sha256(b"predicate").digest()))
        self.assertLessEqual(payload["iat"], int(time.time()))
        self.assertEqual(payload["exp"] - payload["iat"], 60)
        self.assertTrue(payload["jti"])

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        signature = b64url_decode(signature_b64)
        # Raises cryptography.exceptions.InvalidSignature if the proof does not verify.
        keypair.private_key.public_key().verify(signature, signing_input)

    def test_holder_proof_jti_is_unique_per_call(self) -> None:
        keypair = common.holder_keypair()
        kwargs = {"audience": "a", "evaluation_id": "e", "credential_profile": "p", "disclosure": "predicate", "claim_ids": ["x"]}
        first = common.holder_proof(keypair, **kwargs)
        second = common.holder_proof(keypair, **kwargs)
        first_jti = json.loads(b64url_decode(first.split(".")[1]))["jti"]
        second_jti = json.loads(b64url_decode(second.split(".")[1]))["jti"]
        self.assertNotEqual(first_jti, second_jti)

    def test_credential_attempt_includes_holder_binding_and_matching_claims(self) -> None:
        claim_ids = ["survivor-is-eligible"]
        evaluation_result = StepHttpResult(200, {"results": [{"evaluation_id": "eval-999"}]}, {})
        captured: dict[str, Any] = {}

        def fake_http_json(method, url, headers, body=None, timeout=8.0):
            captured["method"], captured["url"], captured["headers"], captured["body"] = method, url, headers, body
            return StepHttpResult(400, {"code": "credential.holder_proof_required"}, {})

        original = common.http_json
        common.http_json = fake_http_json
        try:
            result = common.credential_attempt(
                "http://example.invalid/v1/credentials",
                "runtime-token",
                "https://id.registrystack.org/solmara/purpose/survivor-benefit-determination",
                evaluation_result,
                "survivor_benefit_sd_jwt",
                claim_ids,
                "pension-notary",
            )
        finally:
            common.http_json = original

        body = result["credential_source"]["body"]
        self.assertEqual(body["claims"], claim_ids)
        self.assertEqual(body["holder"]["binding"], "did")
        self.assertTrue(body["holder"]["id"].startswith("did:jwk:"))
        proof_payload = json.loads(b64url_decode(body["holder"]["proof"].split(".")[1]))
        self.assertEqual(proof_payload["aud"], "pension-notary")
        self.assertEqual(proof_payload["claims"], claim_ids)

        # request_source redaction is unaffected by the new holder object.
        self.assertEqual(result["credential_source"]["headers"]["x-api-key"], "[runtime token hidden]")
        # And the outgoing body actually carried the same holder object (nothing lost in transit).
        self.assertEqual(captured["body"]["holder"], body["holder"])


class ChildBenefitFederatorTest(unittest.TestCase):
    def test_catalog_lists_source_owned_predicates_without_eligibility_composition(self) -> None:
        catalog = child_benefit_federator.claim_catalog()
        ids = {entry["id"] for entry in catalog["claims"]}

        self.assertIn("birth-is-registered", ids)
        self.assertIn("population-record-active", ids)
        self.assertIn("household-below-poverty-threshold", ids)
        self.assertNotIn("eligible-for-child-benefit", ids)
        self.assertEqual(catalog["bundle_media_type"], common.FEDERATED_BUNDLE_FORMAT)
        self.assertEqual(catalog["composition"]["eligible-for-child-benefit"], "not_returned_by_federator")
        self.assertEqual(catalog["data"], catalog["claims"])

    def test_federation_payload_targets_the_source_notary_profile(self) -> None:
        route = child_benefit_federator.CLAIM_ROUTES["population-record-active"]
        payload = child_benefit_federator.federation_payload(
            route,
            "2300010248",
            common.PURPOSES["child_benefit"],
            "01J9Z6Q6Q6Q6Q6Q6Q6Q6Q6Q6S0",
        )

        self.assertEqual(payload["iss"], child_benefit_federator.FEDERATOR_ISSUER)
        self.assertEqual(payload["sub"], child_benefit_federator.FEDERATOR_NODE_ID)
        self.assertEqual(payload["aud"], route["node_id"])
        self.assertEqual(payload["profile"], "population_record_active")
        self.assertEqual(payload["request"]["subject"], {"id": "2300010248", "id_type": "solmara_uin"})
        self.assertEqual(payload["request"]["claims"], ["population-record-active"])

    def test_peer_response_must_verify_before_federator_accepts_it(self) -> None:
        route = child_benefit_federator.CLAIM_ROUTES["birth-is-registered"]
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        kid = f'{route["node_id"]}#test-key'
        request_jti = "01J9Z6Q6Q6Q6Q6Q6Q6Q6Q6Q6S1"
        now = int(time.time())
        payload = {
            "iss": route["issuer"],
            "sub": route["node_id"],
            "aud": child_benefit_federator.FEDERATOR_NODE_ID,
            "iat": now,
            "nbf": now,
            "exp": now + 300,
            "jti": "01J9Z6Q6Q6Q6Q6Q6Q6Q6Q6Q6S2",
            "request_jti": request_jti,
            "protocol": child_benefit_federator.FEDERATION_PROTOCOL,
            "action": "evaluate",
            "profile": route["profile"],
            "result": {"claims": {"birth-is-registered": {"satisfied": True, "disclosure": "predicate", "value": True}}},
        }
        header = {"alg": "EdDSA", "typ": child_benefit_federator.FEDERATION_RESPONSE_TYP, "kid": kid}
        signing_input = (
            f"{b64url_encode(json.dumps(header, separators=(',', ':'), sort_keys=True).encode())}."
            f"{b64url_encode(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode())}"
        )
        token = f"{signing_input}.{b64url_encode(private_key.sign(signing_input.encode('ascii')))}"
        original_jwk_for_kid = child_benefit_federator.jwk_for_kid
        child_benefit_federator.jwk_for_kid = lambda _route, _kid: {
            "kid": kid,
            "kty": "OKP",
            "crv": "Ed25519",
            "x": b64url_encode(public_key),
        }

        try:
            verified = child_benefit_federator.verify_peer_response(route, request_jti, token, "application/jwt")
            rejected = child_benefit_federator.verify_peer_response(route, request_jti, f"{signing_input}.AA", "application/jwt")
        finally:
            child_benefit_federator.jwk_for_kid = original_jwk_for_kid

        self.assertEqual(verified["request_jti"], request_jti)
        self.assertEqual(verified["result"]["claims"]["birth-is-registered"]["satisfied"], True)
        self.assertEqual(rejected["error"]["code"], "bad_response_signature")

    def test_public_trace_allowlists_verified_response_fields(self) -> None:
        route = child_benefit_federator.CLAIM_ROUTES["birth-is-registered"]
        peer = {
            "iss": route["issuer"],
            "sub": route["node_id"],
            "aud": child_benefit_federator.FEDERATOR_NODE_ID,
            "iat": 1,
            "nbf": 1,
            "exp": 2,
            "jti": "01J9Z6Q6Q6Q6Q6Q6Q6Q6Q6Q6S2",
            "request_jti": "01J9Z6Q6Q6Q6Q6Q6Q6Q6Q6Q6S1",
            "protocol": child_benefit_federator.FEDERATION_PROTOCOL,
            "action": "evaluate",
            "profile": route["profile"],
            "subject_ref": "stable-pairwise-subject-ref",
            "evaluation_id": "authority-internal-evaluation-id",
            "source_observed_at": "2026-07-14T00:00:00Z",
            "future_peer_field": {"raw_household_score": 42},
            "result": {
                "claims": {
                    "birth-is-registered": {
                        "satisfied": True,
                        "disclosure": "predicate",
                        "value": True,
                        "source_row": {"birth_brn": "BRN-SECRET"},
                    }
                }
            },
        }

        summary = child_benefit_federator.verified_response_summary(route, peer)
        serialized = json.dumps(summary, sort_keys=True)

        self.assertTrue(summary["signature_verified"])
        self.assertEqual(summary["claim"]["satisfied"], True)
        for forbidden in (
            "stable-pairwise-subject-ref",
            "authority-internal-evaluation-id",
            "source_observed_at",
            "future_peer_field",
            "raw_household_score",
            "BRN-SECRET",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_peer_response_requires_bounded_temporal_claims_and_jti(self) -> None:
        route = child_benefit_federator.CLAIM_ROUTES["birth-is-registered"]
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        kid = f'{route["node_id"]}#test-key'
        request_jti = "01J9Z6Q6Q6Q6Q6Q6Q6Q6Q6Q6S1"
        now = int(time.time())
        base_payload = {
            "iss": route["issuer"],
            "sub": route["node_id"],
            "aud": child_benefit_federator.FEDERATOR_NODE_ID,
            "iat": now,
            "nbf": now,
            "exp": now + child_benefit_federator.MAX_RESPONSE_LIFETIME_SECONDS,
            "jti": "01J9Z6Q6Q6Q6Q6Q6Q6Q6Q6Q6S2",
            "request_jti": request_jti,
            "protocol": child_benefit_federator.FEDERATION_PROTOCOL,
            "action": "evaluate",
            "profile": route["profile"],
            "result": {"claims": {"birth-is-registered": {"satisfied": True, "disclosure": "predicate"}}},
        }

        def sign(payload: dict[str, Any]) -> str:
            header = {"alg": "EdDSA", "typ": child_benefit_federator.FEDERATION_RESPONSE_TYP, "kid": kid}
            signing_input = (
                f"{b64url_encode(json.dumps(header, separators=(',', ':'), sort_keys=True).encode())}."
                f"{b64url_encode(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode())}"
            )
            return f"{signing_input}.{b64url_encode(private_key.sign(signing_input.encode('ascii')))}"

        original_jwk_for_kid = child_benefit_federator.jwk_for_kid
        child_benefit_federator.jwk_for_kid = lambda _route, _kid: {
            "kid": kid,
            "kty": "OKP",
            "crv": "Ed25519",
            "x": b64url_encode(public_key),
        }
        try:
            for claim in ("iat", "nbf", "exp", "jti"):
                payload = dict(base_payload)
                payload.pop(claim)
                rejected = child_benefit_federator.verify_peer_response(
                    route, request_jti, sign(payload), "application/jwt"
                )
                self.assertIsNotNone(child_benefit_federator.verification_error_code(rejected), claim)

            overlong = dict(base_payload, exp=now + child_benefit_federator.MAX_RESPONSE_LIFETIME_SECONDS + 1)
            rejected = child_benefit_federator.verify_peer_response(
                route, request_jti, sign(overlong), "application/jwt"
            )
        finally:
            child_benefit_federator.jwk_for_kid = original_jwk_for_kid

        self.assertEqual(child_benefit_federator.verification_error_code(rejected), "invalid_response_lifetime")

    def test_unsigned_or_failed_peer_response_is_not_a_false_predicate(self) -> None:
        route = child_benefit_federator.CLAIM_ROUTES["birth-is-registered"]
        original_post_jwt = child_benefit_federator.post_jwt
        original_sign_jwt = child_benefit_federator.sign_jwt
        child_benefit_federator.sign_jwt = lambda _payload: "signed-request"
        try:
            child_benefit_federator.post_jwt = lambda _url, _token: (
                200,
                {"content-type": "application/json"},
                {"result": {"claims": {"birth-is-registered": {"satisfied": False, "disclosure": "predicate"}}}},
            )
            with self.assertRaises(child_benefit_federator.FederationUpstreamError) as unsigned:
                child_benefit_federator.call_peer_notary(route, "2300010248", common.PURPOSES["child_benefit"])

            child_benefit_federator.post_jwt = lambda _url, _token: (503, {"content-type": "application/json"}, {})
            with self.assertRaises(child_benefit_federator.FederationUpstreamError) as unavailable:
                child_benefit_federator.call_peer_notary(route, "2300010248", common.PURPOSES["child_benefit"])
        finally:
            child_benefit_federator.post_jwt = original_post_jwt
            child_benefit_federator.sign_jwt = original_sign_jwt

        self.assertEqual(unsigned.exception.code, "unsigned_peer_response")
        self.assertEqual(unavailable.exception.status, 503)

    def test_request_body_has_a_hard_size_limit(self) -> None:
        handler = object.__new__(child_benefit_federator.ChildBenefitFederatorHandler)
        handler.headers = {"Content-Length": str(child_benefit_federator.MAX_REQUEST_BODY_BYTES + 1)}
        handler.rfile = io.BytesIO(b"")

        with self.assertRaises(child_benefit_federator.RequestBodyError) as rejected:
            handler.read_body()

        self.assertEqual(rejected.exception.status, 413)

    def test_federator_key_must_match_the_configured_public_domain(self) -> None:
        env_name = child_benefit_federator.FEDERATOR_JWK_ENV
        original = os.environ.get(env_name)
        os.environ[env_name] = json.dumps(
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": "did:web:child-benefit-federator.wrong.example#request-key-1",
                "x": "AA",
                "d": "AA",
            }
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "CHILD_BENEFIT_PUBLIC_DOMAIN"):
                child_benefit_federator.private_jwk()
        finally:
            if original is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = original

    def test_duplicate_claims_are_rejected_before_federation(self) -> None:
        token = "test-federator-token"
        os.environ[child_benefit_federator.FEDERATOR_TOKEN_ENV] = token
        server = ThreadingHTTPServer(("127.0.0.1", 0), child_benefit_federator.ChildBenefitFederatorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        body = {
            "target": {"identifiers": [{"scheme": "solmara_uin", "value": "2300010248"}]},
            "claims": ["birth-is-registered", "birth-is-registered"],
            "disclosure": "predicate",
            "format": common.FEDERATED_BUNDLE_FORMAT,
        }
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/v1/evaluations",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-api-key": token,
                "Data-Purpose": common.PURPOSES["child_benefit"],
                "Content-Type": "application/json",
                "Accept": common.FEDERATED_BUNDLE_FORMAT,
            },
            method="POST",
        )
        try:
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(request, timeout=5)
            payload = json.loads(rejected.exception.read().decode("utf-8"))
            rejected.exception.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
            os.environ.pop(child_benefit_federator.FEDERATOR_TOKEN_ENV, None)

        self.assertEqual(rejected.exception.code, 400)
        self.assertEqual(payload["code"], "request.invalid")

    def test_raw_household_request_is_denied_as_problem_details(self) -> None:
        token = "test-federator-token"
        os.environ[child_benefit_federator.FEDERATOR_TOKEN_ENV] = token
        server = ThreadingHTTPServer(("127.0.0.1", 0), child_benefit_federator.ChildBenefitFederatorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        body = {
            "target": {"identifiers": [{"scheme": "solmara_uin", "value": "2300010248"}]},
            "claims": ["household-poverty-score"],
            "disclosure": "value",
            "format": common.FEDERATED_BUNDLE_FORMAT,
        }
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/v1/evaluations",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-api-key": token,
                "Data-Purpose": common.PURPOSES["child_benefit"],
                "Content-Type": "application/json",
                "Accept": common.FEDERATED_BUNDLE_FORMAT,
            },
            method="POST",
        )
        try:
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(request, timeout=5)
            content_type = rejected.exception.headers.get_content_type()
            payload = json.loads(rejected.exception.read().decode("utf-8"))
            rejected.exception.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
            os.environ.pop(child_benefit_federator.FEDERATOR_TOKEN_ENV, None)

        self.assertEqual(rejected.exception.code, 403)
        self.assertEqual(content_type, "application/problem+json")
        self.assertEqual(payload["code"], "pdp.purpose_not_permitted")
        self.assertNotIn("household-poverty-score", json.dumps(payload))

    def test_success_response_uses_the_bundle_media_type(self) -> None:
        token = "test-federator-token"
        os.environ[child_benefit_federator.FEDERATOR_TOKEN_ENV] = token
        original_evaluate_bundle = child_benefit_federator.evaluate_bundle
        child_benefit_federator.evaluate_bundle = lambda *_args: {
            "schema_version": child_benefit_federator.API_VERSION,
            "results": [],
            "federation_trace": [],
        }
        server = ThreadingHTTPServer(("127.0.0.1", 0), child_benefit_federator.ChildBenefitFederatorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        body = {
            "target": {"identifiers": [{"scheme": "solmara_uin", "value": "2300010248"}]},
            "claims": ["birth-is-registered"],
            "disclosure": "predicate",
            "format": common.FEDERATED_BUNDLE_FORMAT,
        }
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/v1/evaluations",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-api-key": token,
                "Data-Purpose": common.PURPOSES["child_benefit"],
                "Content-Type": "application/json",
                "Accept": common.FEDERATED_BUNDLE_FORMAT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get_content_type(), common.FEDERATED_BUNDLE_FORMAT)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
            child_benefit_federator.evaluate_bundle = original_evaluate_bundle
            os.environ.pop(child_benefit_federator.FEDERATOR_TOKEN_ENV, None)


class StdlibOnlyImportTest(unittest.TestCase):
    def test_scenarios_import_without_cryptography(self) -> None:
        """Preview-only consumers (scripts/smoke-story-previews.py) run under the
        system Python, so importing the scenario modules must not require the
        cryptography package; only actually signing a holder proof may."""
        code = (
            "import builtins\n"
            "real_import = builtins.__import__\n"
            "def guard(name, *args, **kwargs):\n"
            "    if name.split('.')[0] == 'cryptography':\n"
            "        raise ModuleNotFoundError(name)\n"
            "    return real_import(name, *args, **kwargs)\n"
            "builtins.__import__ = guard\n"
            "import scenarios.common\n"
            "import scenarios.child_benefit\n"
        )
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class CredentialSummaryVctTest(unittest.TestCase):
    VCT = "https://id.registrystack.org/solmara/vct/child-benefit-enrollment-eligibility"

    @staticmethod
    def compact_sd_jwt(payload: dict[str, Any]) -> str:
        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        header = b64url(json.dumps({"alg": "EdDSA", "typ": "dc+sd-jwt"}).encode())
        body = b64url(json.dumps(payload).encode())
        return f"{header}.{body}.fake-signature~ZmFrZS1kaXNjbG9zdXJl~"

    def test_issued_summary_extracts_vct_from_sd_jwt_payload(self) -> None:
        body = {
            "credential": self.compact_sd_jwt({"vct": self.VCT, "iss": "did:web:child-benefit-notary"}),
            "credential_profile": "child_benefit_eligibility_sd_jwt",
            "disclosures": ["a", "b"],
        }
        summary = common.credential_summary("profile", "did:jwk:x", StepHttpResult(200, body, {}))
        self.assertEqual(summary["status"], "issued")
        self.assertEqual(summary["vct"], self.VCT)

    def test_issued_summary_without_decodable_credential_has_no_vct(self) -> None:
        body = {"credential": "not-a-jwt", "disclosures": []}
        summary = common.credential_summary("profile", "did:jwk:x", StepHttpResult(200, body, {}))
        self.assertEqual(summary["status"], "issued")
        self.assertIsNone(summary["vct"])

    def test_issued_summary_with_undecodable_payload_has_no_vct(self) -> None:
        body = {"credential": "eyJhbGciOiJFZERTQSJ9.%%%not-base64%%%.sig", "disclosures": []}
        summary = common.credential_summary("profile", "did:jwk:x", StepHttpResult(200, body, {}))
        self.assertEqual(summary["status"], "issued")
        self.assertIsNone(summary["vct"])


class FriendlyResultTest(unittest.TestCase):
    COPY = {
        "positive": {
            "met": ("Yes. Mateo qualifies for review.", "All four facts came back met."),
        },
        "poverty-control": {
            "unmet": ("Rejected: the household is above the threshold.", "The caseworker never sees the income."),
        },
    }

    def test_pdp_denial_reads_as_designed(self) -> None:
        result = StepHttpResult(403, {"code": "pdp.purpose_not_permitted", "detail": "nope"}, {})
        friendly = common.friendly_result("positive", result, self.COPY)
        self.assertEqual(friendly["status"], "done")
        self.assertEqual(friendly["title"], "Refused, exactly as designed.")

    def test_all_claims_met_uses_step_copy(self) -> None:
        body = {"results": [{"claim_id": "a", "satisfied": True}, {"claim_id": "b", "satisfied": True}]}
        friendly = common.friendly_result("positive", StepHttpResult(200, body, {}), self.COPY)
        self.assertEqual(friendly["status"], "done")
        self.assertEqual(friendly["title"], "Yes. Mateo qualifies for review.")
        self.assertIn({"label": "Claims met", "value": "2 of 2"}, friendly["facts"])

    def test_unmet_claim_uses_unmet_copy_and_names_claim(self) -> None:
        body = {"results": [{"claim_id": "household-below-poverty-threshold", "satisfied": False}]}
        friendly = common.friendly_result("poverty-control", StepHttpResult(200, body, {}), self.COPY)
        self.assertEqual(friendly["status"], "done")
        self.assertEqual(friendly["title"], "Rejected: the household is above the threshold.")

    def test_unmet_claim_without_copy_falls_back_to_generic_rejection(self) -> None:
        body = {"results": [{"claim_id": "child-age-under-5", "satisfied": False}]}
        friendly = common.friendly_result("deceased-control", StepHttpResult(200, body, {}), self.COPY)
        self.assertEqual(friendly["status"], "done")
        self.assertEqual(friendly["title"], "Rejected, exactly as designed.")
        self.assertIn("child-age-under-5", friendly["message"])

    def test_refused_copy_frames_intended_denial_as_done(self) -> None:
        copy = {"cause-of-death-denial": {"refused": ("Refused: that question does not exist here.", "No such claim is offered.")}}
        result = StepHttpResult(404, {"code": "claim.not_found", "detail": "the requested claim is not available"}, {})
        friendly = common.friendly_result("cause-of-death-denial", result, copy)
        self.assertEqual(friendly["status"], "done")
        self.assertEqual(friendly["title"], "Refused: that question does not exist here.")

    def test_non_pdp_error_without_refused_copy_needs_attention(self) -> None:
        result = StepHttpResult(404, {"code": "claim.not_found", "detail": "missing"}, {})
        friendly = common.friendly_result("positive", result, self.COPY)
        self.assertEqual(friendly["status"], "needs_attention")

    def test_no_response_needs_attention(self) -> None:
        friendly = common.friendly_result("positive", StepHttpResult(None, {}, {}, "URLError"), self.COPY)
        self.assertEqual(friendly["status"], "needs_attention")

    def test_unexpected_error_status_needs_attention(self) -> None:
        result = StepHttpResult(500, {"detail": "boom"}, {})
        friendly = common.friendly_result("positive", result, self.COPY)
        self.assertEqual(friendly["status"], "needs_attention")
        self.assertIn("boom", friendly["message"])


if __name__ == "__main__":
    unittest.main()
