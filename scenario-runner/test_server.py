#!/usr/bin/env python3
"""Contract tests for the scenario-runner API."""

from __future__ import annotations

import base64
import hashlib
import json
import os
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

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402
from server import ScenarioRunnerHandler  # noqa: E402
from scenarios import child_benefit, citizen, common, farmer_voucher, pension_survivor  # noqa: E402
from scenarios.common import StepHttpResult  # noqa: E402


def b64url_decode(segment: str) -> bytes:
    padded = segment + "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(padded)


class ScenarioRunnerServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["SCENARIO_RUNNER_HOST"] = "127.0.0.1"
        for name in (
            "CHILD_BENEFIT_NOTARY_TOKEN",
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

    def test_child_benefit_denial_step_ignores_override(self) -> None:
        payload = self.post_json(
            "/v1/scenarios/birth-to-child-benefit/steps/purpose-denial/run",
            {"config": {"purpose_override": "https://id.registrystack.org/solmara/purpose/child-benefit-review"}},
        )
        self.assertEqual(
            payload["result"]["request_source"]["headers"]["Data-Purpose"],
            "https://id.registrystack.org/solmara/purpose/unsupported-demo-purpose",
        )

    def test_child_benefit_positive_attempts_real_credential_endpoint(self) -> None:
        calls: list[str] = []
        original_http_json = child_benefit.http_json
        original_common_http_json = common.http_json
        os.environ["CHILD_BENEFIT_NOTARY_TOKEN"] = "runtime-token"

        def fake_http_json(method: str, url: str, headers: dict, body: dict | None = None, timeout: float = 8.0) -> StepHttpResult:
            calls.append(url)
            if url.endswith("/v1/evaluations"):
                return StepHttpResult(
                    200,
                    {"results": [{"evaluation_id": "eval-123", "claim_id": "birth-is-registered", "satisfied": True}]},
                    {"content-type": "application/json"},
                )
            return StepHttpResult(
                400,
                {"code": "credential.holder_proof_required", "title": "Holder proof required"},
                {"content-type": "application/problem+json"},
            )

        try:
            child_benefit.http_json = fake_http_json
            common.http_json = fake_http_json
            result = child_benefit.run_step({}, "positive")
        finally:
            child_benefit.http_json = original_http_json
            common.http_json = original_common_http_json
            os.environ.pop("CHILD_BENEFIT_NOTARY_TOKEN", None)

        self.assertTrue(any(call.endswith("/v1/credentials") for call in calls))
        self.assertEqual(result["request_source"]["body"]["format"], "application/dc+sd-jwt")
        self.assertEqual(result["credential"]["status"], "not_issued")
        self.assertEqual(result["credential"]["reason"], "credential.holder_proof_required")

    def test_child_benefit_positive_credential_request_carries_holder_proof(self) -> None:
        os.environ["CHILD_BENEFIT_NOTARY_TOKEN"] = "runtime-token"

        def fake_http_json(method: str, url: str, headers: dict, body: dict | None = None, timeout: float = 8.0) -> StepHttpResult:
            if url.endswith("/v1/evaluations"):
                return StepHttpResult(
                    200,
                    {"results": [{"evaluation_id": "eval-123", "claim_id": "birth-is-registered", "satisfied": True}]},
                    {"content-type": "application/json"},
                )
            return StepHttpResult(400, {"code": "credential.holder_proof_required"}, {"content-type": "application/problem+json"})

        original_http_json = child_benefit.http_json
        original_common_http_json = common.http_json
        try:
            child_benefit.http_json = fake_http_json
            common.http_json = fake_http_json
            result = child_benefit.run_step({}, "positive")
        finally:
            child_benefit.http_json = original_http_json
            common.http_json = original_common_http_json
            os.environ.pop("CHILD_BENEFIT_NOTARY_TOKEN", None)

        credential_body = result["credential_source"]["body"]
        self.assertEqual(credential_body["holder"]["binding"], "did")
        self.assertTrue(credential_body["holder"]["id"].startswith("did:jwk:"))
        self.assertEqual(len(credential_body["holder"]["proof"].split(".")), 3)

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
