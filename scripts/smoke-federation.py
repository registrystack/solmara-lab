#!/usr/bin/env python3
"""Smoke the live child-benefit federation protocol and result boundary."""

from __future__ import annotations

import importlib
import os
import shlex
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scenarios.common import FEDERATED_BUNDLE_FORMAT, auth_headers, evaluation_body, http_json, joined_url  # noqa: E402


POSITIVE_SUBJECT = "2300010248"
UNSUPPORTED_PURPOSE = "https://id.registrystack.org/solmara/purpose/unsupported-federation-smoke"
FEDERATION_PATH = "/federation/v1/evaluations"


def main() -> int:
    load_dotenv(ROOT / ".env")
    federation = load_federation_module()
    claims = list(federation.CLAIM_ROUTES)
    route = federation.CLAIM_ROUTES["birth-is-registered"]

    failures = protocol_failures(federation, route, POSITIVE_SUBJECT)
    failures.extend(bundle_failures(federation, POSITIVE_SUBJECT, claims))
    failures.extend(raw_household_denial_failures(federation, POSITIVE_SUBJECT))
    if failures:
        for failure in failures:
            print(f"smoke-federation: {failure}", file=sys.stderr)
        return 1

    print(
        "smoke-federation: signed authority success, exact-request replay denial, "
        "unsupported-purpose denial, and error-state checks passed"
    )
    return 0


def load_federation_module() -> Any:
    scenario_runner = ROOT / "scenario-runner"
    if str(scenario_runner) not in sys.path:
        sys.path.insert(0, str(scenario_runner))
    return importlib.import_module("child_benefit_federator")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        if raw_value == "":
            os.environ[key] = ""
            continue
        parts = shlex.split(raw_value, posix=True)
        os.environ[key] = parts[0] if parts else ""


def protocol_failures(federation: Any, route: dict[str, str], subject: str) -> list[str]:
    failures: list[str] = []
    url = joined_url(os.environ.get(route["url_env"], route["default_url"]), FEDERATION_PATH)

    try:
        request_jti = federation.ulid()
        payload = federation.federation_payload(route, subject, federation.CHILD_PURPOSE, request_jti)
        signed_request = federation.sign_jwt(payload)
    except Exception as error:
        return [f"could not sign authority request ({error.__class__.__name__}); run `just generate` before live smoke"]

    status, headers, body = federation.post_jwt(url, signed_request)
    if status != 200:
        failures.append(f"signed authority request returned HTTP {status}, expected 200")
    elif not isinstance(body, str):
        failures.append("signed authority request returned an unsigned response")
    else:
        verified = federation.verify_peer_response(route, request_jti, body, headers.get("content-type", ""))
        verification_error = federation.verification_error_code(verified)
        if verification_error:
            failures.append(f"signed authority response failed verification ({verification_error})")
        else:
            failures.extend(validated_claim_failures(route, verified))

    replay_status, replay_headers, replay_body = federation.post_jwt(url, signed_request)
    failures.extend(
        denial_failures(
            "exact signed request replay",
            replay_status,
            replay_headers,
            replay_body,
            expected_status=409,
            expected_code="federation.replay",
        )
    )

    try:
        unsupported_jti = federation.ulid()
        unsupported_payload = federation.federation_payload(route, subject, UNSUPPORTED_PURPOSE, unsupported_jti)
        unsupported_request = federation.sign_jwt(unsupported_payload)
    except Exception as error:
        failures.append(f"could not sign unsupported-purpose request ({error.__class__.__name__})")
        return failures

    unsupported_status, unsupported_headers, unsupported_body = federation.post_jwt(url, unsupported_request)
    failures.extend(
        denial_failures(
            "unsupported-purpose request",
            unsupported_status,
            unsupported_headers,
            unsupported_body,
            expected_status=403,
            expected_code="federation.forbidden",
        )
    )
    return failures


