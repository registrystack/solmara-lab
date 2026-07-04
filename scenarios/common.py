#!/usr/bin/env python3
"""Shared helpers for Solmara Lab guided scenarios."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin


CLAIM_RESULT_FORMAT = "application/vnd.registry-notary.claim-result+json"
PURPOSES = {
    "child_benefit": "https://id.registrystack.org/solmara/purpose/child-benefit-review",
    "pension_payment": "https://id.registrystack.org/solmara/purpose/pension-payment-review",
    "survivor_benefit": "https://id.registrystack.org/solmara/purpose/survivor-benefit-determination",
    "voucher": "https://id.registrystack.org/solmara/purpose/voucher-eligibility-review",
    "livestock": "https://id.registrystack.org/solmara/purpose/livestock-movement-control",
    "citizen_self_service": "https://id.registrystack.org/solmara/purpose/citizen-self-service",
}


@dataclass
class StepHttpResult:
    status: int | None
    body: Any
    headers: dict[str, str]
    error: str = ""


def joined_url(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def env_url(env_name: str, default: str, path: str) -> str:
    return joined_url(os.environ.get(env_name, default), path)


def request_source(method: str, url: str, headers: dict[str, str], body: Any | None = None) -> dict[str, Any]:
    source: dict[str, Any] = {"method": method, "url": url, "headers": redact_headers(headers)}
    if body is not None:
        source["body"] = body
    return source


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = dict(headers)
    for key in list(redacted):
        if key.lower() == "authorization":
            redacted[key] = "Bearer [runtime token hidden]" if redacted[key] else "Bearer [runtime token missing]"
        if key.lower() == "x-api-key":
            redacted[key] = "[runtime token hidden]" if redacted[key] else "[runtime token missing]"
    return redacted


def auth_headers(token: str, purpose: str, accept: str = "application/json") -> dict[str, str]:
    return {"x-api-key": token, "Accept": accept, "Data-Purpose": purpose}


def evaluation_body(subject: str, claim_ids: list[str], *, scheme: str, disclosure: str = "predicate") -> dict[str, Any]:
    return {
        "target": {"type": "Person", "identifiers": [{"scheme": scheme, "value": subject}]},
        "claims": claim_ids,
        "disclosure": disclosure,
        "format": CLAIM_RESULT_FORMAT,
    }


def http_json(method: str, url: str, headers: dict[str, str], body: Any | None = None, timeout: float = 8.0) -> StepHttpResult:
    data = None
    request_headers = dict(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, headers=request_headers, data=data, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return StepHttpResult(response.status, parse_body(raw), {key.lower(): value for key, value in response.headers.items()})
    except urllib.error.HTTPError as error:
        return StepHttpResult(error.code, parse_body(error.read()), {key.lower(): value for key, value in error.headers.items()})
    except Exception as error:
        return StepHttpResult(None, {}, {}, error.__class__.__name__)


def parse_body(raw: bytes) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw.decode("utf-8", errors="replace")


def source_response(result: StepHttpResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "headers": {key: value for key, value in result.headers.items() if key in {"content-type", "www-authenticate"}},
        "body": result.body,
        "error": result.error,
    }


def missing_runtime_token(step_id: str, service: str, token_env: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "friendly": {
            "title": f"{service} is not configured yet.",
            "message": "The Solmara wave 1 flow is scaffolded. Set the service URL and token environment variables once the local stack endpoints are available.",
            "status": "needs_attention",
            "facts": [
                {"label": "Required token env", "value": token_env},
                {"label": "Runtime", "value": "Not called without a token"},
            ],
        },
        "request_source": request,
        "response_source": {"note": "No runtime token configured, so the request was not sent."},
    }


def standard_error_result(step_id: str) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "friendly": {"title": "Unknown step.", "message": "This scenario step is not configured.", "status": "needs_attention", "facts": []},
        "request_source": {},
        "response_source": {},
    }
