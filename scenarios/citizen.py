#!/usr/bin/env python3
"""Citizen self-service guided scenario."""

from __future__ import annotations

from typing import Any

from .common import (
    CLAIM_RESULT_FORMAT,
    PURPOSES,
    SD_JWT_VC_FORMAT,
    StepHttpResult,
    auth_headers,
    credential_attempt,
    evaluation_body,
    friendly_result,
    http_json,
    missing_runtime_token,
    request_source,
    source_response,
    standard_error_result,
)
from .service_config import (
    authority_service_id,
    service_token,
    service_token_env,
    service_url,
)


SCENARIO_ID = "citizen-self-service"
SERVICE_NAME = "Citizen self-service evidence"
CRA_CLIENT = "cra-citizen"
NIA_CLIENT = "nia-citizen"
POSITIVE_SUBJECT = "2300018263"
CRA_CLAIMS = ["civil-record-linked"]
NIA_CLAIMS = ["citizen-population-record-active"]
CREDENTIAL_PROFILE = "nia-citizen-status.citizen-population-status"
CREDENTIAL_STEPS = {"positive"}
AUTHORITY_NAMES = {
    CRA_CLIENT: "Civil Registration Authority",
    NIA_CLIENT: "National Identity Agency",
}
FRIENDLY = {
    "discover": {
        "met": (
            "The catalogues list what may be asked.",
            "Claim definitions only. No resident data has moved.",
        ),
    },
    "positive": {
        "met": (
            "Elena's minimized status is ready.",
            "CRA confirmed the civil link and NIA confirmed an active population record. NIA can issue the population-status credential.",
        ),
        "unmet": (
            "No status credential is available on the facts returned.",
            "One or more self-service checks came back not met.",
        ),
    },
}


def story() -> dict[str, Any]:
    return {
        "id": SCENARIO_ID,
        "title": "Citizen self-service",
        "short_title": "Citizen self-service",
        "proves": "The portal can present separate CRA and NIA evidence while NIA remains the sole citizen-status credential issuer.",
        "domain": "Citizen services",
        "availability": "hosted",
        "intro": "A signed-in citizen previews their own minimized status evidence.",
        "actor": "Citizen Services Portal",
        "subject": {"name": "Elena Dela Cruz", "identifier": POSITIVE_SUBJECT},
        "requester": {
            "name": "Citizen portal BFF",
            "purpose": PURPOSES["citizen_self_service"],
        },
        "steps": [
            {
                "id": "discover",
                "label": "Discover citizen claims",
                "prompt": "Read the CRA and NIA catalogues.",
                "button": "Discover",
                "request_summary": "GET /v1/claims from CRA and NIA.",
            },
            {
                "id": "positive",
                "label": "Evaluate citizen status",
                "prompt": "Evaluate the two source-owned predicates.",
                "button": "Evaluate",
                "request_summary": "POST CRA civil-link and NIA population-status claims.",
            },
            {
                "id": "purpose-denial",
                "label": "Purpose denial",
                "prompt": "Use an unsupported purpose.",
                "button": "Try denial",
                "request_summary": "POST the same claims with an unsupported Data-Purpose header.",
            },
        ],
        "receipt": [
            {
                "label": "Credential",
                "value": "NIA citizen population-status SD-JWT VC preview",
            },
            {"label": "Raw rows copied", "value": "No"},
        ],
    }


def preview_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=True)


def _request(config: dict[str, Any], step_id: str, *, send: bool) -> dict[str, Any]:
    subject = {"positive": POSITIVE_SUBJECT, "purpose-denial": POSITIVE_SUBJECT}.get(
        step_id
    )
    if step_id != "discover" and not subject:
        return standard_error_result(step_id)
    purpose = request_purpose(config, step_id)
    requests = authority_requests(step_id, subject, purpose)
    preview = combined_request_preview(requests, purpose)
    if not send:
        return {"request_source": preview}

    missing = next(
        (request for request in requests if not service_token(request["client_id"])),
        None,
    )
    if missing:
        result = missing_runtime_token(
            step_id,
            SERVICE_NAME,
            service_token_env(missing["client_id"]),
            preview,
        )
        result["request_sources"] = [request["source"] for request in requests]
        return result

    responses: list[tuple[dict[str, Any], StepHttpResult]] = []
    for authority_request in requests:
        result = http_json(
            authority_request["method"],
            authority_request["url"],
            authority_request["headers"],
            authority_request["body"],
        )
        responses.append((authority_request, result))

    aggregate = aggregate_response(responses)
    payload: dict[str, Any] = {
        "step_id": step_id,
        "friendly": friendly_result(step_id, aggregate, FRIENDLY),
        "request_source": preview,
        "request_sources": [request["source"] for request, _ in responses],
        "response_source": source_response(aggregate),
        "source_trace": [
            authority_trace(request, response) for request, response in responses
        ],
    }
    if step_id in CREDENTIAL_STEPS and aggregate.status == 200:
        nia_result = next(
            response
            for request, response in responses
            if request["client_id"] == NIA_CLIENT
        )
        payload.update(
            credential_attempt(
                service_url(NIA_CLIENT, "/v1/credentials"),
                service_token(NIA_CLIENT),
                purpose,
                nia_result,
                CREDENTIAL_PROFILE,
                NIA_CLAIMS,
                authority_service_id(NIA_CLIENT),
            )
        )
    return payload


