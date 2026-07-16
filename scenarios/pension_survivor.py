#!/usr/bin/env python3
"""Death-to-pension-stop plus survivor-benefit guided scenario."""

from __future__ import annotations

from typing import Any

from .common import (
    CLAIM_RESULT_FORMAT,
    PURPOSES,
    SD_JWT_VC_FORMAT,
    StepHttpResult,
    auth_headers,
    credential_attempt,
    evaluation_body,
    friendly_result,
    http_json,
    missing_runtime_token,
    request_source,
    source_response,
    standard_error_result,
)
from .service_config import (
    authority_service_id,
    service_token,
    service_token_env,
    service_url,
)


SCENARIO_ID = "death-to-pension-survivor"
SERVICE_NAME = "Pension evidence services"
CRA_CLIENT = "cra-pension"
SIPF_CLIENT = "sipf-pension"
DECEASED_PENSIONER = "2300109568"
SURVIVING_SPOUSE = "2300118698"
STALE_CONTROL = "2300127827"
DISSOLVED_MARRIAGE_CONTROL = "2300146081"
DEATH_CLAIMS = ["person-is-deceased"]
PAYMENT_CLAIMS = ["pension-payment-active"]
SURVIVOR_CLAIMS = ["survivor-is-eligible"]
CREDENTIAL_PROFILE = "sipf-survivor-benefit.survivor-benefit-status"
CREDENTIAL_STEPS = {"survivor-benefit"}
AUTHORITY_NAMES = {
    CRA_CLIENT: "Civil Registration Authority",
    SIPF_CLIENT: "Social Insurance and Pensions Fund",
}
FRIENDLY = {
    "discover": {
        "met": (
            "The catalogues list what may be asked.",
            "Claim definitions only. No pension records have moved.",
        ),
    },
    "stop-payment": {
        "met": (
            "The pension stops.",
            "The application combined CRA's death predicate with SIPF's active-payment predicate. Neither authority received the other's source record.",
        ),
        "unmet": (
            "No stop today.",
            "The application only derives a stop when death is registered and SIPF confirms an active payment.",
        ),
    },
    "survivor-benefit": {
        "met": (
            "Yes. The surviving spouse can be offered the benefit.",
            "SIPF returned only the survivor eligibility fact and can issue the corresponding credential.",
        ),
        "unmet": (
            "Not eligible on the facts returned.",
            "The SIPF survivor eligibility check came back not met.",
        ),
    },
    "stale-control": {
        "unmet": (
            "No death registered yet, so nothing changes.",
            "CRA has no death record for this pensioner. The application does not derive a stop.",
        ),
    },
    "dissolved-control": {
        "unmet": (
            "Rejected: the marriage was dissolved.",
            "The SIPF survivor check came back not met because the marriage no longer stands.",
        ),
    },
    "cause-of-death-denial": {
        "refused": (
            "Refused: that question does not exist here.",
            "CRA offers no cause-of-death claim for this purpose, so the over-disclosing question cannot be asked.",
        ),
    },
}


