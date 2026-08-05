#!/usr/bin/env python3
"""Registry Evidence and Mint helpers for the guided Solmara scenarios."""

from __future__ import annotations

import base64
import json
import os
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

EVIDENCE_JWS_MEDIA_TYPE = "application/jose+json"
CHILD_BENEFIT_AS_OF_DATE = "2026-07-14"
PURPOSES = {
    "child_benefit": "child-benefit-review",
    "pension_payment": "pension-payment-review",
    "survivor_benefit": "survivor-benefit-determination",
    "voucher": "voucher-eligibility-review",
    "livestock": "livestock-movement-control",
    "citizen_self_service": "citizen-self-service",
}

_TOKEN_LOCK = threading.Lock()
_TOKEN_CACHE: tuple[str, float] = ("", 0.0)


@dataclass
class StepHttpResult:
    status: int | None
    body: Any
    headers: dict[str, str]
    error: str = ""


def joined_url(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def request_source(
    method: str,
    url: str,
    headers: dict[str, str],
    body: Any | None = None,
) -> dict[str, Any]:
    source: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": redact_headers(headers),
    }
    if body is not None:
        source["body"] = body
    return source


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = dict(headers)
    for key in redacted:
        if key.lower() == "authorization":
            redacted[key] = "Bearer [runtime token hidden]"
        elif key.lower() == "x-api-key":
            redacted[key] = "[runtime token hidden]"
    return redacted


def tls_context() -> ssl.SSLContext | None:
    ca_bundle = os.environ.get("SOLMARA_EVIDENCE_CA_BUNDLE")
    return ssl.create_default_context(cafile=ca_bundle) if ca_bundle else None


def http_json(
    method: str,
    url: str,
    headers: dict[str, str],
    body: Any | None = None,
    timeout: float = 8.0,
) -> StepHttpResult:
    data = None
    request_headers = dict(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, headers=request_headers, data=data, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=tls_context()) as response:
            return StepHttpResult(
                response.status,
                parse_body(response.read()),
                {key.lower(): value for key, value in response.headers.items()},
            )
    except urllib.error.HTTPError as error:
        return StepHttpResult(
            error.code,
            parse_body(error.read()),
            {key.lower(): value for key, value in error.headers.items()},
        )
    except Exception as error:  # the guided UI reports a value-free class only
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
        "headers": {
            key: value
            for key, value in result.headers.items()
            if key in {"content-type", "www-authenticate"}
        },
        "body": result.body,
        "error": result.error,
    }


def _client_assertion(client_id: str, key_path: str, audience: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    jwk = json.loads(Path(key_path).read_text())
    now = int(time.time())
    header = {"alg": "EdDSA", "typ": "JWT", "kid": jwk["kid"]}
    claims = {
        "iss": client_id,
        "sub": client_id,
        "aud": audience,
        "iat": now,
        "exp": now + 120,
        "jti": str(uuid.uuid4()),
    }
    signing_input = ".".join(
        b64url_nopad(json.dumps(value, separators=(",", ":")).encode())
        for value in (header, claims)
    )
    private_key = Ed25519PrivateKey.from_private_bytes(b64url_decode(jwk["d"]))
    signature = private_key.sign(signing_input.encode("ascii"))
    return f"{signing_input}.{b64url_nopad(signature)}"


def evidence_access_token() -> str:
    """Obtain and briefly cache a Mint token using private_key_jwt."""
    static = os.environ.get("SOLMARA_EVIDENCE_ACCESS_TOKEN", "")
    if static:
        return static
    mint_url = os.environ.get("SOLMARA_MINT_URL", "")
    assertion_audience = os.environ.get("SOLMARA_MINT_ASSERTION_AUDIENCE", "")
    client_id = os.environ.get("SOLMARA_EVIDENCE_CLIENT_ID", "")
    key_path = os.environ.get("SOLMARA_EVIDENCE_CLIENT_KEY", "")
    if not mint_url or not client_id or not key_path or not Path(key_path).is_file():
        return ""
    global _TOKEN_CACHE
    with _TOKEN_LOCK:
        if _TOKEN_CACHE[0] and _TOKEN_CACHE[1] > time.time() + 10:
            return _TOKEN_CACHE[0]
        token_url = joined_url(mint_url, "/token")
        assertion = _client_assertion(
            client_id, key_path, assertion_audience or token_url
        )
        form = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": assertion,
            }
        ).encode()
        request = urllib.request.Request(
            token_url,
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8, context=tls_context()) as response:
                payload = json.loads(response.read())
        except Exception:
            return ""
        token = payload.get("access_token", "")
        lifetime = int(payload.get("expires_in", 300))
        if isinstance(token, str) and token:
            _TOKEN_CACHE = (token, time.time() + lifetime)
            return token
        return ""


