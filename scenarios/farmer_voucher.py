#!/usr/bin/env python3
"""Farmer climate-smart voucher guided scenario."""

from __future__ import annotations

from typing import Any

from .common import CLAIM_RESULT_FORMAT, PURPOSES, SD_JWT_VC_FORMAT, auth_headers, credential_attempt, evaluation_body, friendly_result, http_json, missing_runtime_token, request_source, source_response, standard_error_result
from .service_config import service_token, service_token_env, service_url


SCENARIO_ID = "farmer-climate-smart-voucher"
SERVICE_NAME = "NAgDI Notary"
SERVICE_ID = "nagdi-notary"
POSITIVE_FARMER = "FR-1001"
PARCEL_CONTROL = "FR-1002"
REDEEMED_CONTROL = "FR-1003"
CLAIMS = ["eligible-for-climate-smart-input-voucher"]
MOVEMENT_CLAIMS = ["eligible-for-livestock-movement-permit"]
VOUCHER_CREDENTIAL_PROFILE = "climate_smart_voucher_sd_jwt"
MOVEMENT_CREDENTIAL_PROFILE = "livestock_movement_sd_jwt"
CREDENTIAL_STEPS = {"positive", "movement-permit"}
FRIENDLY = {
    "discover": {
        "met": ("The catalogue lists what may be asked.", "Claim definitions only. No workbook rows have moved."),
    },
    "positive": {
        "met": (
            "Yes. This farmer qualifies for the voucher.",
            "The eligibility fact came back met. The workbook itself never left NAgDI.",
        ),
        "unmet": (
            "Not eligible on the facts returned.",
            "The voucher eligibility check came back not met for this farmer.",
        ),
    },
    "inactive-parcel-control": {
        "unmet": (
            "Rejected: the parcel is not active.",
            "The eligibility check came back not met, so no voucher is issued for an inactive parcel.",
        ),
    },
    "redeemed-control": {
        "unmet": (
            "Rejected: already redeemed this season.",
            "The eligibility check came back not met, preventing a double redemption.",
        ),
    },
    "movement-permit": {
        "met": (
            "Yes. The movement permit can be issued.",
            "The livestock movement fact came back met under its own purpose.",
        ),
        "unmet": (
            "No permit on the facts returned.",
            "The movement-control check came back not met.",
        ),
    },
}


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
    return _request(config, step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=True)


def _request(config: dict[str, Any], step_id: str, *, send: bool) -> dict[str, Any]:
    url = service_url(SERVICE_ID, "/v1/claims" if step_id == "discover" else "/v1/evaluations")
    subject = {
        "positive": POSITIVE_FARMER,
        "inactive-parcel-control": PARCEL_CONTROL,
        "redeemed-control": REDEEMED_CONTROL,
        "movement-permit": POSITIVE_FARMER,
        "purpose-denial": POSITIVE_FARMER,
    }.get(step_id)
    claims = MOVEMENT_CLAIMS if step_id in {"movement-permit", "purpose-denial"} else CLAIMS
    purpose = request_purpose(config, step_id)
    token = service_token(SERVICE_ID)
    credential_profile = credential_profile_for_step(step_id)
    evaluation_format = SD_JWT_VC_FORMAT if step_id in CREDENTIAL_STEPS else CLAIM_RESULT_FORMAT
    headers = auth_headers(token, purpose, evaluation_format if step_id != "discover" else "application/json")
    body = None if step_id == "discover" else evaluation_body(subject or "", claims, scheme="farmer_id", format=evaluation_format)
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
    if credential_profile and result.status and 200 <= result.status < 300:
        payload.update(credential_attempt(service_url(SERVICE_ID, "/v1/credentials"), token, purpose, result, credential_profile, claims, SERVICE_ID))
    return payload


def credential_profile_for_step(step_id: str) -> str | None:
    if step_id == "positive":
        return VOUCHER_CREDENTIAL_PROFILE
    if step_id == "movement-permit":
        return MOVEMENT_CREDENTIAL_PROFILE
    return None


def request_purpose(config: dict[str, Any], step_id: str) -> str:
    if step_id == "purpose-denial":
        return PURPOSES["voucher"]
    if isinstance(config.get("purpose_override"), str):
        return config["purpose_override"]
    if step_id == "movement-permit":
        return PURPOSES["livestock"]
    return PURPOSES["voucher"]
