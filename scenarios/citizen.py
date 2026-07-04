#!/usr/bin/env python3
"""Citizen self-service guided scenario."""

from __future__ import annotations

import os
from typing import Any

from .common import (
    CLAIM_RESULT_FORMAT,
    PURPOSES,
    auth_headers,
    env_url,
    evaluation_body,
    http_json,
    missing_runtime_token,
    request_source,
    source_response,
    standard_error_result,
)


SCENARIO_ID = "citizen-self-service"
SERVICE_NAME = "Citizen Notary"
URL_ENV = "PORTAL_CITIZEN_NOTARY_URL"
TOKEN_ENV = "PORTAL_CITIZEN_NOTARY_TOKEN"
DEFAULT_URL = "http://127.0.0.1:4324"
POSITIVE_SUBJECT = "2300018263"
CLAIMS = ["population-record-active", "civil-record-linked", "citizen-self-service-summary"]


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
    return _request(step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(step_id, send=True)


def _request(step_id: str, *, send: bool) -> dict[str, Any]:
    url = env_url(URL_ENV, DEFAULT_URL, "/v1/claims" if step_id == "discover" else "/v1/evaluations")
    subject = {"positive": POSITIVE_SUBJECT, "purpose-denial": POSITIVE_SUBJECT}.get(step_id)
    purpose = (
        "https://id.registrystack.org/solmara/purpose/unsupported-demo-purpose"
        if step_id == "purpose-denial"
        else PURPOSES["citizen_self_service"]
    )
    token = os.environ.get(TOKEN_ENV, "")
    headers = auth_headers(token, purpose, CLAIM_RESULT_FORMAT if step_id != "discover" else "application/json")
    body = None if step_id == "discover" else evaluation_body(subject or "", CLAIMS, scheme="solmara_uin")
    if step_id != "discover" and not subject:
        return standard_error_result(step_id)
    request = request_source("GET" if step_id == "discover" else "POST", url, headers, body)
    if not send:
        return {"request_source": request}
    if not token:
        return missing_runtime_token(step_id, SERVICE_NAME, TOKEN_ENV, request)
    result = http_json("GET" if step_id == "discover" else "POST", url, headers, body)
    return {
        "step_id": step_id,
        "friendly": {
            "title": "Request completed." if result.status and 200 <= result.status < 300 else "Request needs attention.",
            "message": "The response is minimized to citizen-facing claim results and denial codes.",
            "status": "done" if result.status and 200 <= result.status < 300 else "needs_attention",
            "facts": [{"label": "HTTP status", "value": result.status if result.status is not None else "No response"}],
        },
        "request_source": request,
        "response_source": source_response(result),
    }
