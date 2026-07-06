#!/usr/bin/env python3
"""Death to pension stop plus survivor benefit guided scenario."""

from __future__ import annotations

from typing import Any

from .common import CLAIM_RESULT_FORMAT, PURPOSES, SD_JWT_VC_FORMAT, auth_headers, credential_attempt, evaluation_body, friendly_result, http_json, missing_runtime_token, request_source, source_response, standard_error_result
from .service_config import service_token, service_token_env, service_url


SCENARIO_ID = "death-to-pension-survivor"
SERVICE_NAME = "Pension Notary"
SERVICE_ID = "pension-notary"
DECEASED_PENSIONER = "2300109568"
SURVIVING_SPOUSE = "2300118698"
STALE_CONTROL = "2300127827"
DISSOLVED_MARRIAGE_CONTROL = "2300146081"
STOP_PAYMENT_CLAIMS = ["person-is-deceased", "pension-payment-should-stop"]
SURVIVOR_CLAIMS = ["survivor-is-eligible"]
CREDENTIAL_PROFILE = "survivor_benefit_sd_jwt"
CREDENTIAL_STEPS = {"survivor-benefit"}
FRIENDLY = {
    "discover": {
        "met": ("The catalogue lists what may be asked.", "Claim definitions only. No pension records have moved."),
    },
    "stop-payment": {
        "met": (
            "The pension stops. The death fact was enough.",
            "SIPF learned that the pensioner is deceased and the payment should stop. It never saw the cause of death.",
        ),
        "unmet": (
            "No stop today.",
            "The death is not confirmed by the civil register, so the payment continues.",
        ),
    },
    "survivor-benefit": {
        "met": (
            "Yes. The surviving spouse can be offered the benefit.",
            "Marriage registration links the survivor to the deceased. Only the eligibility fact is disclosed.",
        ),
        "unmet": (
            "Not eligible on the facts returned.",
            "The survivor eligibility check came back not met.",
        ),
    },
    "stale-control": {
        "unmet": (
            "No death registered yet, so nothing changes.",
            "The civil register has no death record for this pensioner. The pension keeps paying until evidence exists.",
        ),
    },
    "dissolved-control": {
        "unmet": (
            "Rejected: the marriage was dissolved.",
            "The survivor check came back not met because the marriage no longer stands.",
        ),
    },
    "cause-of-death-denial": {
        "refused": (
            "Refused: that question does not even exist here.",
            "The Pension Notary offers no cause-of-death claim, so the over-disclosing question cannot be asked at all.",
        ),
    },
}


def story() -> dict[str, Any]:
    return {
        "id": SCENARIO_ID,
        "title": "Death to pension stop plus survivor benefit",
        "short_title": "Pension stop and survivor benefit",
        "proves": "Civil death evidence and SIPF enrollment can stop a pension and preview survivor-benefit eligibility.",
        "domain": "Pensions",
        "availability": "hosted",
        "intro": "SIPF reviews a death registration without requesting cause of death.",
        "actor": "SIPF payments reviewer",
        "subject": {"name": "Rafael Nkomo", "identifier": DECEASED_PENSIONER},
        "requester": {"name": "SIPF review desk", "purpose": PURPOSES["pension_payment"]},
        "steps": [
            {"id": "discover", "label": "Discover pension claims", "prompt": "Read the Pension Notary catalogue.", "button": "Discover", "request_summary": "GET /v1/claims"},
            {"id": "stop-payment", "label": "Stop pension payment", "prompt": "Evaluate the deceased pensioner.", "button": "Evaluate", "request_summary": "POST pension stop claims."},
            {"id": "survivor-benefit", "label": "Preview survivor benefit", "prompt": "Evaluate survivor eligibility linked by marriage registration.", "button": "Evaluate", "request_summary": "POST survivor benefit claim."},
            {"id": "stale-control", "label": "Death not yet registered", "prompt": "Show stale-data reconciliation.", "button": "Evaluate", "request_summary": "POST death claim for stale control UIN."},
            {"id": "dissolved-control", "label": "Dissolved marriage control", "prompt": "Reject survivor claim when the marriage was dissolved.", "button": "Evaluate", "request_summary": "POST survivor claim for dissolved-marriage control UIN."},
            {"id": "cause-of-death-denial", "label": "Purpose denial", "prompt": "Ask for cause of death and get denied.", "button": "Try denial", "request_summary": "POST over-disclosing death-cause claim."},
        ],
        "receipt": [
            {"label": "Credential", "value": "survivor-benefit eligibility VC preview"},
            {"label": "Cause of death disclosed", "value": "No"},
        ],
    }


def preview_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=True)


def _request(config: dict[str, Any], step_id: str, *, send: bool) -> dict[str, Any]:
    url = service_url(SERVICE_ID, "/v1/claims" if step_id == "discover" else "/v1/evaluations")
    subject = {
        "stop-payment": DECEASED_PENSIONER,
        "survivor-benefit": SURVIVING_SPOUSE,
        "stale-control": STALE_CONTROL,
        "dissolved-control": DISSOLVED_MARRIAGE_CONTROL,
        "cause-of-death-denial": DECEASED_PENSIONER,
    }.get(step_id)
    if step_id == "cause-of-death-denial":
        claim_ids = ["cause-of-death"]
    elif step_id in {"survivor-benefit", "dissolved-control"}:
        claim_ids = SURVIVOR_CLAIMS
    else:
        claim_ids = STOP_PAYMENT_CLAIMS
    purpose = request_purpose(config, step_id)
    token = service_token(SERVICE_ID)
    evaluation_format = SD_JWT_VC_FORMAT if step_id in CREDENTIAL_STEPS else CLAIM_RESULT_FORMAT
    headers = auth_headers(token, purpose, evaluation_format if step_id != "discover" else "application/json")
    body = None if step_id == "discover" else evaluation_body(subject or "", claim_ids, scheme="solmara_uin", format=evaluation_format)
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
        payload.update(credential_attempt(service_url(SERVICE_ID, "/v1/credentials"), token, purpose, result, CREDENTIAL_PROFILE, claim_ids, SERVICE_ID))
    return payload


def request_purpose(config: dict[str, Any], step_id: str) -> str:
    if isinstance(config.get("purpose_override"), str):
        return config["purpose_override"]
    if step_id in {"survivor-benefit", "dissolved-control"}:
        return PURPOSES["survivor_benefit"]
    return PURPOSES["pension_payment"]