def story() -> dict[str, Any]:
    return {
        "id": SCENARIO_ID,
        "title": "Death to pension stop plus survivor benefit",
        "short_title": "Pension stop and survivor benefit",
        "proves": "CRA death evidence and SIPF payment evidence can drive an application decision without a cross-authority Notary.",
        "domain": "Pensions",
        "availability": "hosted",
        "intro": "SIPF reviews a death registration without requesting cause of death.",
        "actor": "SIPF payments reviewer",
        "subject": {"name": "Rafael Nkomo", "identifier": DECEASED_PENSIONER},
        "requester": {
            "name": "SIPF review desk",
            "purpose": PURPOSES["pension_payment"],
        },
        "steps": [
            {
                "id": "discover",
                "label": "Discover pension claims",
                "prompt": "Read the CRA and SIPF catalogues.",
                "button": "Discover",
                "request_summary": "GET /v1/claims from CRA and SIPF.",
            },
            {
                "id": "stop-payment",
                "label": "Stop pension payment",
                "prompt": "Evaluate the deceased pensioner.",
                "button": "Evaluate",
                "request_summary": "POST the CRA death and SIPF active-payment claims.",
            },
            {
                "id": "survivor-benefit",
                "label": "Preview survivor benefit",
                "prompt": "Evaluate survivor eligibility.",
                "button": "Evaluate",
                "request_summary": "POST the SIPF survivor claim.",
            },
            {
                "id": "stale-control",
                "label": "Death not yet registered",
                "prompt": "Show stale-data reconciliation.",
                "button": "Evaluate",
                "request_summary": "POST the CRA and SIPF claims for the stale control UIN.",
            },
            {
                "id": "dissolved-control",
                "label": "Dissolved marriage control",
                "prompt": "Reject survivor eligibility when the marriage was dissolved.",
                "button": "Evaluate",
                "request_summary": "POST the SIPF survivor claim for the dissolved-marriage control UIN.",
            },
            {
                "id": "cause-of-death-denial",
                "label": "Purpose denial",
                "prompt": "Ask for cause of death and get denied.",
                "button": "Try denial",
                "request_summary": "POST an unavailable CRA cause-of-death claim.",
            },
        ],
        "receipt": [
            {"label": "Credential", "value": "SIPF survivor-benefit status VC preview"},
            {"label": "Cause of death disclosed", "value": "No"},
        ],
    }


def preview_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=False)["request_source"]


def run_step(config: dict[str, Any], step_id: str) -> dict[str, Any]:
    return _request(config, step_id, send=True)


def _request(config: dict[str, Any], step_id: str, *, send: bool) -> dict[str, Any]:
    subject = {
        "stop-payment": DECEASED_PENSIONER,
        "survivor-benefit": SURVIVING_SPOUSE,
        "stale-control": STALE_CONTROL,
        "dissolved-control": DISSOLVED_MARRIAGE_CONTROL,
        "cause-of-death-denial": DECEASED_PENSIONER,
    }.get(step_id)
    if step_id != "discover" and not subject:
        return standard_error_result(step_id)
    purpose = request_purpose(config, step_id)
    requests = authority_requests(step_id, subject, purpose)
    preview = combined_request_preview(requests, purpose)
    if not send:
        return {"request_source": preview}

    missing = next(
        (request for request in requests if not service_token(request["client_id"])),
        None,
    )
    if missing:
        result = missing_runtime_token(
            step_id,
            SERVICE_NAME,
            service_token_env(missing["client_id"]),
            preview,
        )
        result["request_sources"] = [request["source"] for request in requests]
        return result

    responses: list[tuple[dict[str, Any], StepHttpResult]] = []
    for authority_request in requests:
        result = http_json(
            authority_request["method"],
            authority_request["url"],
            authority_request["headers"],
            authority_request["body"],
        )
        responses.append((authority_request, result))

    aggregate = aggregate_response(responses)
    payload: dict[str, Any] = {
        "step_id": step_id,
        "friendly": friendly_result(step_id, aggregate, FRIENDLY),
        "request_source": preview,
        "request_sources": [request["source"] for request, _ in responses],
        "response_source": source_response(aggregate),
        "source_trace": [
            authority_trace(request, response) for request, response in responses
        ],
    }
    if step_id in {"stop-payment", "stale-control"} and aggregate.status == 200:
        payload["derived_decisions"] = {
            "pension-payment-should-stop": derived_stop_decision(aggregate.body),
            "owner": "pension-review-application",
        }
    if step_id in CREDENTIAL_STEPS and aggregate.status == 200:
        sipf_result = responses[0][1]
        payload.update(
            credential_attempt(
                service_url(SIPF_CLIENT, "/v1/credentials"),
                service_token(SIPF_CLIENT),
                purpose,
                sipf_result,
                CREDENTIAL_PROFILE,
                SURVIVOR_CLAIMS,
                authority_service_id(SIPF_CLIENT),
            )
        )
    return payload


