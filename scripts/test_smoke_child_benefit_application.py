from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SCRIPT = Path(__file__).with_name("smoke-child-benefit-application.py")
SPEC = importlib.util.spec_from_file_location("smoke_child_benefit_application", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class ChildBenefitApplicationSmokeTests(unittest.TestCase):
    def test_accepts_source_owned_application_evidence(self) -> None:
        claims = list(smoke.EXPECTED_CLAIM_OWNERS)

        failures = smoke.validated_evidence_failures(
            200,
            valid_evidence(claims),
            smoke.POSITIVE_SUBJECT,
            claims,
        )

        self.assertEqual([], failures)

    def test_rejects_obsolete_federation_and_raw_source_fields(self) -> None:
        claims = ["birth-is-registered"]
        body = valid_evidence(claims)
        body["federation_trace"] = []
        body["results"][0]["source_record"] = {"birth_brn": "protected"}

        failures = smoke.validated_evidence_failures(
            200,
            body,
            smoke.POSITIVE_SUBJECT,
            claims,
        )

        self.assertTrue(any("obsolete federation_trace" in failure for failure in failures))
        self.assertTrue(any("raw source" in failure for failure in failures))

    def test_rejects_wrong_owner_duplicate_result_and_subject_echo(self) -> None:
        claims = ["birth-is-registered"]
        body = valid_evidence(claims)
        body["results"][0]["notary_service_id"] = "child-benefit-federator"
        body["results"].append(dict(body["results"][0]))
        body["debug_subject"] = smoke.POSITIVE_SUBJECT

        failures = smoke.validated_evidence_failures(
            200,
            body,
            smoke.POSITIVE_SUBJECT,
            claims,
        )

        self.assertTrue(any("exactly the requested predicates" in failure for failure in failures))
        self.assertTrue(any("authority Notary" in failure for failure in failures))
        self.assertTrue(any("raw subject identifier" in failure for failure in failures))

    def test_application_request_uses_ordinary_json(self) -> None:
        claims = ["birth-is-registered"]
        captured: dict[str, Any] = {}
        original_http_json = smoke.http_json

        def fake_http_json(
            method: str,
            url: str,
            headers: dict[str, str],
            body: Any,
        ) -> Any:
            captured.update(method=method, url=url, headers=headers, body=body)
            return SimpleNamespace(status=200, body=valid_evidence(claims))

        smoke.http_json = fake_http_json
        try:
            failures = smoke.application_evidence_failures(
                "http://application.test",
                "test-token",
                smoke.POSITIVE_SUBJECT,
                claims,
            )
        finally:
            smoke.http_json = original_http_json

        self.assertEqual([], failures)
        self.assertEqual("application/json", captured["headers"]["Accept"])
        self.assertEqual("application/json", captured["body"]["format"])
        self.assertEqual(claims, captured["body"]["claims"])
        self.assertEqual(
            {"as_of_date": smoke.CHILD_BENEFIT_AS_OF_DATE},
            captured["body"]["variables"],
        )

    def test_raw_household_denial_requires_stable_purpose_problem(self) -> None:
        captured: dict[str, Any] = {}
        original_http_json = smoke.http_json

        def fake_http_json(
            method: str,
            url: str,
            headers: dict[str, str],
            body: Any,
        ) -> Any:
            captured.update(method=method, url=url, headers=headers, body=body)
            return SimpleNamespace(
                status=403,
                headers={"content-type": "application/problem+json"},
                body={"code": "pdp.purpose_not_permitted"},
            )

        smoke.http_json = fake_http_json
        try:
            failures = smoke.raw_household_denial_failures(
                "http://application.test",
                "test-token",
                smoke.POSITIVE_SUBJECT,
            )
        finally:
            smoke.http_json = original_http_json

        self.assertEqual([], failures)
        self.assertEqual(["household-poverty-score"], captured["body"]["claims"])
        self.assertEqual("value", captured["body"]["disclosure"])
        self.assertEqual("application/json", captured["headers"]["Accept"])


def valid_evidence(claims: list[str]) -> dict[str, Any]:
    services = {smoke.EXPECTED_CLAIM_OWNERS[claim_id] for claim_id in claims}
    return {
        "schema_version": "solmara-child-benefit-evidence/v1",
        "orchestration": {
            "service_id": "child-benefit-federator",
            "decision": "not_composed",
        },
        "target": {"type": "Person", "identifier_schemes": ["solmara_uin"]},
        "results": [
            {
                "claim_id": claim_id,
                "satisfied": True,
                "disclosure": "predicate",
                "notary_service_id": smoke.EXPECTED_CLAIM_OWNERS[claim_id],
            }
            for claim_id in claims
        ],
        "source_trace": [
            {
                "service_id": service_id,
                "response_summary": {"status": 200},
            }
            for service_id in sorted(services)
        ],
    }


if __name__ == "__main__":
    unittest.main()
