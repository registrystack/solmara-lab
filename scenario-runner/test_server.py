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

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402
import child_benefit_federator  # noqa: E402
from server import ScenarioRunnerHandler  # noqa: E402
from scenarios import child_benefit, citizen, common, pension_survivor  # noqa: E402
from scenarios.common import StepHttpResult  # noqa: E402


def b64url_decode(segment: str) -> bytes:
    padded = segment + "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(padded)


class ScenarioRunnerServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["SCENARIO_RUNNER_HOST"] = "127.0.0.1"
        for name in (
            "CHILD_BENEFIT_FEDERATOR_TOKEN",
            "CRA_CHILD_BENEFIT_CLIENT_TOKEN",
            "NIA_CHILD_BENEFIT_CLIENT_TOKEN",
            "SRO_CHILD_BENEFIT_CLIENT_TOKEN",
            "PROGRAMME_CHILD_BENEFIT_CLIENT_TOKEN",
            "CRA_PENSION_CLIENT_TOKEN",
            "SIPF_PENSION_CLIENT_TOKEN",
            "NAGDI_NOTARY_TOKEN",
            "CRA_CITIZEN_CLIENT_TOKEN",
            "NIA_CITIZEN_CLIENT_TOKEN",
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
        first = self.post_json(
            "/v1/scenarios/birth-to-child-benefit/steps/positive/run", {}
        )
        second = self.post_json(
            "/v1/scenarios/birth-to-child-benefit/steps/positive/run", {}
        )
        self.assertEqual(first["result"]["friendly"]["status"], "needs_attention")
        self.assertEqual(
            first["result"]["response_source"], second["result"]["response_source"]
        )

    def test_child_benefit_purpose_override_reaches_request_source(self) -> None:
        purpose = "https://id.registrystack.org/solmara/purpose/survivor-benefit-determination"
        payload = self.post_json(
            "/v1/scenarios/birth-to-child-benefit/steps/positive/run",
            {"config": {"purpose_override": purpose}},
        )
        self.assertEqual(
            payload["result"]["request_source"]["headers"]["Data-Purpose"], purpose
        )
        self.assertEqual(
            payload["result"]["request_source"]["headers"]["Content-Type"],
            "application/json",
        )

    def test_child_benefit_denial_step_ignores_override(self) -> None:
        payload = self.post_json(
            "/v1/scenarios/birth-to-child-benefit/steps/purpose-denial/run",
            {
                "config": {
                    "purpose_override": "https://id.registrystack.org/solmara/purpose/child-benefit-review"
                }
            },
        )
        self.assertEqual(
            payload["result"]["request_source"]["headers"]["Data-Purpose"],
            "https://id.registrystack.org/solmara/purpose/unsupported-demo-purpose",
        )

    def test_child_benefit_positive_calls_application_without_credential_composition(
        self,
    ) -> None:
        calls: list[str] = []
        original_http_json = child_benefit.http_json
        os.environ["CHILD_BENEFIT_FEDERATOR_TOKEN"] = "runtime-token"

        def fake_http_json(
            method: str,
            url: str,
            headers: dict,
            body: dict | None = None,
            timeout: float = 8.0,
        ) -> StepHttpResult:
            calls.append(url)
            return StepHttpResult(
                200,
                {
                    "orchestration": {
                        "service_id": "child-benefit-federator",
                        "decision": "not_composed",
                    },
                    "results": [
                        {"claim_id": "birth-is-registered", "satisfied": True},
                        {"claim_id": "population-record-active", "satisfied": True},
                    ],
                    "source_trace": [
                        {
                            "authority": "Civil Registration Authority",
                            "service_id": "cra-notary",
                        }
                    ],
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
            "application/json",
        )
        self.assertIn(
            "population-record-active", result["request_source"]["body"]["claims"]
        )
        self.assertEqual(
            result["source_trace"][0]["authority"], "Civil Registration Authority"
        )

    def test_pension_survivor_purpose_override_reaches_request_source(self) -> None:
        purpose = (
            "https://id.registrystack.org/solmara/purpose/voucher-eligibility-review"
        )
        payload = self.post_json(
            "/v1/scenarios/death-to-pension-survivor/steps/stop-payment/run",
            {"config": {"purpose_override": purpose}},
        )
        self.assertEqual(
            payload["result"]["request_source"]["headers"]["Data-Purpose"], purpose
        )

    def test_pension_stop_calls_cra_and_sipf_and_derives_the_application_decision(
        self,
    ) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []
        original_http_json = pension_survivor.http_json
        for name in ("CRA_PENSION_CLIENT_TOKEN", "SIPF_PENSION_CLIENT_TOKEN"):
            os.environ[name] = f"token-{name.lower()}"

        def fake_http_json(
            method: str,
            url: str,
            headers: dict,
            body: dict | None = None,
            timeout: float = 8.0,
        ) -> StepHttpResult:
            assert body is not None
            calls.append((url, body))
            claim_id = body["claims"][0]
            return StepHttpResult(
                200,
                {
                    "results": [
                        {
                            "evaluation_id": f"eval-{claim_id}",
                            "claim_id": claim_id,
                            "satisfied": True,
                            "disclosure": "predicate",
                        }
                    ]
                },
                {"content-type": common.CLAIM_RESULT_FORMAT},
            )

        try:
            pension_survivor.http_json = fake_http_json
            result = pension_survivor.run_step({}, "stop-payment")
        finally:
            pension_survivor.http_json = original_http_json
            for name in ("CRA_PENSION_CLIENT_TOKEN", "SIPF_PENSION_CLIENT_TOKEN"):
                os.environ.pop(name, None)

        self.assertEqual(
            [body["claims"] for _, body in calls],
            [["person-is-deceased"], ["pension-payment-active"]],
        )
        self.assertTrue(calls[0][0].endswith("/v1/evaluations"))
        self.assertTrue(calls[1][0].endswith("/v1/evaluations"))
        self.assertEqual(
            [trace["service_id"] for trace in result["source_trace"]],
            ["cra-notary", "sipf-notary"],
        )
        self.assertIs(result["derived_decisions"]["pension-payment-should-stop"], True)
        self.assertNotIn(
            "pension-payment-should-stop", [body["claims"][0] for _, body in calls]
        )

    def test_survivor_credential_is_issued_by_sipf(self) -> None:
        original_http_json = pension_survivor.http_json
        original_credential_attempt = pension_survivor.credential_attempt
        os.environ["SIPF_PENSION_CLIENT_TOKEN"] = "sipf-token"
        captured: dict[str, Any] = {}

        def fake_http_json(
            method: str,
            url: str,
            headers: dict,
            body: dict | None = None,
            timeout: float = 8.0,
        ) -> StepHttpResult:
            return StepHttpResult(
                200,
                {
                    "results": [
                        {
                            "evaluation_id": "eval-survivor",
                            "claim_id": "survivor-is-eligible",
                            "satisfied": True,
                            "disclosure": "predicate",
                        }
                    ]
                },
                {"content-type": common.CLAIM_RESULT_FORMAT},
            )

        def fake_credential_attempt(
            url, token, purpose, evaluation_result, profile, claim_ids, service_id
        ):
            captured.update(
                url=url,
                token=token,
                profile=profile,
                claim_ids=claim_ids,
                service_id=service_id,
            )
            return {"credential": {"status": "issued"}}

        try:
            pension_survivor.http_json = fake_http_json
            pension_survivor.credential_attempt = fake_credential_attempt
            result = pension_survivor.run_step({}, "survivor-benefit")
        finally:
            pension_survivor.http_json = original_http_json
            pension_survivor.credential_attempt = original_credential_attempt
            os.environ.pop("SIPF_PENSION_CLIENT_TOKEN", None)

        self.assertEqual(captured["service_id"], "sipf-notary")
        self.assertEqual(
            captured["profile"], "sipf-survivor-benefit.survivor-benefit-status"
        )
        self.assertEqual(captured["claim_ids"], ["survivor-is-eligible"])
        self.assertTrue(captured["url"].endswith("/v1/credentials"))
        self.assertEqual(result["credential"]["status"], "issued")

    def test_farmer_voucher_purpose_override_reaches_request_source(self) -> None:
        purpose = "https://id.registrystack.org/solmara/purpose/citizen-self-service"
        payload = self.post_json(
            "/v1/scenarios/farmer-climate-smart-voucher/steps/positive/run",
            {"config": {"purpose_override": purpose}},
        )
        self.assertEqual(
            payload["result"]["request_source"]["headers"]["Data-Purpose"], purpose
        )

    def test_farmer_voucher_denial_step_ignores_override(self) -> None:
        payload = self.post_json(
            "/v1/scenarios/farmer-climate-smart-voucher/steps/purpose-denial/run",
            {
                "config": {
                    "purpose_override": "https://id.registrystack.org/solmara/purpose/livestock-movement-control"
                }
            },
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
        self.assertEqual(
            payload["result"]["request_source"]["headers"]["Data-Purpose"], purpose
        )

    def test_citizen_denial_step_ignores_override(self) -> None:
        payload = self.post_json(
            "/v1/scenarios/citizen-self-service/steps/purpose-denial/run",
            {
                "config": {
                    "purpose_override": "https://id.registrystack.org/solmara/purpose/citizen-self-service"
                }
            },
        )
        self.assertEqual(
            payload["result"]["request_source"]["headers"]["Data-Purpose"],
            "https://id.registrystack.org/solmara/purpose/unsupported-demo-purpose",
        )

    def test_citizen_calls_cra_and_nia_and_uses_nia_for_issuance(self) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []
        original_http_json = citizen.http_json
        original_credential_attempt = citizen.credential_attempt
        for name in ("CRA_CITIZEN_CLIENT_TOKEN", "NIA_CITIZEN_CLIENT_TOKEN"):
            os.environ[name] = f"token-{name.lower()}"
        captured: dict[str, Any] = {}

        def fake_http_json(
            method: str,
            url: str,
            headers: dict,
            body: dict | None = None,
            timeout: float = 8.0,
        ) -> StepHttpResult:
            assert body is not None
            calls.append((url, body))
            claim_id = body["claims"][0]
            return StepHttpResult(
                200,
                {
                    "results": [
                        {
                            "evaluation_id": f"eval-{claim_id}",
                            "claim_id": claim_id,
                            "satisfied": True,
                            "disclosure": "predicate",
                        }
                    ]
                },
                {"content-type": common.CLAIM_RESULT_FORMAT},
            )

        def fake_credential_attempt(
            url, token, purpose, evaluation_result, profile, claim_ids, service_id
        ):
            captured.update(
                url=url,
                token=token,
                profile=profile,
                claim_ids=claim_ids,
                service_id=service_id,
            )
            return {"credential": {"status": "issued"}}

        try:
            citizen.http_json = fake_http_json
            citizen.credential_attempt = fake_credential_attempt
            result = citizen.run_step({}, "positive")
        finally:
            citizen.http_json = original_http_json
            citizen.credential_attempt = original_credential_attempt
            for name in ("CRA_CITIZEN_CLIENT_TOKEN", "NIA_CITIZEN_CLIENT_TOKEN"):
                os.environ.pop(name, None)

        self.assertEqual(
            [body["claims"] for _, body in calls],
            [["civil-record-linked"], ["citizen-population-record-active"]],
        )
        self.assertEqual(
            [trace["service_id"] for trace in result["source_trace"]],
            ["cra-notary", "nia-notary"],
        )
        self.assertEqual(captured["service_id"], "nia-notary")
        self.assertEqual(
            captured["profile"], "nia-citizen-status.citizen-population-status"
        )
        self.assertEqual(captured["claim_ids"], ["citizen-population-record-active"])
        self.assertTrue(captured["url"].endswith("/v1/credentials"))
        self.assertNotIn("citizen-self-service-summary", json.dumps(result))

    def test_unknown_scenario_returns_404(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.fetch_json("/v1/scenarios/not-a-story")
        self.assertEqual(raised.exception.code, 404)
        raised.exception.close()

    def fetch_json(self, path: str) -> dict:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}{path}", timeout=5
        ) as response:
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
        public_bytes = keypair.private_key.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )
        self.assertEqual(jwk["x"], common.b64url_nopad(public_bytes))

    def test_holder_proof_header_and_payload_bindings(self) -> None:
        keypair = common.holder_keypair()
        claim_ids = ["birth-is-registered", "child-age-under-5"]
        proof = common.holder_proof(
            keypair,
            audience="sipf-notary",
            evaluation_id="eval-123",
            credential_profile="sipf-survivor-benefit.survivor-benefit-status",
            disclosure="predicate",
            claim_ids=claim_ids,
        )
        header_b64, payload_b64, signature_b64 = proof.split(".")
        header = json.loads(b64url_decode(header_b64))
        payload = json.loads(b64url_decode(payload_b64))

        self.assertEqual(
            header, {"alg": "EdDSA", "typ": "kb+jwt", "kid": keypair.holder_id}
        )
        self.assertEqual(payload["sub"], keypair.holder_id)
        self.assertEqual(payload["aud"], "sipf-notary")
        self.assertEqual(payload["evaluation_id"], "eval-123")
        self.assertEqual(
            payload["credential_profile"],
            "sipf-survivor-benefit.survivor-benefit-status",
        )
        self.assertEqual(payload["claims"], claim_ids)
        self.assertEqual(
            payload["disclosure"],
            common.b64url_nopad(hashlib.sha256(b"predicate").digest()),
        )
        self.assertLessEqual(payload["iat"], int(time.time()))
        self.assertEqual(payload["exp"] - payload["iat"], 60)
        self.assertTrue(payload["jti"])

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        signature = b64url_decode(signature_b64)
        # Raises cryptography.exceptions.InvalidSignature if the proof does not verify.
        keypair.private_key.public_key().verify(signature, signing_input)

    def test_holder_proof_jti_is_unique_per_call(self) -> None:
        keypair = common.holder_keypair()
        kwargs = {
            "audience": "a",
            "evaluation_id": "e",
            "credential_profile": "p",
            "disclosure": "predicate",
            "claim_ids": ["x"],
        }
        first = common.holder_proof(keypair, **kwargs)
        second = common.holder_proof(keypair, **kwargs)
        first_jti = json.loads(b64url_decode(first.split(".")[1]))["jti"]
        second_jti = json.loads(b64url_decode(second.split(".")[1]))["jti"]
        self.assertNotEqual(first_jti, second_jti)

    def test_credential_attempt_includes_holder_binding_and_matching_claims(
        self,
    ) -> None:
        claim_ids = ["survivor-is-eligible"]
        evaluation_result = StepHttpResult(
            200, {"results": [{"evaluation_id": "eval-999"}]}, {}
        )
        captured: dict[str, Any] = {}

        def fake_http_json(method, url, headers, body=None, timeout=8.0):
            (
                captured["method"],
                captured["url"],
                captured["headers"],
                captured["body"],
            ) = method, url, headers, body
            return StepHttpResult(400, {"code": "credential.holder_proof_required"}, {})

        original = common.http_json
        common.http_json = fake_http_json
        try:
            result = common.credential_attempt(
                "http://example.invalid/v1/credentials",
                "runtime-token",
                "https://id.registrystack.org/solmara/purpose/survivor-benefit-determination",
                evaluation_result,
                "sipf-survivor-benefit.survivor-benefit-status",
                claim_ids,
                "sipf-notary",
            )
        finally:
            common.http_json = original

        body = result["credential_source"]["body"]
        self.assertEqual(body["claims"], claim_ids)
        self.assertEqual(body["holder"]["binding"], "did")
        self.assertTrue(body["holder"]["id"].startswith("did:jwk:"))
        proof_payload = json.loads(b64url_decode(body["holder"]["proof"].split(".")[1]))
        self.assertEqual(proof_payload["aud"], "sipf-notary")
        self.assertEqual(proof_payload["claims"], claim_ids)

        # request_source redaction is unaffected by the new holder object.
        self.assertEqual(
            result["credential_source"]["headers"]["x-api-key"],
            "[runtime token hidden]",
        )
        # And the outgoing body actually carried the same holder object (nothing lost in transit).
        self.assertEqual(captured["body"]["holder"], body["holder"])


class ChildBenefitFederatorTest(unittest.TestCase):
    TOKEN_ENVS = (
        "CRA_CHILD_BENEFIT_CLIENT_TOKEN",
        "NIA_CHILD_BENEFIT_CLIENT_TOKEN",
        "SRO_CHILD_BENEFIT_CLIENT_TOKEN",
        "PROGRAMME_CHILD_BENEFIT_CLIENT_TOKEN",
    )

    def setUp(self) -> None:
        for name in self.TOKEN_ENVS:
            os.environ[name] = f"token-{name.lower()}"

    def tearDown(self) -> None:
        for name in self.TOKEN_ENVS:
            os.environ.pop(name, None)
        os.environ.pop(child_benefit_federator.FEDERATOR_TOKEN_ENV, None)

    def test_catalog_lists_authority_predicates_without_eligibility_composition(
        self,
    ) -> None:
        catalog = child_benefit_federator.claim_catalog()
        ids = {entry["id"] for entry in catalog["claims"]}

        self.assertEqual(
            ids,
            {
                "birth-is-registered",
                "child-age-under-5",
                "population-record-active",
                "household-below-poverty-threshold",
                "not-already-enrolled",
            },
        )
        self.assertNotIn("eligible-for-child-benefit", ids)
        self.assertEqual(
            catalog["response_media_type"],
            "application/json",
        )
        self.assertEqual(
            catalog["composition"]["eligible-for-child-benefit"],
            "not_returned_by_orchestrator",
        )
        self.assertEqual(catalog["data"], catalog["claims"])

    def test_collection_groups_five_claims_into_four_ordinary_notary_calls(
        self,
    ) -> None:
        calls: list[tuple[str, dict[str, str], dict[str, Any]]] = []
        original_http_json = child_benefit_federator.http_json

        def fake_http_json(
            method: str,
            url: str,
            headers: dict[str, str],
            body: dict[str, Any],
            timeout: float = 8.0,
        ) -> StepHttpResult:
            calls.append((url, headers, body))
            return StepHttpResult(
                200,
                {
                    "results": [
                        {
                            "evaluation_id": f"internal-{claim_id}",
                            "claim_id": claim_id,
                            "claim_version": "1",
                            "satisfied": True,
                            "disclosure": "predicate",
                            "issued_at": "2026-07-15T00:00:00Z",
                            "source_row": {"private": "must-not-cross"},
                        }
                        for claim_id in body["claims"]
                    ]
                },
                {"content-type": common.CLAIM_RESULT_FORMAT},
            )

        try:
            child_benefit_federator.http_json = fake_http_json
            evidence = child_benefit_federator.collect_evidence(
                "2300010248",
                list(child_benefit.CLAIMS),
                common.PURPOSES["child_benefit"],
                {
                    "type": "Person",
                    "identifiers": [{"scheme": "solmara_uin", "value": "2300010248"}],
                },
            )
        finally:
            child_benefit_federator.http_json = original_http_json

        self.assertEqual(len(calls), 4)
        self.assertEqual(
            calls[0][2]["claims"], ["birth-is-registered", "child-age-under-5"]
        )
        self.assertEqual(calls[1][2]["claims"], ["population-record-active"])
        self.assertEqual(calls[2][2]["claims"], ["household-below-poverty-threshold"])
        self.assertEqual(calls[3][2]["claims"], ["not-already-enrolled"])
        self.assertTrue(all(url.endswith("/v1/evaluations") for url, _, _ in calls))
        self.assertTrue(
            all(
                headers["Accept"] == common.CLAIM_RESULT_FORMAT
                for _, headers, _ in calls
            )
        )
        self.assertEqual(
            [result["claim_id"] for result in evidence["results"]], child_benefit.CLAIMS
        )
        self.assertEqual(
            [trace["service_id"] for trace in evidence["source_trace"]],
            ["cra-notary", "nia-notary", "sro-notary", "programme-notary"],
        )
        self.assertEqual(evidence["orchestration"]["decision"], "not_composed")
        serialized = json.dumps(evidence, sort_keys=True)
        self.assertNotIn("2300010248", serialized)
        self.assertNotIn("internal-", serialized)
        self.assertNotIn("source_row", serialized)
        self.assertNotIn("must-not-cross", serialized)
        self.assertNotIn("token-", serialized)

    def test_unavailable_authority_is_an_error_not_a_false_predicate(self) -> None:
        original_http_json = child_benefit_federator.http_json
        child_benefit_federator.http_json = lambda *_args, **_kwargs: StepHttpResult(
            503,
            {"code": "upstream.unavailable"},
            {"content-type": "application/problem+json"},
        )
        try:
            with self.assertRaises(
                child_benefit_federator.AuthorityUpstreamError
            ) as raised:
                child_benefit_federator.collect_evidence(
                    "2300010248",
                    ["birth-is-registered"],
                    common.PURPOSES["child_benefit"],
                    {},
                )
        finally:
            child_benefit_federator.http_json = original_http_json

        self.assertEqual(raised.exception.status, 503)
        self.assertEqual(raised.exception.code, "upstream.unavailable")

    def test_authority_must_return_exactly_the_requested_predicate_set(self) -> None:
        route = child_benefit_federator.CLAIM_ROUTES["birth-is-registered"]
        response = StepHttpResult(
            200,
            {
                "results": [
                    {
                        "claim_id": "population-record-active",
                        "satisfied": True,
                        "disclosure": "predicate",
                    }
                ]
            },
            {},
        )

        with self.assertRaises(
            child_benefit_federator.AuthorityUpstreamError
        ) as raised:
            child_benefit_federator.minimized_results(
                route, ["birth-is-registered"], response
            )

        self.assertEqual(raised.exception.code, "unexpected_claim_results")

    def test_request_body_has_a_hard_size_limit(self) -> None:
        handler = object.__new__(child_benefit_federator.ChildBenefitFederatorHandler)
        handler.headers = {
            "Content-Length": str(child_benefit_federator.MAX_REQUEST_BODY_BYTES + 1)
        }
        handler.rfile = io.BytesIO(b"")

        with self.assertRaises(child_benefit_federator.RequestBodyError) as rejected:
            handler.read_body()

        self.assertEqual(rejected.exception.status, 413)

    def test_duplicate_claims_are_rejected_before_authority_calls(self) -> None:
        status, content_type, payload = self.post_application(
            {
                "target": {
                    "identifiers": [{"scheme": "solmara_uin", "value": "2300010248"}]
                },
                "claims": ["birth-is-registered", "birth-is-registered"],
                "disclosure": "predicate",
                "format": "application/json",
            }
        )

        self.assertEqual(status, 400)
        self.assertEqual(content_type, "application/problem+json")
        self.assertEqual(payload["code"], "request.invalid")

    def test_raw_household_request_is_denied_without_echoing_the_claim(self) -> None:
        status, content_type, payload = self.post_application(
            {
                "target": {
                    "identifiers": [{"scheme": "solmara_uin", "value": "2300010248"}]
                },
                "claims": ["household-poverty-score"],
                "disclosure": "value",
                "format": "application/json",
            }
        )

        self.assertEqual(status, 403)
        self.assertEqual(content_type, "application/problem+json")
        self.assertEqual(payload["code"], "pdp.purpose_not_permitted")
        self.assertNotIn("household-poverty-score", json.dumps(payload))

    def test_success_uses_the_child_benefit_evidence_media_type(self) -> None:
        original_collect_evidence = child_benefit_federator.collect_evidence
        child_benefit_federator.collect_evidence = lambda *_args: {
            "schema_version": child_benefit_federator.API_VERSION,
            "results": [],
            "source_trace": [],
        }
        try:
            status, content_type, _payload = self.post_application(
                {
                    "target": {
                        "identifiers": [
                            {"scheme": "solmara_uin", "value": "2300010248"}
                        ]
                    },
                    "claims": ["birth-is-registered"],
                    "disclosure": "predicate",
                    "format": "application/json",
                }
            )
        finally:
            child_benefit_federator.collect_evidence = original_collect_evidence

        self.assertEqual(status, 200)
        self.assertEqual(content_type, "application/json")

    def test_obsolete_federation_route_is_absent(self) -> None:
        token = "test-application-token"
        os.environ[child_benefit_federator.FEDERATOR_TOKEN_ENV] = token
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), child_benefit_federator.ChildBenefitFederatorHandler
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/federation/v1/evaluations",
            data=b"{}",
            headers={"x-api-key": token, "Content-Type": "application/json"},
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

        self.assertEqual(rejected.exception.code, 404)
        self.assertEqual(payload["code"], "not_found")

    def post_application(self, body: dict[str, Any]) -> tuple[int, str, dict[str, Any]]:
        token = "test-application-token"
        os.environ[child_benefit_federator.FEDERATOR_TOKEN_ENV] = token
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), child_benefit_federator.ChildBenefitFederatorHandler
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/v1/evaluations",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-api-key": token,
                "Data-Purpose": common.PURPOSES["child_benefit"],
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    return (
                        response.status,
                        response.headers.get_content_type(),
                        json.loads(response.read().decode("utf-8")),
                    )
            except urllib.error.HTTPError as error:
                return (
                    error.code,
                    error.headers.get_content_type(),
                    json.loads(error.read().decode("utf-8")),
                )
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


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
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class CredentialSummaryVctTest(unittest.TestCase):
    VCT = (
        "https://id.registrystack.org/solmara/vct/child-benefit-enrollment-eligibility"
    )

    @staticmethod
    def compact_sd_jwt(payload: dict[str, Any]) -> str:
        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        header = b64url(json.dumps({"alg": "EdDSA", "typ": "dc+sd-jwt"}).encode())
        body = b64url(json.dumps(payload).encode())
        return f"{header}.{body}.fake-signature~ZmFrZS1kaXNjbG9zdXJl~"

    def test_issued_summary_extracts_vct_from_sd_jwt_payload(self) -> None:
        body = {
            "credential": self.compact_sd_jwt(
                {"vct": self.VCT, "iss": "did:web:child-benefit-notary"}
            ),
            "credential_profile": "child_benefit_eligibility_sd_jwt",
            "disclosures": ["a", "b"],
        }
        summary = common.credential_summary(
            "profile", "did:jwk:x", StepHttpResult(200, body, {})
        )
        self.assertEqual(summary["status"], "issued")
        self.assertEqual(summary["vct"], self.VCT)

    def test_issued_summary_without_decodable_credential_has_no_vct(self) -> None:
        body = {"credential": "not-a-jwt", "disclosures": []}
        summary = common.credential_summary(
            "profile", "did:jwk:x", StepHttpResult(200, body, {})
        )
        self.assertEqual(summary["status"], "issued")
        self.assertIsNone(summary["vct"])

    def test_issued_summary_with_undecodable_payload_has_no_vct(self) -> None:
        body = {
            "credential": "eyJhbGciOiJFZERTQSJ9.%%%not-base64%%%.sig",
            "disclosures": [],
        }
        summary = common.credential_summary(
            "profile", "did:jwk:x", StepHttpResult(200, body, {})
        )
        self.assertEqual(summary["status"], "issued")
        self.assertIsNone(summary["vct"])


