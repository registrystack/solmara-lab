#!/usr/bin/env python3
"""Farmer voucher and livestock Evidence scenario."""

from __future__ import annotations

from typing import Any

from .common import PURPOSES, evidence_body, evidence_headers, friendly_result, http_json, missing_runtime_token, normalized_evidence_result, request_source, safe_evidence_projection, source_response, standard_error_result
from .service_config import authority_service_id, requirement_config, requirement_id, service_token, service_token_env, service_url


SCENARIO_ID = "farmer-climate-smart-voucher"
SERVICE_NAME = "Registry Evidence"
POSITIVE_FARMER = "FR-1001"
AUTHORIZATION_CONTROL = "FR-1002"
REDEEMED_CONTROL = "FR-1003"
FRIENDLY = {
    "positive": {"met": ("Yes. This farmer qualifies for the voucher.", "The signed assertion carries reviewed concept values, not a workbook row.")},
    "authorization-control": {"unmet": ("Rejected: no data-use authorization on file.", "Evidence returned a signed false eligibility value.")},
    "redeemed-control": {"unmet": ("Rejected: already redeemed this season.", "The signed false value prevents double redemption.")},
    "movement-permit": {"met": ("Yes. The movement permit can be issued.", "The livestock requirement was evaluated under its own purpose.")},
    "purpose-denial": {"refused": ("Refused, exactly as designed.", "The voucher purpose cannot authorize the livestock requirement.")},
}


def story() -> dict[str, Any]:
    return {"id": SCENARIO_ID, "title": "Farmer climate-smart voucher", "short_title": "Farmer voucher", "proves": "NAgDI workbooks can back governed Evidence requirements without workbook export.", "domain": "Agriculture", "availability": "local", "intro": "A supplier checks a minimized signed assertion.", "actor": "Voucher redemption desk", "subject": {"name": "Amina Kone", "identifier": POSITIVE_FARMER}, "requester": {"name": "NAgDI voucher desk", "purpose": PURPOSES["voucher"]}, "steps": [{"id": "discover", "label": "Discover NAgDI requirements", "prompt": "Read Evidence definitions.", "button": "Discover", "request_summary": "GET /v1/evidence-definitions"}, {"id": "positive", "label": "Evaluate voucher eligibility", "prompt": "Run the positive control.", "button": "Evaluate", "request_summary": "POST voucher Evidence requirement."}, {"id": "authorization-control", "label": "Missing authorization control", "prompt": "Reject missing data-use authorization.", "button": "Evaluate", "request_summary": "POST voucher Evidence requirement."}, {"id": "redeemed-control", "label": "Already redeemed control", "prompt": "Reject an already-redeemed farmer.", "button": "Evaluate", "request_summary": "POST voucher Evidence requirement."}, {"id": "movement-permit", "label": "Livestock movement permit", "prompt": "Evaluate movement control.", "button": "Evaluate", "request_summary": "POST livestock Evidence requirement."}, {"id": "purpose-denial", "label": "Purpose denial", "prompt": "Use the wrong purpose.", "button": "Try denial", "request_summary": "POST livestock requirement with voucher purpose."}], "receipt": [{"label": "Artifact", "value": "Signed Evidence JWS"}, {"label": "Workbook exported", "value": "No"}]}


def preview_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=True)


def _request(config: dict[str, Any], step_id: str, *, send: bool) -> dict[str, Any]:
    subjects = {"positive": POSITIVE_FARMER, "authorization-control": AUTHORIZATION_CONTROL, "redeemed-control": REDEEMED_CONTROL, "movement-permit": POSITIVE_FARMER, "purpose-denial": POSITIVE_FARMER}
    if step_id != "discover" and step_id not in subjects:
        return standard_error_result(step_id)
    client = "nagdi-livestock" if step_id in {"movement-permit", "purpose-denial"} else "nagdi-voucher"
    token = service_token(client) if send else ""
    purpose = request_purpose(config, step_id)
    url = service_url(client, "/v1/evidence-definitions" if step_id == "discover" else "/v1/evidence")
    headers = evidence_headers(token, discover=step_id == "discover")
    body = None if step_id == "discover" else evidence_body(subjects[step_id], requirement_id(client), purpose, selector_profile="farmer-reference-v1", selector_field="farmer_id")
    request = request_source("GET" if step_id == "discover" else "POST", url, headers, body)
    if not send:
        return {"request_source": request}
    if not token:
        return missing_runtime_token(step_id, SERVICE_NAME, service_token_env(client), request)
    raw = http_json("GET" if step_id == "discover" else "POST", url, headers, body)
    result = raw if step_id == "discover" else normalized_evidence_result(raw, request=body, service_id=client)
    config = requirement_config(client)
    trace = {"authority": config["name"], "service_id": authority_service_id(client), "issuer": config["issuer"], "provider": config["provider"], "source": config["source"], "status": result.status}
    projection = safe_evidence_projection(result)
    return {"step_id": step_id, "friendly": friendly_result(step_id, result, FRIENDLY), "request_source": request, "response_source": source_response(result), "source_trace": [trace], **projection}


def request_purpose(config: dict[str, Any], step_id: str) -> str:
    if step_id == "purpose-denial":
        return PURPOSES["voucher"]
    if isinstance(config.get("purpose_override"), str):
        return config["purpose_override"]
    return PURPOSES["livestock"] if step_id == "movement-permit" else PURPOSES["voucher"]
