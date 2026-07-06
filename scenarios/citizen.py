#!/usr/bin/env python3
"""Citizen self-service guided scenario."""

from __future__ import annotations

from typing import Any

from .common import (
    CLAIM_RESULT_FORMAT,
    PURPOSES,
    SD_JWT_VC_FORMAT,
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
from .service_config import service_token, service_token_env, service_url


SCENARIO_ID = "citizen-self-service"
SERVICE_NAME = "Citizen Notary"
SERVICE_ID = "citizen-notary"
POSITIVE_SUBJECT = "2300018263"
CLAIMS = ["population-record-active", "civil-record-linked", "citizen-self-service-summary"]
CREDENTIAL_PROFILE = "citizen_status_sd_jwt"
CREDENTIAL_STEPS = {"positive"}
FRIENDLY = {
    "discover": {
        "met": ("The catalogue lists what may be asked.", "Claim definitions only. No resident data has moved."),
    },
    "positive": {
        "met": (
            "Here is Elena's own summary.",
            "The portal shows a resident their own facts, under the self-service purpose, and nothing else.",
        ),
        "unmet": (
            "No summary available on the facts returned.",
            "One or more self-service checks came back not met.",
        ),
    },
}


def story() -> dict[str, Any]:
    return {
        "id": SCENARIO_ID,
        "title": "Citizen self-service",
        "short_title": "Citizen self-service",
        "proves": "The portal-facing Citizen Notary can compose NIA population and CRA civil evidence.",
        "domain": "Citizen services",
        "availability": "hosted",
        "intro": "A signed-in citizen previews their own minimized status evidence.",
        "actor": "Citizen Services Portal",
        "subject": {"name": "Elena Dela Cruz", "identifier": POSITIVE_SUBJECT},
        "requester": {"name": "Citizen portal BFF", "purpose": PURPOSES["citizen_self_service"]},
        "steps": [
            {"id": "discover", "label": "Discover citizen claims", "prompt": "Read the Citizen Notary catalogue.", "button": "Discover", "request_summary": "GET /v1/claims"},
            {"id": "positive", "label": "Evaluate citizen summary", "prompt": "Evaluate the portal-facing summary.", "button": "Evaluate", "request_summary": "POST citizen self-service claims."},
            {"id": "purpose-denial", "label": "Purpose denial", "prompt": "Use an unsupported purpose.", "button": "Try denial", "request_summary": "POST with an unsupported Data-Purpose header."},
        ],
        "receipt": [
            {"label": "Credential", "value": "citizen status SD-JWT VC preview"},
            {"label": "Raw rows copied", "value": "No"},
        ],
    }


def preview_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=True)


def _request(config: dict[str, Any], step_id: str, *, send: bool) -> dict[str, Any]:
    url = service_url(SERVICE_ID, "/v1/claims" if step_id == "discover" else "/v1/evaluations")
    subject = {"positive": POSITIVE_SUBJECT, "purpose-denial": POSITIVE_SUBJECT}.get(step_id)
    purpose = request_purpose(config, step_id)
    token = service_token(SERVICE_ID)
    evaluation_format = SD_JWT_VC_FORMAT if step_id in CREDENTIAL_STEPS else CLAIM_RESULT_FORMAT
    headers = auth_headers(token, purpose, evaluation_format if step_id != "discover" else "application/json")
    body = None if step_id == "discover" else evaluation_body(subject or "", CLAIMS, scheme="solmara_uin", format=evaluation_format)
    if step_id != "discover" and not subject:
        return standard_error_result(step_id)
    request = request_source("GET" if step_id == "discover" else "POST", url, headers, body)
    if not send:
        return {"request_source": request}
    if not token:
        return missing_runtime_token(step_id, SERVICE_NAME, service_token_env(SERVICE_ID), request)
    result = http_json("GET" if step_id == "discover" else "POST", url, headers, body)
    payload = {
        "step_id": step_id,
        "friendly": friendly_result(step_id, result, FRIENDLY),
        "request_source": request,
        "response_source": source_response(result),
    }
    if step_id in CREDENTIAL_STEPS and result.status and 200 <= result.status < 300:
        payload.update(credential_attempt(service_url(SERVICE_ID, "/v1/credentials"), token, purpose, result, CREDENTIAL_PROFILE, CLAIMS, SERVICE_ID))
    return payload


def request_purpose(config: dict[str, Any], step_id: str) -> str:
    if step_id == "purpose-denial":
        return "https://id.registrystack.org/solmara/purpose/unsupported-demo-purpose"
    if isinstance(config.get("purpose_override"), str):
        return config["purpose_override"]
    return PURPOSES["citizen_self_service"]
