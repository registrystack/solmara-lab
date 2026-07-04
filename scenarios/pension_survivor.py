#!/usr/bin/env python3
"""Death to pension stop plus survivor benefit guided scenario."""

from __future__ import annotations

import os
from typing import Any

from .common import CLAIM_RESULT_FORMAT, PURPOSES, auth_headers, env_url, evaluation_body, http_json, missing_runtime_token, request_source, source_response, standard_error_result


SCENARIO_ID = "death-to-pension-survivor"
SERVICE_NAME = "Pension Notary"
URL_ENV = "PENSION_NOTARY_URL"
TOKEN_ENV = "PENSION_NOTARY_TOKEN"
DEFAULT_URL = "http://127.0.0.1:4322"
DECEASED_PENSIONER = "2300109568"
SURVIVING_SPOUSE = "2300118698"
STALE_CONTROL = "2300127827"
DISSOLVED_MARRIAGE_CONTROL = "2300146081"
STOP_PAYMENT_CLAIMS = ["person-is-deceased", "pension-payment-should-stop"]
SURVIVOR_CLAIMS = ["survivor-is-eligible"]


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
    return _request(step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(step_id, send=True)


def _request(step_id: str, *, send: bool) -> dict[str, Any]:
    url = env_url(URL_ENV, DEFAULT_URL, "/v1/claims" if step_id == "discover" else "/v1/evaluations")
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
    purpose = PURPOSES["survivor_benefit"] if step_id in {"survivor-benefit", "dissolved-control"} else PURPOSES["pension_payment"]
    token = os.environ.get(TOKEN_ENV, "")
    headers = auth_headers(token, purpose, CLAIM_RESULT_FORMAT if step_id != "discover" else "application/json")
    body = None if step_id == "discover" else evaluation_body(subject or "", claim_ids, scheme="solmara_uin")
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
            "message": "The evidence response should disclose the death fact, not medical cause.",
            "status": "done" if result.status and 200 <= result.status < 300 else "needs_attention",
            "facts": [{"label": "HTTP status", "value": result.status if result.status is not None else "No response"}],
        },
        "request_source": request,
        "response_source": source_response(result),
    }