def validated_claim_failures(route: dict[str, str], payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["verified authority response was not a JSON object"]
    result = payload.get("result")
    claims = result.get("claims") if isinstance(result, dict) else None
    claim = claims.get(route["claim_id"]) if isinstance(claims, dict) else None
    if not isinstance(claim, dict):
        return [f'verified authority response omitted {route["claim_id"]}']
    if claim.get("satisfied") is not True or claim.get("disclosure") != "predicate":
        return [f'verified authority response did not satisfy {route["claim_id"]} as a predicate']
    return []


def denial_failures(
    label: str,
    status: int | None,
    headers: dict[str, str],
    body: Any,
    *,
    expected_status: int,
    expected_code: str,
) -> list[str]:
    failures: list[str] = []
    if status != expected_status:
        failures.append(f"{label} returned HTTP {status}, expected {expected_status}")
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/problem+json":
        failures.append(f"{label} returned {content_type or 'no content type'}, expected application/problem+json")
    code = body.get("code") if isinstance(body, dict) else None
    if code != expected_code:
        failures.append(f"{label} returned problem code {code!r}, expected {expected_code!r}")
    return failures


def bundle_failures(federation: Any, subject: str, claims: list[str]) -> list[str]:
    token = os.environ.get(federation.FEDERATOR_TOKEN_ENV, "")
    if not token:
        return [f"missing {federation.FEDERATOR_TOKEN_ENV}; run `just generate` before live smoke"]
    base_url = os.environ.get("CHILD_BENEFIT_FEDERATOR_URL", "http://127.0.0.1:4321")
    response = http_json(
        "POST",
        joined_url(base_url, "/v1/evaluations"),
        auth_headers(token, federation.CHILD_PURPOSE, FEDERATED_BUNDLE_FORMAT),
        evaluation_body(subject, claims, scheme="solmara_uin", format=FEDERATED_BUNDLE_FORMAT),
    )
    return validated_bundle_failures(response.status, response.body, claims)


def validated_bundle_failures(status: int | None, body: Any, claims: list[str]) -> list[str]:
    if status != 200:
        return [f"positive federated bundle returned HTTP {status}, expected 200"]
    if not isinstance(body, dict):
        return ["positive federated bundle was not a JSON object"]

    failures: list[str] = []
    results = body.get("results")
    result_by_claim = {
        item.get("claim_id"): item
        for item in results
        if isinstance(item, dict) and isinstance(item.get("claim_id"), str)
    } if isinstance(results, list) else {}
    if len(result_by_claim) != len(claims) or set(result_by_claim) != set(claims):
        failures.append("positive federated bundle did not return exactly the requested authority predicates")
    for claim_id in claims:
        result = result_by_claim.get(claim_id)
        if not isinstance(result, dict):
            continue
        if any(key in result for key in ("error", "federation_error", "federation_status")):
            failures.append(f"{claim_id} represented an authority error as a predicate result")
        if result.get("satisfied") is not True or result.get("value") is not True:
            failures.append(f"positive federated bundle returned {claim_id} as false or indeterminate")

    trace = body.get("federation_trace")
    if not isinstance(trace, list) or len(trace) != len(claims):
        failures.append("positive federated bundle did not include one authority trace per predicate")
    else:
        for item in trace:
            claim_id = item.get("claim_id", "unknown claim") if isinstance(item, dict) else "unknown claim"
            response_source = item.get("response_source") if isinstance(item, dict) else None
            if not isinstance(response_source, dict) or response_source.get("status") != 200:
                failures.append(f"{claim_id} authority trace did not record HTTP 200")
                continue
            response_body = response_source.get("body")
            if not isinstance(response_body, dict) or "error" in response_body:
                failures.append(f"{claim_id} authority trace contains an outage or response-verification error")

    federator = body.get("federator")
    if not isinstance(federator, dict) or federator.get("decision") != "not_composed":
        failures.append("positive federated bundle did not preserve the federator's non-composition boundary")
    return failures


def raw_household_denial_failures(federation: Any, subject: str) -> list[str]:
    token = os.environ.get(federation.FEDERATOR_TOKEN_ENV, "")
    if not token:
        return [f"missing {federation.FEDERATOR_TOKEN_ENV}; run `just generate` before live smoke"]
    base_url = os.environ.get("CHILD_BENEFIT_FEDERATOR_URL", "http://127.0.0.1:4321")
    response = http_json(
        "POST",
        joined_url(base_url, "/v1/evaluations"),
        auth_headers(token, federation.CHILD_PURPOSE, FEDERATED_BUNDLE_FORMAT),
        evaluation_body(
            subject,
            ["household-poverty-score"],
            scheme="solmara_uin",
            disclosure="value",
            format=FEDERATED_BUNDLE_FORMAT,
        ),
    )
    failures: list[str] = []
    if response.status != 403:
        failures.append(f"raw household request returned HTTP {response.status}, expected 403")
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/problem+json":
        failures.append(
            f"raw household request returned {content_type or 'no content type'}, expected application/problem+json"
        )
    code = response.body.get("code") if isinstance(response.body, dict) else None
    if code != "pdp.purpose_not_permitted":
        failures.append(
            f"raw household request returned problem code {code!r}, expected 'pdp.purpose_not_permitted'"
        )
    serialized = str(response.body)
    if "household-poverty-score" in serialized or "raw_household_score" in serialized:
        failures.append("raw household denial reflected a protected source field")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
