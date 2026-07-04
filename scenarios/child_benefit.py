#!/usr/bin/env python3
"""Birth to child benefit guided scenario."""

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


SCENARIO_ID = "birth-to-child-benefit"
SERVICE_NAME = "Child Benefit Notary"
URL_ENV = "CHILD_BENEFIT_NOTARY_URL"
TOKEN_ENV = "CHILD_BENEFIT_NOTARY_TOKEN"
DEFAULT_URL = "http://127.0.0.1:4321"
POSITIVE_SUBJECT = "2300010248"
DECEASED_CONTROL = "2300091305"
ABOVE_THRESHOLD_CONTROL = "2300036523"
UNREGISTERED_CONTROL = "2300073046"
DUPLICATE_CONTROL = "2300054788"
CLAIMS = [
    "birth-is-registered",
    "child-age-under-5",
    "household-below-poverty-threshold",
    "not-already-enrolled",
]


def story() -> dict[str, Any]:
    return {
        "id": SCENARIO_ID,
        "title": "Birth to child benefit",
        "short_title": "Child benefit",
        "proves": "Civil, population, social registry, and beneficiary evidence can decide child-benefit eligibility without copying source rows.",
        "domain": "Social protection",
        "availability": "hosted",
        "intro": "A caseworker reviews child benefit eligibility from minimized Solmara evidence.",
        "actor": "MoSD child benefit caseworker",
        "subject": {"name": "Mateo Santos", "identifier": POSITIVE_SUBJECT},
        "requester": {"name": "Child benefit desk", "purpose": PURPOSES["child_benefit"]},
        "steps": [
            {"id": "discover", "label": "Discover claims", "prompt": "Read the Notary claim catalogue.", "button": "Discover", "request_summary": "GET /v1/claims"},
            {"id": "positive", "label": "Evaluate eligible child", "prompt": "Run the positive control.", "button": "Evaluate", "request_summary": "POST child-benefit claims for the positive UIN."},
            {"id": "deceased-control", "label": "Deceased control", "prompt": "Confirm a deceased child is rejected.", "button": "Evaluate", "request_summary": "POST child-benefit claims for the deceased control UIN."},
            {"id": "poverty-control", "label": "Income threshold control", "prompt": "Confirm an above-threshold household is rejected.", "button": "Evaluate", "request_summary": "POST child-benefit claims for the threshold control UIN."},
            {"id": "unregistered-control", "label": "Unregistered birth control", "prompt": "Route an unregistered birth to registration first.", "button": "Evaluate", "request_summary": "POST child-benefit claims for the unregistered control UIN."},
            {"id": "duplicate-control", "label": "Duplicate enrollment control", "prompt": "Reject an already-enrolled child.", "button": "Evaluate", "request_summary": "POST child-benefit claims for the duplicate control UIN."},
            {"id": "purpose-denial", "label": "Purpose denial", "prompt": "Try the same request with an unsupported purpose.", "button": "Try denial", "request_summary": "POST with an unsupported Data-Purpose header."},
        ],
        "receipt": [
            {"label": "Credential", "value": "enrollment-eligibility SD-JWT VC preview"},
            {"label": "Raw rows copied", "value": "No"},
        ],
    }


def preview_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(step_id, send=True)


def _request(step_id: str, *, send: bool) -> dict[str, Any]:
    url = env_url(URL_ENV, DEFAULT_URL, "/v1/claims" if step_id == "discover" else "/v1/evaluations")
    subject = {
        "positive": POSITIVE_SUBJECT,
        "deceased-control": DECEASED_CONTROL,
        "poverty-control": ABOVE_THRESHOLD_CONTROL,
        "unregistered-control": UNREGISTERED_CONTROL,
        "duplicate-control": DUPLICATE_CONTROL,
        "purpose-denial": POSITIVE_SUBJECT,
    }.get(step_id)
    purpose = "https://id.registrystack.org/solmara/purpose/unsupported-demo-purpose" if step_id == "purpose-denial" else PURPOSES["child_benefit"]
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
            "message": "The response is minimized to claim results and denial codes.",
            "status": "done" if result.status and 200 <= result.status < 300 else "needs_attention",
            "facts": [{"label": "HTTP status", "value": result.status if result.status is not None else "No response"}],
        },
        "request_source": request,
        "response_source": source_response(result),
    }
