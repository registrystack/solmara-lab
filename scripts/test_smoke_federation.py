from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SCRIPT = Path(__file__).with_name("smoke-federation.py")
SPEC = importlib.util.spec_from_file_location("smoke_federation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


ROUTE = {
    "claim_id": "birth-is-registered",
    "url_env": "TEST_AUTHORITY_URL",
    "default_url": "http://authority.test",
}


class FakeFederation:
    CHILD_PURPOSE = "child-benefit-purpose"

    def __init__(self) -> None:
        self.jtis = iter(("request-1", "request-2"))
        self.posts: list[tuple[str, str]] = []

    def ulid(self) -> str:
        return next(self.jtis)

    def federation_payload(self, route: dict[str, str], subject: str, purpose: str, jti: str) -> dict[str, Any]:
        return {"claim": route["claim_id"], "subject": subject, "purpose": purpose, "jti": jti}

    def sign_jwt(self, payload: dict[str, Any]) -> str:
        return f'{payload["purpose"]}:{payload["jti"]}'

    def post_jwt(self, url: str, token: str) -> tuple[int, dict[str, str], Any]:
        self.posts.append((url, token))
        if len(self.posts) == 1:
            return 200, {"content-type": "application/jwt"}, "signed-response"
        if len(self.posts) == 2:
            return 409, {"content-type": "application/problem+json"}, {"code": "federation.replay"}
        return 403, {"content-type": "application/problem+json"}, {"code": "federation.forbidden"}

    def verify_peer_response(self, route: dict[str, str], request_jti: str, token: str, content_type: str) -> Any:
        return {
            "result": {
                "claims": {
                    route["claim_id"]: {"satisfied": True, "disclosure": "predicate"},
                }
            }
        }

    def verification_error_code(self, payload: Any) -> None:
        return None


class SmokeFederationTests(unittest.TestCase):
    def test_protocol_replays_the_exact_same_signed_request(self) -> None:
        federation = FakeFederation()

        failures = smoke.protocol_failures(federation, ROUTE, "2300010248")

        self.assertEqual([], failures)
        self.assertEqual(federation.posts[0][1], federation.posts[1][1])
        self.assertNotEqual(federation.posts[1][1], federation.posts[2][1])

    def test_bundle_rejects_error_represented_as_false_predicate(self) -> None:
        body = valid_bundle()
        body["results"][0].update(
            {
                "satisfied": False,
                "value": False,
                "federation_status": None,
                "federation_error": {"code": "bad_response_signature"},
            }
        )
        body["federation_trace"][0]["response_source"] = {
            "status": None,
            "body": {"error": {"code": "bad_response_signature"}},
        }

        failures = smoke.validated_bundle_failures(200, body, ["birth-is-registered"])

        self.assertTrue(any("represented an authority error" in failure for failure in failures))
        self.assertTrue(any("outage or response-verification error" in failure or "HTTP 200" in failure for failure in failures))

    def test_bundle_accepts_verified_positive_authority_result(self) -> None:
        self.assertEqual([], smoke.validated_bundle_failures(200, valid_bundle(), ["birth-is-registered"]))

    def test_raw_household_denial_requires_the_purpose_problem(self) -> None:
        federation = SimpleNamespace(
            FEDERATOR_TOKEN_ENV="TEST_FEDERATOR_TOKEN",
            CHILD_PURPOSE="child-benefit-purpose",
        )
        os.environ[federation.FEDERATOR_TOKEN_ENV] = "test-token"
        captured: dict[str, Any] = {}
        original_http_json = smoke.http_json

        def fake_http_json(method: str, url: str, headers: dict[str, str], body: Any) -> Any:
            captured.update(method=method, url=url, headers=headers, body=body)
            return SimpleNamespace(
                status=403,
                headers={"content-type": "application/problem+json"},
                body={"code": "pdp.purpose_not_permitted", "detail": "Minimized predicates only."},
            )

        smoke.http_json = fake_http_json
        try:
            failures = smoke.raw_household_denial_failures(federation, "2300010248")
        finally:
            smoke.http_json = original_http_json
            os.environ.pop(federation.FEDERATOR_TOKEN_ENV, None)

        self.assertEqual([], failures)
        self.assertEqual(captured["body"]["claims"], ["household-poverty-score"])
        self.assertEqual(captured["body"]["format"], smoke.FEDERATED_BUNDLE_FORMAT)
        self.assertEqual(captured["headers"]["Accept"], smoke.FEDERATED_BUNDLE_FORMAT)


def valid_bundle() -> dict[str, Any]:
    return {
        "results": [
            {
                "claim_id": "birth-is-registered",
                "satisfied": True,
                "value": True,
            }
        ],
        "federation_trace": [
            {
                "claim_id": "birth-is-registered",
                "response_source": {
                    "status": 200,
                    "body": {"result": {"claims": {"birth-is-registered": {"satisfied": True}}}},
                },
            }
        ],
        "federator": {"decision": "not_composed"},
    }


if __name__ == "__main__":
    unittest.main()