def authority_requests(
    step_id: str, subject: str | None, purpose: str
) -> list[dict[str, Any]]:
    if step_id == "discover":
        return [
            build_request(CRA_CLIENT, "GET", "/v1/claims", purpose),
            build_request(SIPF_CLIENT, "GET", "/v1/claims", purpose),
        ]
    if step_id in {"stop-payment", "stale-control"}:
        return [
            build_request(
                CRA_CLIENT, "POST", "/v1/evaluations", purpose, subject, DEATH_CLAIMS
            ),
            build_request(
                SIPF_CLIENT, "POST", "/v1/evaluations", purpose, subject, PAYMENT_CLAIMS
            ),
        ]
    if step_id in {"survivor-benefit", "dissolved-control"}:
        return [
            build_request(
                SIPF_CLIENT,
                "POST",
                "/v1/evaluations",
                purpose,
                subject,
                SURVIVOR_CLAIMS,
                SD_JWT_VC_FORMAT,
            )
        ]
    if step_id == "cause-of-death-denial":
        return [
            build_request(
                CRA_CLIENT,
                "POST",
                "/v1/evaluations",
                purpose,
                subject,
                ["cause-of-death"],
            )
        ]
    return []


def build_request(
    client_id: str,
    method: str,
    path: str,
    purpose: str,
    subject: str | None = None,
    claims: list[str] | None = None,
    response_format: str = CLAIM_RESULT_FORMAT,
) -> dict[str, Any]:
    token = service_token(client_id)
    url = service_url(client_id, path)
    headers = auth_headers(
        token, purpose, response_format if method == "POST" else "application/json"
    )
    body = (
        evaluation_body(
            subject or "", claims or [], scheme="solmara_uin", format=response_format
        )
        if method == "POST"
        else None
    )
    return {
        "client_id": client_id,
        "method": method,
        "url": url,
        "headers": headers,
        "body": body,
        "source": request_source(method, url, headers, body),
    }


def combined_request_preview(
    requests: list[dict[str, Any]], purpose: str
) -> dict[str, Any]:
    if len(requests) == 1:
        return requests[0]["source"]
    return {
        "method": "MULTI",
        "url": "solmara://authority-notaries",
        "headers": {"Data-Purpose": purpose},
        "requests": [request["source"] for request in requests],
    }


def aggregate_response(
    responses: list[tuple[dict[str, Any], StepHttpResult]],
) -> StepHttpResult:
    failed = next(
        (
            response
            for _, response in responses
            if response.status is None or not 200 <= response.status < 300
        ),
        None,
    )
    if failed:
        return failed
    results: list[dict[str, Any]] = []
    for request, response in responses:
        body = response.body if isinstance(response.body, dict) else {}
        raw_results = body.get("results")
        if request["method"] == "POST" and not isinstance(raw_results, list):
            return StepHttpResult(
                502,
                {
                    "code": "authority.invalid_response",
                    "detail": "An authority response omitted claim results.",
                },
                {},
            )
        for result in raw_results or []:
            if isinstance(result, dict):
                results.append(
                    {
                        **result,
                        "authority": AUTHORITY_NAMES[request["client_id"]],
                        "notary_service_id": authority_service_id(request["client_id"]),
                    }
                )
    return StepHttpResult(
        200, {"results": results}, {"content-type": "application/json"}
    )


def derived_stop_decision(body: Any) -> bool | None:
    if not isinstance(body, dict) or not isinstance(body.get("results"), list):
        return None
    satisfied = {
        result.get("claim_id"): result.get("satisfied")
        for result in body["results"]
        if isinstance(result, dict)
    }
    death = satisfied.get("person-is-deceased")
    active = satisfied.get("pension-payment-active")
    return (
        death and active
        if isinstance(death, bool) and isinstance(active, bool)
        else None
    )


def authority_trace(
    request: dict[str, Any], response: StepHttpResult
) -> dict[str, Any]:
    return {
        "authority": AUTHORITY_NAMES[request["client_id"]],
        "service_id": authority_service_id(request["client_id"]),
        "request_source": request["source"],
        "response_source": source_response(response),
    }


def request_purpose(config: dict[str, Any], step_id: str) -> str:
    if isinstance(config.get("purpose_override"), str):
        return config["purpose_override"]
    if step_id in {"survivor-benefit", "dissolved-control"}:
        return PURPOSES["survivor_benefit"]
    return PURPOSES["pension_payment"]