def authority_requests(
    step_id: str, subject: str | None, purpose: str
) -> list[dict[str, Any]]:
    if step_id == "discover":
        return [
            build_request(CRA_CLIENT, "GET", "/v1/claims", purpose),
            build_request(NIA_CLIENT, "GET", "/v1/claims", purpose),
        ]
    if step_id in {"positive", "purpose-denial"}:
        return [
            build_request(
                CRA_CLIENT, "POST", "/v1/evaluations", purpose, subject, CRA_CLAIMS
            ),
            build_request(
                NIA_CLIENT,
                "POST",
                "/v1/evaluations",
                purpose,
                subject,
                NIA_CLAIMS,
                SD_JWT_VC_FORMAT,
            ),
        ]
    return []


def build_request(
    client_id: str,
    method: str,
    path: str,
    purpose: str,
    subject: str | None = None,
    claims: list[str] | None = None,
    response_format: str = CLAIM_RESULT_FORMAT,
) -> dict[str, Any]:
    token = service_token(client_id)
    url = service_url(client_id, path)
    headers = auth_headers(
        token, purpose, response_format if method == "POST" else "application/json"
    )
    body = (
        evaluation_body(
            subject or "", claims or [], scheme="solmara_uin", format=response_format
        )
        if method == "POST"
        else None
    )
    return {
        "client_id": client_id,
        "method": method,
        "url": url,
        "headers": headers,
        "body": body,
        "source": request_source(method, url, headers, body),
    }


def combined_request_preview(
    requests: list[dict[str, Any]], purpose: str
) -> dict[str, Any]:
    return {
        "method": "MULTI",
        "url": "solmara://authority-notaries",
        "headers": {"Data-Purpose": purpose},
        "requests": [request["source"] for request in requests],
    }


def aggregate_response(
    responses: list[tuple[dict[str, Any], StepHttpResult]],
) -> StepHttpResult:
    failed = next(
        (
            response
            for _, response in responses
            if response.status is None or not 200 <= response.status < 300
        ),
        None,
    )
    if failed:
        return failed
    results: list[dict[str, Any]] = []
    for request, response in responses:
        body = response.body if isinstance(response.body, dict) else {}
        raw_results = body.get("results")
        if request["method"] == "POST" and not isinstance(raw_results, list):
            return StepHttpResult(
                502,
                {
                    "code": "authority.invalid_response",
                    "detail": "An authority response omitted claim results.",
                },
                {},
            )
        for result in raw_results or []:
            if isinstance(result, dict):
                results.append(
                    {
                        **result,
                        "authority": AUTHORITY_NAMES[request["client_id"]],
                        "notary_service_id": authority_service_id(request["client_id"]),
                    }
                )
    return StepHttpResult(
        200, {"results": results}, {"content-type": "application/json"}
    )


def authority_trace(
    request: dict[str, Any], response: StepHttpResult
) -> dict[str, Any]:
    return {
        "authority": AUTHORITY_NAMES[request["client_id"]],
        "service_id": authority_service_id(request["client_id"]),
        "request_source": request["source"],
        "response_source": source_response(response),
    }


def request_purpose(config: dict[str, Any], step_id: str) -> str:
    if step_id == "purpose-denial":
        return "https://id.registrystack.org/solmara/purpose/unsupported-demo-purpose"
    if isinstance(config.get("purpose_override"), str):
        return config["purpose_override"]
    return PURPOSES["citizen_self_service"]
