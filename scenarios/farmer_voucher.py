#!/usr/bin/env python3
"""Farmer climate-smart voucher guided scenario."""

from __future__ import annotations

import os
from typing import Any

from .common import CLAIM_RESULT_FORMAT, PURPOSES, auth_headers, env_url, evaluation_body, http_json, missing_runtime_token, request_source, source_response, standard_error_result


SCENARIO_ID = "farmer-climate-smart-voucher"
SERVICE_NAME = "NAgDI Notary"
URL_ENV = "NAGDI_NOTARY_URL"
TOKEN_ENV = "NAGDI_NOTARY_TOKEN"
DEFAULT_URL = "http://127.0.0.1:4323"
POSITIVE_FARMER = "FR-1001"
PARCEL_CONTROL = "FR-1002"
REDEEMED_CONTROL = "FR-1003"
CLAIMS = ["eligible-for-climate-smart-input-voucher"]
MOVEMENT_CLAIMS = ["eligible-for-livestock-movement-permit"]


def story() -> dict[str, Any]:
    return {
        "id": SCENARIO_ID,
        "title": "Farmer climate-smart voucher",
        "short_title": "Farmer voucher",
        "proves": "NAgDI farmer and livestock workbooks can back governed voucher and movement-control APIs.",
        "domain": "Agriculture",
        "availability": "hosted",
        "intro": "A supplier checks voucher eligibility without receiving farmer or livestock workbooks.",
        "actor": "Voucher redemption desk",
        "subject": {"name": "Amina Kone", "identifier": POSITIVE_FARMER},
        "requester": {"name": "NAgDI voucher desk", "purpose": PURPOSES["voucher"]},
        "steps": [
            {"id": "discover", "label": "Discover NAgDI claims", "prompt": "Read the NAgDI claim catalogue.", "button": "Discover", "request_summary": "GET /v1/claims"},
            {"id": "positive", "label": "Evaluate voucher eligibility", "prompt": "Run the positive farmer control.", "button": "Evaluate", "request_summary": "POST voucher claim for FR-1001."},
            {"id": "inactive-parcel-control", "label": "Inactive parcel control", "prompt": "Reject an inactive parcel control.", "button": "Evaluate", "request_summary": "POST voucher claim for FR-1002."},
            {"id": "redeemed-control", "label": "Already redeemed control", "prompt": "Reject an already-redeemed farmer.", "button": "Evaluate", "request_summary": "POST voucher claim for FR-1003."},
            {"id": "movement-permit", "label": "Livestock movement permit", "prompt": "Evaluate the companion movement-control claim.", "button": "Evaluate", "request_summary": "POST livestock movement-control claim."},
            {"id": "purpose-denial", "label": "Purpose denial", "prompt": "Use the wrong purpose for a movement-control request.", "button": "Try denial", "request_summary": "POST livestock claim with voucher purpose."},
        ],
        "receipt": [
            {"label": "Credential", "value": "voucher eligibility VC preview"},
            {"label": "Workbook exported", "value": "No"},
        ],
    }


def preview_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(step_id, send=True)


def _request(step_id: str, *, send: bool) -> dict[str, Any]:
    url = env_url(URL_ENV, DEFAULT_URL, "/v1/claims" if step_id == "discover" else "/v1/evaluations")
    subject = {
        "positive": POSITIVE_FARMER,
        "inactive-parcel-control": PARCEL_CONTROL,
        "redeemed-control": REDEEMED_CONTROL,
        "movement-permit": POSITIVE_FARMER,
        "purpose-denial": POSITIVE_FARMER,
    }.get(step_id)
    claims = MOVEMENT_CLAIMS if step_id in {"movement-permit", "purpose-denial"} else CLAIMS
    purpose = PURPOSES["voucher"] if step_id != "movement-permit" else PURPOSES["livestock"]
    token = os.environ.get(TOKEN_ENV, "")
    headers = auth_headers(token, purpose, CLAIM_RESULT_FORMAT if step_id != "discover" else "application/json")
    body = None if step_id == "discover" else evaluation_body(subject or "", claims, scheme="farmer_id")
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
            "message": "The response should prove the voucher or movement-control fact without exporting workbook rows.",
            "status": "done" if result.status and 200 <= result.status < 300 else "needs_attention",
            "facts": [{"label": "HTTP status", "value": result.status if result.status is not None else "No response"}],
        },
        "request_source": request,
        "response_source": source_response(result),
    }
