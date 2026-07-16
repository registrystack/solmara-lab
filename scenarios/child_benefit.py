#!/usr/bin/env python3
"""Birth to child benefit guided scenario."""

from __future__ import annotations

from typing import Any

from .common import (
    CHILD_BENEFIT_AS_OF_DATE,
    PURPOSES,
    auth_headers,
    evaluation_body,
    friendly_result,
    http_json,
    missing_runtime_token,
    request_source,
    source_response,
    standard_error_result,
)
from .service_config import service_token, service_token_env, service_url


SCENARIO_ID = "birth-to-child-benefit"
SERVICE_NAME = "Child Benefit Federator"
SERVICE_ID = "child-benefit-federator"
POSITIVE_SUBJECT = "2300010248"
DECEASED_CONTROL = "2300091305"
ABOVE_THRESHOLD_CONTROL = "2300036523"
UNREGISTERED_CONTROL = "2300073046"
DUPLICATE_CONTROL = "2300054788"
CLAIMS = [
    "birth-is-registered",
    "population-record-active",
    "child-age-under-5",
    "household-below-poverty-threshold",
    "not-already-enrolled",
]
FRIENDLY = {
    "discover": {
        "met": (
            "The catalogue lists what may be asked.",
            "Claim definitions only. No resident data has moved yet.",
        ),
    },
    "positive": {
        "met": (
            "Mateo's source predicates are ready for review.",
            "The application collected five source-owned facts. It did not make the benefit decision.",
        ),
        "unmet": (
            "Review cannot proceed on the facts returned.",
            "One or more source-owned checks came back not met. The programme policy layer decides what happens next.",
        ),
    },
    "deceased-control": {
        "unmet": (
            "Rejected, exactly as designed.",
            "The civil predicate fails for the deceased control case. The application only returns that fact.",
        ),
    },
    "poverty-control": {
        "unmet": (
            "Rejected: the household is above the threshold.",
            "The social registry predicate came back not met. The caseworker never sees the household's actual income.",
        ),
    },
    "unregistered-control": {
        "unmet": (
            "No birth predicate could be satisfied. Registration comes first.",
            "The civil authority returns only the minimized predicate result, not a source row.",
        ),
    },
    "duplicate-control": {
        "unmet": (
            "Rejected: already enrolled.",
            "The programme MIS predicate came back not met, preventing a double payment.",
        ),
    },
}


def story() -> dict[str, Any]:
    return {
        "id": SCENARIO_ID,
        "title": "Birth to child benefit",
        "short_title": "Child benefit",
        "proves": "Civil, population, social registry, and beneficiary evidence can be collected as source-owned predicates without copying source rows.",
        "domain": "Social protection",
        "availability": "hosted",
        "intro": "A caseworker reviews child benefit eligibility from minimized Solmara evidence.",
        "actor": "MoSD child benefit caseworker",
        "subject": {"name": "Mateo Santos", "identifier": POSITIVE_SUBJECT},
        "requester": {
            "name": "Child benefit desk",
            "purpose": PURPOSES["child_benefit"],
        },
        "steps": [
            {
                "id": "discover",
                "label": "Discover predicates",
                "prompt": "Read the child-benefit evidence catalogue.",
                "button": "Discover",
                "request_summary": "GET /v1/claims",
            },
            {
                "id": "positive",
                "label": "Collect eligible child predicates",
                "prompt": "Run the positive control.",
                "button": "Evaluate",
                "request_summary": "POST child-benefit evidence request for the positive UIN.",
            },
            {
                "id": "deceased-control",
                "label": "Deceased control",
                "prompt": "Confirm a deceased child is rejected.",
                "button": "Evaluate",
                "request_summary": "POST child-benefit claims for the deceased control UIN.",
            },
            {
                "id": "poverty-control",
                "label": "Income threshold control",
                "prompt": "Confirm an above-threshold household is rejected.",
                "button": "Evaluate",
                "request_summary": "POST child-benefit claims for the threshold control UIN.",
            },
            {
                "id": "unregistered-control",
                "label": "Unregistered birth control",
                "prompt": "Route an unregistered birth to registration first.",
                "button": "Evaluate",
                "request_summary": "POST child-benefit claims for the unregistered control UIN.",
            },
            {
                "id": "duplicate-control",
                "label": "Duplicate enrollment control",
                "prompt": "Reject an already-enrolled child.",
                "button": "Evaluate",
                "request_summary": "POST child-benefit claims for the duplicate control UIN.",
            },
            {
                "id": "purpose-denial",
                "label": "Purpose denial",
                "prompt": "Try the same request with an unsupported purpose.",
                "button": "Try denial",
                "request_summary": "POST with an unsupported Data-Purpose header.",
            },
        ],
        "receipt": [
            {
                "label": "Evidence",
                "value": "Source-owned predicates, no eligibility composition",
            },
            {"label": "Raw rows copied", "value": "No"},
        ],
    }


def preview_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=True)


def _request(config: dict[str, Any], step_id: str, *, send: bool) -> dict[str, Any]:
    url = service_url(
        SERVICE_ID, "/v1/claims" if step_id == "discover" else "/v1/evaluations"
    )
    subject = {
        "positive": POSITIVE_SUBJECT,
        "deceased-control": DECEASED_CONTROL,
        "poverty-control": ABOVE_THRESHOLD_CONTROL,
        "unregistered-control": UNREGISTERED_CONTROL,
        "duplicate-control": DUPLICATE_CONTROL,
        "purpose-denial": POSITIVE_SUBJECT,
    }.get(step_id)
    purpose = request_purpose(config, step_id)
    token = service_token(SERVICE_ID)
    headers = auth_headers(token, purpose, "application/json")
    body = (
        None
        if step_id == "discover"
        else evaluation_body(
            subject or "",
            CLAIMS,
            scheme="solmara_uin",
            format="application/json",
            variables={"as_of_date": CHILD_BENEFIT_AS_OF_DATE},
        )
    )
    if step_id != "discover" and not subject:
        return standard_error_result(step_id)
    request = request_source(
        "GET" if step_id == "discover" else "POST", url, headers, body
    )
    if not send:
        return {"request_source": request}
    if not token:
        return missing_runtime_token(
            step_id, SERVICE_NAME, service_token_env(SERVICE_ID), request
        )
    result = http_json("GET" if step_id == "discover" else "POST", url, headers, body)
    response_body = result.body if isinstance(result.body, dict) else {}
    payload = {
        "step_id": step_id,
        "friendly": friendly_result(step_id, result, FRIENDLY),
        "request_source": request,
        "response_source": source_response(result),
        "source_trace": response_body.get("source_trace", []),
    }
    return payload


def request_purpose(config: dict[str, Any], step_id: str) -> str:
    if step_id == "purpose-denial":
        return "https://id.registrystack.org/solmara/purpose/unsupported-demo-purpose"
    if isinstance(config.get("purpose_override"), str):
        return config["purpose_override"]
    return PURPOSES["child_benefit"]
