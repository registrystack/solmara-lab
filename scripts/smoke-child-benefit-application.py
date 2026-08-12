#!/usr/bin/env python3
"""Smoke child-benefit collection over the central Registry Evidence API.

The child-benefit service is an application evidence collector. It requests
separately governed requirements and never composes the programme decision.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scenarios.common import (  # noqa: E402
    PURPOSES,
    http_json,
    joined_url,
)
from scenarios.service_config import requirement_id  # noqa: E402


POSITIVE_SUBJECT = "2300010248"
APPLICATION_URL_ENV = "CHILD_BENEFIT_FEDERATOR_URL"
APPLICATION_URL_DEFAULT = "http://127.0.0.1:4321"
APPLICATION_TOKEN_ENV = "CHILD_BENEFIT_FEDERATOR_TOKEN"
UNSUPPORTED_PURPOSE = "https://id.registrystack.org/solmara/purpose/unsupported-application-smoke"
EXPECTED_CLAIM_OWNERS = {
    "birth-is-registered": ("Civil Registration Authority", "cra-child-benefit"),
    "child-age-under-5": ("Civil Registration Authority", "cra-child-benefit"),
    "population-record-active": ("National Identity Agency", "nia-child-benefit"),
    "household-below-poverty-threshold": (
        "Social Registry Office",
        "sro-child-benefit",
    ),
    "not-already-enrolled": ("MoSD Programme MIS", "programme-child-benefit"),
}


def main() -> int:
    load_dotenv(ROOT / ".env")
    token = os.environ.get(APPLICATION_TOKEN_ENV, "")
    if not token:
        print(
            f"smoke-child-benefit-application: missing {APPLICATION_TOKEN_ENV}; run `just generate` before live smoke",
            file=sys.stderr,
        )
        return 1

    base_url = os.environ.get(APPLICATION_URL_ENV, APPLICATION_URL_DEFAULT)
    claims = list(EXPECTED_CLAIM_OWNERS)
    failures = application_evidence_failures(base_url, token, POSITIVE_SUBJECT, claims)
    failures.extend(wrong_purpose_failures(base_url, token, POSITIVE_SUBJECT))
    failures.extend(raw_household_denial_failures(base_url, token, POSITIVE_SUBJECT))
    if failures:
        for failure in failures:
            print(f"smoke-child-benefit-application: {failure}", file=sys.stderr)
        return 1

    print(
        "smoke-child-benefit-application: authority-owned evidence, application non-composition, "
        "unsupported-purpose denial, and raw-source denial checks passed"
    )
    return 0


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


def application_evidence_failures(
    base_url: str, token: str, subject: str, claims: list[str]
) -> list[str]:
    response = http_json(
        "POST",
        joined_url(base_url, "/v1/evaluations"),
        application_headers(token, PURPOSES["child_benefit"]),
        application_body(subject, claims),
    )
    return validated_evidence_failures(response.status, response.body, subject, claims)


def validated_evidence_failures(
    status: int | None, body: Any, subject: str, claims: list[str]
) -> list[str]:
    if status != 200:
        return [f"positive application request returned HTTP {status}, expected 200"]
    if not isinstance(body, dict):
        return ["positive application response was not a JSON object"]

    failures: list[str] = []
    for obsolete in ("federation_trace", "federator", "federation"):
        if obsolete in body:
            failures.append(f"positive application response retained obsolete {obsolete}")

    orchestration = body.get("orchestration")
    if not isinstance(orchestration, dict):
        failures.append("positive application response omitted orchestration ownership")
    else:
        if orchestration.get("service_id") != "child-benefit-federator":
            failures.append("positive application response identified the wrong application")
        if orchestration.get("decision") != "not_composed":
            failures.append("positive application response crossed the programme decision boundary")

    results = body.get("results")
    result_by_claim = (
        {
            item.get("claim_id"): item
            for item in results
            if isinstance(item, dict) and isinstance(item.get("claim_id"), str)
        }
        if isinstance(results, list)
        else {}
    )
    if (
        not isinstance(results, list)
        or set(result_by_claim) != set(claims)
        or len(results) != len(claims)
    ):
        failures.append("positive application response did not return exactly the requested predicates")
    for claim_id in claims:
        result = result_by_claim.get(claim_id)
        if not isinstance(result, dict):
            continue
        if any(key in result for key in ("error", "source_record", "raw")):
            failures.append(f"{claim_id} leaked an error or raw source representation")
        if result.get("satisfied") is not True or result.get("value") is not True:
            failures.append(f"positive application response did not satisfy {claim_id} as a predicate")
        expected_authority, _ = EXPECTED_CLAIM_OWNERS[claim_id]
        if result.get("authority") != expected_authority:
            failures.append(f"{claim_id} was not attributed to its source authority")

    source_trace = body.get("source_trace")
    expected_sources = []
    for authority, client_id in dict.fromkeys(
        EXPECTED_CLAIM_OWNERS[claim] for claim in claims
    ):
        expected_sources.append(
            (
                authority,
                requirement_id(client_id),
                "registry-evidence",
                200,
            )
        )
    if not isinstance(source_trace, list):
        failures.append("positive application response omitted its ordinary source trace")
    else:
        traced_sources: list[tuple[Any, Any, Any, Any]] = []
        for item in source_trace:
            if not isinstance(item, dict):
                failures.append("positive application source trace contained an invalid entry")
                continue
            traced_sources.append(
                (
                    item.get("authority"),
                    item.get("requirement"),
                    item.get("service_id"),
                    item.get("status"),
                )
            )
        if traced_sources != expected_sources:
            failures.append(
                "positive application source trace did not exactly cover the requested Evidence requirements"
            )

    signed_evidence = body.get("signed_evidence")
    if not isinstance(signed_evidence, list) or len(signed_evidence) != len(
        expected_sources
    ):
        failures.append(
            "positive application response did not preserve one signed assertion per Evidence requirement"
        )
    elif any(
        not isinstance(assertion, dict)
        or not {"protected", "payload", "signature"}.issubset(assertion)
        for assertion in signed_evidence
    ):
        failures.append("positive application response contained an invalid signed assertion")

    if subject in json.dumps(body, sort_keys=True):
        failures.append("positive application response echoed the raw subject identifier")
    return failures


def wrong_purpose_failures(base_url: str, token: str, subject: str) -> list[str]:
    response = http_json(
        "POST",
        joined_url(base_url, "/v1/evaluations"),
        application_headers(token, UNSUPPORTED_PURPOSE),
        application_body(subject, ["birth-is-registered"]),
    )
    return denial_failures(
        "unsupported-purpose request",
        response.status,
        response.headers,
        response.body,
        expected_status=403,
        expected_code="not_authorized",
        forbidden_values=(subject,),
    )


def denial_failures(
    label: str,
    status: int | None,
    headers: dict[str, str],
    body: Any,
    *,
    expected_status: int,
    expected_code: str,
    forbidden_values: tuple[str, ...] = (),
) -> list[str]:
    failures: list[str] = []
    if status != expected_status:
        failures.append(f"{label} returned HTTP {status}, expected {expected_status}")
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/problem+json":
        failures.append(
            f"{label} returned {content_type or 'no content type'}, expected application/problem+json"
        )
    code = body.get("code") if isinstance(body, dict) else None
    if code != expected_code:
        failures.append(f"{label} returned problem code {code!r}, expected {expected_code!r}")
    serialized = json.dumps(body, sort_keys=True) if body is not None else ""
    if any(value and value in serialized for value in forbidden_values):
        failures.append(f"{label} reflected a protected request or source value")
    if isinstance(body, dict) and any(
        key in body
        for key in ("results", "signed_evidence", "source_trace", "assertion")
    ):
        failures.append(f"{label} returned partial Evidence data")
    return failures


def raw_household_denial_failures(
    base_url: str, token: str, subject: str
) -> list[str]:
    response = http_json(
        "POST",
        joined_url(base_url, "/v1/evaluations"),
        application_headers(token, PURPOSES["child_benefit"]),
        application_body(subject, ["household-poverty-score"]),
    )
    failures = denial_failures(
        "raw household request",
        response.status,
        response.headers,
        response.body,
        expected_status=400,
        expected_code="invalid_request",
        forbidden_values=(subject, "raw_household_score"),
    )
    serialized = json.dumps(response.body, sort_keys=True)
    if "raw_household_score" in serialized or subject in serialized:
        failures.append("raw household denial reflected protected source data")
    return failures


def application_headers(token: str, purpose: str) -> dict[str, str]:
    return {
        "x-api-key": token,
        "Data-Purpose": purpose,
        "Accept": "application/json",
    }


def application_body(subject: str, claims: list[str]) -> dict[str, Any]:
    return {
        "target": {
            "identifiers": [
                {"scheme": "solmara_uin", "value": subject},
            ]
        },
        "claims": claims,
    }


if __name__ == "__main__":
    raise SystemExit(main())
