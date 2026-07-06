#!/usr/bin/env python3
"""Shared helpers for Solmara Lab guided scenarios."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


CLAIM_RESULT_FORMAT = "application/vnd.registry-notary.claim-result+json"
SD_JWT_VC_FORMAT = "application/dc+sd-jwt"
HOLDER_PROOF_TYP = "kb+jwt"
HOLDER_PROOF_ALG = "EdDSA"
HOLDER_PROOF_LIFETIME_SECONDS = 60
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


def evaluation_body(
    subject: str,
    claim_ids: list[str],
    *,
    scheme: str,
    disclosure: str = "predicate",
    format: str = CLAIM_RESULT_FORMAT,
) -> dict[str, Any]:
    return {
        "target": {"type": "Person", "identifiers": [{"scheme": scheme, "value": subject}]},
        "claims": claim_ids,
        "disclosure": disclosure,
        "format": format,
    }


def b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def json_b64url(value: Any) -> str:
    return b64url_nopad(json.dumps(value, separators=(",", ":")).encode("utf-8"))


@dataclass
class HolderKeypair:
    """An ephemeral did:jwk holder identity used to prove possession at credential issuance."""

    holder_id: str
    private_key: Ed25519PrivateKey


def holder_keypair() -> HolderKeypair:
    """Generate a fresh Ed25519 keypair and derive its did:jwk holder id.

    The private key never leaves this process; only the public JWK is encoded
    into the did:jwk identifier that gets sent to the notary.
    """
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    public_jwk = {"kty": "OKP", "crv": "Ed25519", "x": b64url_nopad(public_bytes)}
    holder_id = f"did:jwk:{json_b64url(public_jwk)}"
    return HolderKeypair(holder_id=holder_id, private_key=private_key)


def holder_proof(
    keypair: HolderKeypair,
    *,
    audience: str,
    evaluation_id: str,
    credential_profile: str,
    disclosure: str,
    claim_ids: list[str],
) -> str:
    """Sign a holder key-binding proof JWT for a credential issuance request.

    A fresh jti is minted on every call so repeated runs stay replay-safe.
    """
    now = int(time.time())
    header = {"alg": HOLDER_PROOF_ALG, "typ": HOLDER_PROOF_TYP, "kid": keypair.holder_id}
    disclosure_hash = b64url_nopad(hashlib.sha256(disclosure.encode("utf-8")).digest())
    payload = {
        "sub": keypair.holder_id,
        "aud": audience,
        "iat": now,
        "exp": now + HOLDER_PROOF_LIFETIME_SECONDS,
        "jti": str(uuid.uuid4()),
        "evaluation_id": evaluation_id,
        "credential_profile": credential_profile,
        "disclosure": disclosure_hash,
        "claims": claim_ids,
    }
    signing_input = f"{json_b64url(header)}.{json_b64url(payload)}"
    signature = keypair.private_key.sign(signing_input.encode("ascii"))
    return f"{signing_input}.{b64url_nopad(signature)}"


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


def credential_attempt(
    url: str,
    token: str,
    purpose: str,
    evaluation_result: StepHttpResult,
    profile: str,
    claim_ids: list[str],
    service_id: str,
    *,
    disclosure: str = "predicate",
) -> dict[str, Any]:
    evaluation_id = first_evaluation_id(evaluation_result.body)
    if not evaluation_id:
        return {
            "credential": {
                "status": "not_attempted",
                "profile": profile,
                "format": SD_JWT_VC_FORMAT,
                "reason": "evaluation_id_missing",
                "message": "The notary did not return an evaluation id for credential issuance.",
            }
        }
    keypair = holder_keypair()
    proof = holder_proof(
        keypair,
        audience=service_id,
        evaluation_id=evaluation_id,
        credential_profile=profile,
        disclosure=disclosure,
        claim_ids=claim_ids,
    )
    body = {
        "evaluation_id": evaluation_id,
        "credential_profile": profile,
        "format": SD_JWT_VC_FORMAT,
        "claims": claim_ids,
        "disclosure": disclosure,
        "purpose": purpose,
        "holder": {"binding": "did", "id": keypair.holder_id, "proof": proof},
    }
    headers = auth_headers(token, purpose, "application/json")
    request = request_source("POST", url, headers, body)
    result = http_json("POST", url, headers, body)
    return {
        "credential_source": request,
        "credential_response_source": source_response(result),
        "credential": credential_summary(profile, keypair.holder_id, result),
    }


def first_evaluation_id(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    results = body.get("results")
    if not isinstance(results, list):
        return None
    for result in results:
        if isinstance(result, dict) and isinstance(result.get("evaluation_id"), str):
            return result["evaluation_id"]
    return None


def credential_summary(profile: str, holder_id: str, result: StepHttpResult) -> dict[str, Any]:
    body = result.body if isinstance(result.body, dict) else {}
    if result.status and 200 <= result.status < 300:
        credential = body.get("credential")
        preview = f"{credential[:48]}..." if isinstance(credential, str) and len(credential) > 48 else credential
        disclosures = body.get("disclosures")
        return {
            "status": "issued",
            "profile": body.get("credential_profile", profile),
            "format": body.get("format", SD_JWT_VC_FORMAT),
            "issuer": body.get("issuer"),
            "credential_id": body.get("credential_id"),
            "expires_at": body.get("expires_at"),
            "holder_id": holder_id,
            "disclosures": len(disclosures) if isinstance(disclosures, list) else 0,
            "compact_preview": preview,
        }
    reason = body.get("code") or body.get("error") or result.error or f"HTTP {result.status}"
    message = body.get("detail") or body.get("message") or body.get("title") or "Credential issuance did not complete."
    return {
        "status": "not_issued",
        "profile": profile,
        "format": SD_JWT_VC_FORMAT,
        "reason": reason,
        "http_status": result.status,
        "message": message,
    }


def friendly_result(step_id: str, result: StepHttpResult, copy: dict[str, dict[str, tuple[str, str]]] | None = None) -> dict[str, Any]:
    """Civilian-language summary of a step outcome.

    `copy` maps step_id -> {"met": (title, message), "unmet": (title, message)}
    for outcomes the story wants to narrate; everything else falls back to
    honest generic copy. A 403 with a pdp.* code is the boundary working, so
    it reads as success, never as an error.
    """
    copy = copy or {}
    body = result.body if isinstance(result.body, dict) else {}
    raw_results = body.get("results")
    results = raw_results if isinstance(raw_results, list) else None
    unmet = (
        [entry.get("claim_id") for entry in results if isinstance(entry, dict) and entry.get("satisfied") is False]
        if results is not None
        else []
    )
    facts: list[dict[str, Any]] = [
        {"label": "HTTP status", "value": result.status if result.status is not None else "No response"}
    ]
    if results is not None:
        facts.append({"label": "Claims met", "value": f"{len(results) - len(unmet)} of {len(results)}"})
    if result.status is None:
        return {
            "title": "No response from the service.",
            "message": "The request could not be sent. Check that the lab stack is running.",
            "status": "needs_attention",
            "facts": facts,
        }
    code = str(body.get("code", ""))
    if result.status >= 400 and "refused" in copy.get(step_id, {}):
        title, message = copy[step_id]["refused"]
        return {"title": title, "message": message, "status": "done", "facts": facts}
    if result.status == 403 and code.startswith("pdp."):
        return {
            "title": "Refused, exactly as designed.",
            "message": "That purpose does not permit this question. Nothing was disclosed, only a stable problem code.",
            "status": "done",
            "facts": facts,
        }
    if 200 <= result.status < 300:
        step_copy = copy.get(step_id, {})
        if unmet:
            title, message = step_copy.get(
                "unmet",
                (
                    "Rejected, exactly as designed.",
                    f"The check on {unmet[0]} came back not met, so the request stops there without exposing anything else.",
                ),
            )
        else:
            title, message = step_copy.get(
                "met",
                ("Request completed.", "The response is minimized to claim results and denial codes."),
            )
        return {"title": title, "message": message, "status": "done", "facts": facts}
    return {
        "title": "Request needs attention.",
        "message": str(body.get("detail") or body.get("title") or "The service returned an unexpected status."),
        "status": "needs_attention",
        "facts": facts,
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