class FriendlyResultTest(unittest.TestCase):
    COPY = {
        "positive": {
            "met": (
                "Yes. Mateo qualifies for review.",
                "All four facts came back met.",
            ),
        },
        "poverty-control": {
            "unmet": (
                "Rejected: the household is above the threshold.",
                "The caseworker never sees the income.",
            ),
        },
    }

    def test_pdp_denial_reads_as_designed(self) -> None:
        result = StepHttpResult(
            403, {"code": "pdp.purpose_not_permitted", "detail": "nope"}, {}
        )
        friendly = common.friendly_result("positive", result, self.COPY)
        self.assertEqual(friendly["status"], "done")
        self.assertEqual(friendly["title"], "Refused, exactly as designed.")

    def test_all_claims_met_uses_step_copy(self) -> None:
        body = {
            "results": [
                {"claim_id": "a", "satisfied": True},
                {"claim_id": "b", "satisfied": True},
            ]
        }
        friendly = common.friendly_result(
            "positive", StepHttpResult(200, body, {}), self.COPY
        )
        self.assertEqual(friendly["status"], "done")
        self.assertEqual(friendly["title"], "Yes. Mateo qualifies for review.")
        self.assertIn({"label": "Claims met", "value": "2 of 2"}, friendly["facts"])

    def test_unmet_claim_uses_unmet_copy_and_names_claim(self) -> None:
        body = {
            "results": [
                {"claim_id": "household-below-poverty-threshold", "satisfied": False}
            ]
        }
        friendly = common.friendly_result(
            "poverty-control", StepHttpResult(200, body, {}), self.COPY
        )
        self.assertEqual(friendly["status"], "done")
        self.assertEqual(
            friendly["title"], "Rejected: the household is above the threshold."
        )

    def test_unmet_claim_without_copy_falls_back_to_generic_rejection(self) -> None:
        body = {"results": [{"claim_id": "child-age-under-5", "satisfied": False}]}
        friendly = common.friendly_result(
            "deceased-control", StepHttpResult(200, body, {}), self.COPY
        )
        self.assertEqual(friendly["status"], "done")
        self.assertEqual(friendly["title"], "Rejected, exactly as designed.")
        self.assertIn("child-age-under-5", friendly["message"])

    def test_refused_copy_frames_intended_denial_as_done(self) -> None:
        copy = {
            "cause-of-death-denial": {
                "refused": (
                    "Refused: that question does not exist here.",
                    "No such claim is offered.",
                )
            }
        }
        result = StepHttpResult(
            404,
            {
                "code": "claim.not_found",
                "detail": "the requested claim is not available",
            },
            {},
        )
        friendly = common.friendly_result("cause-of-death-denial", result, copy)
        self.assertEqual(friendly["status"], "done")
        self.assertEqual(
            friendly["title"], "Refused: that question does not exist here."
        )

    def test_non_pdp_error_without_refused_copy_needs_attention(self) -> None:
        result = StepHttpResult(
            404, {"code": "claim.not_found", "detail": "missing"}, {}
        )
        friendly = common.friendly_result("positive", result, self.COPY)
        self.assertEqual(friendly["status"], "needs_attention")

    def test_no_response_needs_attention(self) -> None:
        friendly = common.friendly_result(
            "positive", StepHttpResult(None, {}, {}, "URLError"), self.COPY
        )
        self.assertEqual(friendly["status"], "needs_attention")

    def test_unexpected_error_status_needs_attention(self) -> None:
        result = StepHttpResult(500, {"detail": "boom"}, {})
        friendly = common.friendly_result("positive", result, self.COPY)
        self.assertEqual(friendly["status"], "needs_attention")
        self.assertIn("boom", friendly["message"])


if __name__ == "__main__":
    unittest.main()
