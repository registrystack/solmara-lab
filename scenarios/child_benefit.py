#!/usr/bin/env python3
"""Birth-to-child-benefit guided scenario through the application collector."""

from __future__ import annotations

from typing import Any

from .common import CHILD_BENEFIT_AS_OF_DATE, PURPOSES, friendly_result, http_json, missing_runtime_token, request_source, source_response, standard_error_result
from .service_config import service_token, service_token_env, service_url


SCENARIO_ID = "birth-to-child-benefit"
SERVICE_NAME = "Child Benefit Evidence Collector"
SERVICE_ID = "child-benefit-federator"
POSITIVE_SUBJECT = "2300010248"
DECEASED_CONTROL = "2300091305"
ABOVE_THRESHOLD_CONTROL = "2300036523"
UNREGISTERED_CONTROL = "2300073046"
DUPLICATE_CONTROL = "2300054788"
CLAIMS = ["birth-is-registered", "population-record-active", "child-age-under-5", "household-below-poverty-threshold", "not-already-enrolled"]
FRIENDLY = {
    "positive": {"met": ("Mateo's signed source evidence is ready.", "Evidence evaluated five reviewed requirements without copying authority rows.")},
    "deceased-control": {"unmet": ("Rejected, exactly as designed.", "The civil evidence says the child is not active for this review.")},
    "poverty-control": {"unmet": ("Rejected: the household is above the threshold.", "Only the reviewed poverty predicate was disclosed.")},
    "unregistered-control": {"unmet": ("Registration comes first.", "No registered-birth evidence was asserted.")},
    "duplicate-control": {"unmet": ("Rejected: already enrolled.", "The programme evidence prevents a duplicate payment.")},
    "purpose-denial": {"refused": ("Refused, exactly as designed.", "The unsupported purpose matched no Evidence grant.")},
}


def story() -> dict[str, Any]:
    return {
        "id": SCENARIO_ID,
        "title": "Birth to child benefit",
        "short_title": "Child benefit",
        "proves": "One application can collect separately signed CRA, NIA, SRO, and MoSD evidence without copying source rows.",
        "domain": "Social protection",
        "availability": "local",
        "intro": "A caseworker reviews minimized Registry Evidence assertions.",
        "actor": "MoSD child benefit caseworker",
        "subject": {"name": "Mateo Santos", "identifier": POSITIVE_SUBJECT},
        "requester": {"name": "Child benefit desk", "purpose": PURPOSES["child_benefit"]},
        "steps": [
            {"id": "discover", "label": "Discover requirements", "prompt": "Read the Evidence definitions.", "button": "Discover", "request_summary": "GET /v1/evidence-definitions"},
            {"id": "positive", "label": "Collect eligible child evidence", "prompt": "Run the positive control.", "button": "Evaluate", "request_summary": "POST five Evidence requirements."},
            {"id": "deceased-control", "label": "Deceased control", "prompt": "Confirm a deceased child is rejected.", "button": "Evaluate", "request_summary": "POST child-benefit requirements."},
            {"id": "poverty-control", "label": "Income threshold control", "prompt": "Confirm an above-threshold household is rejected.", "button": "Evaluate", "request_summary": "POST child-benefit requirements."},
            {"id": "unregistered-control", "label": "Unregistered birth control", "prompt": "Route an unregistered birth to registration first.", "button": "Evaluate", "request_summary": "POST child-benefit requirements."},
            {"id": "duplicate-control", "label": "Duplicate enrollment control", "prompt": "Reject an already-enrolled child.", "button": "Evaluate", "request_summary": "POST child-benefit requirements."},
            {"id": "purpose-denial", "label": "Purpose denial", "prompt": "Try an unsupported purpose.", "button": "Try denial", "request_summary": "POST with an unsupported purpose."},
        ],
        "receipt": [{"label": "Evidence", "value": "Flattened signed JWS assertions"}, {"label": "Raw rows copied", "value": "No"}],
    }


def preview_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=True)


def _request(config: dict[str, Any], step_id: str, *, send: bool) -> dict[str, Any]:
    subject = {"positive": POSITIVE_SUBJECT, "deceased-control": DECEASED_CONTROL, "poverty-control": ABOVE_THRESHOLD_CONTROL, "unregistered-control": UNREGISTERED_CONTROL, "duplicate-control": DUPLICATE_CONTROL, "purpose-denial": POSITIVE_SUBJECT}.get(step_id)
    if step_id != "discover" and not subject:
        return standard_error_result(step_id)
    token = service_token(SERVICE_ID) if send else ""
    purpose = "unsupported-demo-purpose" if step_id == "purpose-denial" else str(config.get("purpose_override") or PURPOSES["child_benefit"])
    url = service_url(SERVICE_ID, "/v1/claims" if step_id == "discover" else "/v1/evaluations")
    headers = {"x-api-key": token, "Accept": "application/json", "Data-Purpose": purpose}
    body = None if step_id == "discover" else {"target": {"type": "Person", "identifiers": [{"scheme": "solmara_uin", "value": subject}]}, "claims": CLAIMS, "disclosure": "predicate", "format": "application/json", "variables": {"as_of_date": CHILD_BENEFIT_AS_OF_DATE}}
    request = request_source("GET" if step_id == "discover" else "POST", url, headers, body)
    if not send:
        return {"request_source": request}
    if not token:
        return missing_runtime_token(step_id, SERVICE_NAME, service_token_env(SERVICE_ID), request)
    result = http_json("GET" if step_id == "discover" else "POST", url, headers, body)
    response_body = result.body if isinstance(result.body, dict) else {}
    return {"step_id": step_id, "friendly": friendly_result(step_id, result, FRIENDLY), "request_source": request, "response_source": source_response(result), "source_trace": response_body.get("source_trace", [])}


def request_purpose(config: dict[str, Any], step_id: str) -> str:
    return "unsupported-demo-purpose" if step_id == "purpose-denial" else str(config.get("purpose_override") or PURPOSES["child_benefit"])
