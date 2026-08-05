#!/usr/bin/env python3
"""Death-to-pension-stop and survivor Evidence scenario."""

from __future__ import annotations

from typing import Any

from .common import PURPOSES, StepHttpResult, evidence_body, evidence_headers, friendly_result, http_json, missing_runtime_token, normalized_evidence_result, request_source, source_response, standard_error_result
from .service_config import requirement_id, service_token, service_token_env, service_url


SCENARIO_ID = "death-to-pension-survivor"
SERVICE_NAME = "Registry Evidence"
DECEASED_PENSIONER = "2300109568"
SURVIVING_SPOUSE = "2300118698"
STALE_CONTROL = "2300127827"
DISSOLVED_MARRIAGE_CONTROL = "2300146081"
AUTHORITY_NAMES = {"cra-pension": "Civil Registration Authority", "sipf-pension": "Social Insurance and Pensions Fund", "sipf-survivor": "Social Insurance and Pensions Fund"}
FRIENDLY = {
    "stop-payment": {"met": ("The pension stops.", "The application combined two signed values while each authority kept its source row.")},
    "survivor-benefit": {"met": ("Yes. The surviving spouse can be offered the benefit.", "SIPF returned only the reviewed survivor concept.")},
    "stale-control": {"unmet": ("No death registered yet, so nothing changes.", "The application does not infer a death from an unresolved requirement.")},
    "dissolved-control": {"unmet": ("Rejected: the marriage was dissolved.", "SIPF returned a signed false survivor value.")},
    "cause-of-death-denial": {"refused": ("Refused: that requirement does not exist here.", "Cause of death cannot be requested through this Evidence bundle.")},
}


def story() -> dict[str, Any]:
    return {"id": SCENARIO_ID, "title": "Death to pension stop plus survivor benefit", "short_title": "Pension stop and survivor benefit", "proves": "CRA and SIPF signed evidence can drive an application decision without a cross-authority decision service.", "domain": "Pensions", "availability": "local", "intro": "SIPF reviews death evidence without requesting cause of death.", "actor": "SIPF payments reviewer", "subject": {"name": "Rafael Nkomo", "identifier": DECEASED_PENSIONER}, "requester": {"name": "SIPF review desk", "purpose": PURPOSES["pension_payment"]}, "steps": [{"id": "discover", "label": "Discover pension requirements", "prompt": "Read Evidence definitions.", "button": "Discover", "request_summary": "GET /v1/evidence-definitions"}, {"id": "stop-payment", "label": "Stop pension payment", "prompt": "Evaluate the deceased pensioner.", "button": "Evaluate", "request_summary": "POST CRA death and SIPF active-payment requirements."}, {"id": "survivor-benefit", "label": "Preview survivor benefit", "prompt": "Evaluate survivor eligibility.", "button": "Evaluate", "request_summary": "POST SIPF survivor requirement."}, {"id": "stale-control", "label": "Death not yet registered", "prompt": "Show stale-data reconciliation.", "button": "Evaluate", "request_summary": "POST CRA and SIPF requirements."}, {"id": "dissolved-control", "label": "Dissolved marriage control", "prompt": "Reject survivor eligibility.", "button": "Evaluate", "request_summary": "POST SIPF survivor requirement."}, {"id": "cause-of-death-denial", "label": "Requirement denial", "prompt": "Ask for cause of death and get denied.", "button": "Try denial", "request_summary": "POST an unconfigured requirement."}], "receipt": [{"label": "Artifact", "value": "Signed Evidence JWS"}, {"label": "Cause of death disclosed", "value": "No"}]}


def preview_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=True)


def _request(config: dict[str, Any], step_id: str, *, send: bool) -> dict[str, Any]:
    subject = {"stop-payment": DECEASED_PENSIONER, "survivor-benefit": SURVIVING_SPOUSE, "stale-control": STALE_CONTROL, "dissolved-control": DISSOLVED_MARRIAGE_CONTROL, "cause-of-death-denial": DECEASED_PENSIONER}.get(step_id)
    if step_id != "discover" and subject is None:
        return standard_error_result(step_id)
    token = service_token("cra-pension") if send else ""
    purpose = request_purpose(config, step_id)
    requests = _requests(step_id, subject or "", purpose, token)
    preview = requests[0]["source"] if len(requests) == 1 else {"method": "MULTI", "url": "solmara://registry-evidence", "purpose": purpose, "requests": [item["source"] for item in requests]}
    if not send:
        return {"request_source": preview}
    if not token:
        return missing_runtime_token(step_id, SERVICE_NAME, service_token_env("cra-pension"), preview)
    responses = [(item, normalized_evidence_result(http_json(item["method"], item["url"], item["headers"], item["body"]))) for item in requests]
    aggregate = _aggregate(responses)
    payload: dict[str, Any] = {"step_id": step_id, "friendly": friendly_result(step_id, aggregate, FRIENDLY), "request_source": preview, "request_sources": [item["source"] for item, _ in responses], "response_source": source_response(aggregate), "source_trace": [{"authority": AUTHORITY_NAMES.get(item["client_id"], "Registry Evidence"), "service_id": "registry-evidence", "status": response.status} for item, response in responses]}
    if step_id in {"stop-payment", "stale-control"} and aggregate.status == 200:
        values = {item.get("claim_id"): item.get("satisfied") for item in aggregate.body.get("results", [])}
        payload["derived_decisions"] = {"pension-payment-should-stop": values.get("person-is-deceased") is True and values.get("pension-payment-active") is True, "owner": "pension-review-application"}
    return payload


def _requests(step_id: str, subject: str, purpose: str, token: str) -> list[dict[str, Any]]:
    if step_id == "discover":
        url = service_url("cra-pension", "/v1/evidence-definitions")
        headers = evidence_headers(token, discover=True)
        return [{"client_id": "cra-pension", "method": "GET", "url": url, "headers": headers, "body": None, "source": request_source("GET", url, headers)}]
    clients = ["cra-pension", "sipf-pension"] if step_id in {"stop-payment", "stale-control"} else ["sipf-survivor"]
    if step_id == "cause-of-death-denial":
        clients = ["cra-pension"]
    items = []
    for client in clients:
        url = service_url(client)
        headers = evidence_headers(token)
        requirement = "https://id.registrystack.org/solmara/requirement/cra-cause-of-death/v1" if step_id == "cause-of-death-denial" else requirement_id(client)
        body = evidence_body(subject, requirement, purpose)
        items.append({"client_id": client, "method": "POST", "url": url, "headers": headers, "body": body, "source": request_source("POST", url, headers, body)})
    return items


def _aggregate(responses: list[tuple[dict[str, Any], StepHttpResult]]) -> StepHttpResult:
    failed = next((response for _, response in responses if response.status is None or not 200 <= response.status < 300), None)
    if failed:
        return failed
    results = [entry for _, response in responses for entry in response.body.get("results", [])]
    return StepHttpResult(200, {"results": results, "signed_evidence": [response.body.get("signed_evidence") for _, response in responses]}, {"content-type": "application/json"})


def request_purpose(config: dict[str, Any], step_id: str) -> str:
    if isinstance(config.get("purpose_override"), str):
        return config["purpose_override"]
    return PURPOSES["survivor_benefit"] if step_id in {"survivor-benefit", "dissolved-control"} else PURPOSES["pension_payment"]
