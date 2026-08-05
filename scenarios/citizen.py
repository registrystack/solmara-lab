#!/usr/bin/env python3
"""Citizen self-service Evidence scenario."""

from __future__ import annotations

from typing import Any

from .common import PURPOSES, StepHttpResult, evidence_body, evidence_headers, friendly_result, http_json, missing_runtime_token, normalized_evidence_result, request_source, source_response, standard_error_result
from .service_config import requirement_id, service_token, service_token_env, service_url


SCENARIO_ID = "citizen-self-service"
SERVICE_NAME = "Registry Evidence"
POSITIVE_SUBJECT = "2300018263"
CLIENTS = ("cra-citizen", "nia-citizen")
AUTHORITY_NAMES = {"cra-citizen": "Civil Registration Authority", "nia-citizen": "National Identity Agency"}
FRIENDLY = {"positive": {"met": ("Elena's signed status evidence is ready.", "CRA and NIA released separate reviewed concept values.")}, "purpose-denial": {"refused": ("Refused, exactly as designed.", "No grant permits that purpose.")}}


def story() -> dict[str, Any]:
    return {"id": SCENARIO_ID, "title": "Citizen self-service", "short_title": "Citizen self-service", "proves": "The portal can present separate CRA and NIA signed evidence through one Evidence service.", "domain": "Citizen services", "availability": "local", "intro": "A signed-in citizen previews minimized evidence.", "actor": "Citizen Services Portal", "subject": {"name": "Elena Dela Cruz", "identifier": POSITIVE_SUBJECT}, "requester": {"name": "Citizen portal BFF", "purpose": PURPOSES["citizen_self_service"]}, "steps": [{"id": "discover", "label": "Discover citizen requirements", "prompt": "Read the Evidence definitions.", "button": "Discover", "request_summary": "GET /v1/evidence-definitions"}, {"id": "positive", "label": "Evaluate citizen status", "prompt": "Evaluate CRA and NIA requirements.", "button": "Evaluate", "request_summary": "POST two Evidence requirements."}, {"id": "purpose-denial", "label": "Purpose denial", "prompt": "Use an unsupported purpose.", "button": "Try denial", "request_summary": "POST with an unsupported purpose."}], "receipt": [{"label": "Artifact", "value": "Two signed Evidence JWS assertions"}, {"label": "Raw rows copied", "value": "No"}]}


def preview_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=True)


def _request(config: dict[str, Any], step_id: str, *, send: bool) -> dict[str, Any]:
    if step_id not in {"discover", "positive", "purpose-denial"}:
        return standard_error_result(step_id)
    token = service_token("cra-citizen") if send else ""
    purpose = "unsupported-demo-purpose" if step_id == "purpose-denial" else str(config.get("purpose_override") or PURPOSES["citizen_self_service"])
    requests = _requests(step_id, POSITIVE_SUBJECT, purpose, token)
    preview = _preview(requests, purpose)
    if not send:
        return {"request_source": preview}
    if not token:
        return missing_runtime_token(step_id, SERVICE_NAME, service_token_env("cra-citizen"), preview)
    responses = [(item, normalized_evidence_result(http_json(item["method"], item["url"], item["headers"], item["body"]))) for item in requests]
    aggregate = _aggregate(responses)
    return {"step_id": step_id, "friendly": friendly_result(step_id, aggregate, FRIENDLY), "request_source": preview, "request_sources": [item["source"] for item, _ in responses], "response_source": source_response(aggregate), "source_trace": [{"authority": AUTHORITY_NAMES[item["client_id"]], "service_id": "registry-evidence", "status": response.status} for item, response in responses]}


def _requests(step_id: str, subject: str, purpose: str, token: str) -> list[dict[str, Any]]:
    if step_id == "discover":
        url = service_url("cra-citizen", "/v1/evidence-definitions")
        headers = evidence_headers(token, discover=True)
        return [{"client_id": "cra-citizen", "method": "GET", "url": url, "headers": headers, "body": None, "source": request_source("GET", url, headers)}]
    items = []
    for client in CLIENTS:
        url = service_url(client)
        headers = evidence_headers(token)
        body = evidence_body(subject, requirement_id(client), purpose)
        items.append({"client_id": client, "method": "POST", "url": url, "headers": headers, "body": body, "source": request_source("POST", url, headers, body)})
    return items


def _preview(requests: list[dict[str, Any]], purpose: str) -> dict[str, Any]:
    return requests[0]["source"] if len(requests) == 1 else {"method": "MULTI", "url": "solmara://registry-evidence", "purpose": purpose, "requests": [item["source"] for item in requests]}


def _aggregate(responses: list[tuple[dict[str, Any], StepHttpResult]]) -> StepHttpResult:
    failed = next((response for _, response in responses if response.status is None or not 200 <= response.status < 300), None)
    if failed:
        return failed
    results = [entry for _, response in responses for entry in response.body.get("results", [])]
    return StepHttpResult(200, {"results": results, "signed_evidence": [response.body.get("signed_evidence") for _, response in responses]}, {"content-type": "application/json"})