def evidence_headers(token: str, *, discover: bool = False) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json" if discover else EVIDENCE_JWS_MEDIA_TYPE,
    }


def evidence_body(
    subject: str,
    requirement: str,
    purpose: str,
    *,
    selector_profile: str = "solmara-uin-v1",
    selector_field: str = "uin",
) -> dict[str, Any]:
    return {
        "requestNonce": b64url_nopad(secrets.token_bytes(32)),
        "requirement": requirement,
        "purpose": purpose,
        "subjects": [
            {
                "role": "subject",
                "selector": {
                    "profile": selector_profile,
                    "values": {selector_field: subject},
                },
            }
        ],
    }


def decoded_evidence_payload(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, dict) or not isinstance(body.get("payload"), str):
        return None
    try:
        payload = json.loads(b64url_decode(body["payload"]))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def normalized_evidence_result(result: StepHttpResult) -> StepHttpResult:
    """Keep the signed JWS and add the old UI's small predicate summary."""
    if result.status is None or not 200 <= result.status < 300:
        return result
    payload = decoded_evidence_payload(result.body)
    if payload is None:
        return StepHttpResult(
            502,
            {"code": "evidence.invalid_response", "detail": "Evidence returned an invalid signed assertion."},
            {},
        )
    supported = payload.get("supportedValues", [])
    results = []
    for entry in supported if isinstance(supported, list) else []:
        if not isinstance(entry, dict):
            continue
        concept = str(entry.get("providesValueFor", ""))
        value = entry.get("value")
        results.append(
            {
                "claim_id": concept.rsplit("/", 1)[-1],
                "concept_id": concept,
                "satisfied": value if isinstance(value, bool) else None,
                "value": value,
            }
        )
    return StepHttpResult(
        result.status,
        {"results": results, "assertion": payload, "signed_evidence": result.body},
        result.headers,
        result.error,
    )


def friendly_result(
    step_id: str,
    result: StepHttpResult,
    copy: dict[str, dict[str, tuple[str, str]]] | None = None,
) -> dict[str, Any]:
    copy = copy or {}
    body = result.body if isinstance(result.body, dict) else {}
    raw_results = body.get("results")
    results = raw_results if isinstance(raw_results, list) else []
    unmet = [item.get("claim_id") for item in results if item.get("satisfied") is False]
    facts = [{"label": "HTTP status", "value": result.status or "No response"}]
    if results:
        facts.append({"label": "Evidence values", "value": f"{len(results) - len(unmet)} of {len(results)} true"})
    if result.status is None:
        return {"title": "No response from the service.", "message": "Check that Mint and Evidence are running.", "status": "needs_attention", "facts": facts}
    if result.status >= 400 and "refused" in copy.get(step_id, {}):
        title, message = copy[step_id]["refused"]
        return {"title": title, "message": message, "status": "done", "facts": facts}
    if 200 <= result.status < 300:
        key = "unmet" if unmet else "met"
        default = (
            ("Evidence returned a false value.", "The signed response discloses only the reviewed concept value.")
            if unmet
            else ("Signed evidence returned.", "The source row stayed behind its authority's Records API.")
        )
        title, message = copy.get(step_id, {}).get(key, default)
        return {"title": title, "message": message, "status": "done", "facts": facts}
    return {
        "title": "Request needs attention.",
        "message": str(body.get("detail") or body.get("title") or body.get("code") or "Evidence refused the request."),
        "status": "needs_attention",
        "facts": facts,
    }


def missing_runtime_token(
    step_id: str, service: str, token_env: str, request: dict[str, Any]
) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "friendly": {
            "title": f"{service} is not configured yet.",
            "message": "Set the local Mint URL and client key, then start the Evidence stack.",
            "status": "needs_attention",
            "facts": [{"label": "Required setting", "value": token_env}],
        },
        "request_source": request,
        "response_source": {"note": "No Mint access token was available."},
    }


def standard_error_result(step_id: str) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "friendly": {"title": "Unknown step.", "message": "This scenario step is not configured.", "status": "needs_attention", "facts": []},
        "request_source": {},
        "response_source": {},
    }
