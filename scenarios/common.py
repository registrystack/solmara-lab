#!/usr/bin/env python3
"""Registry Evidence and Mint helpers for the guided Solmara scenarios."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

EVIDENCE_JWS_MEDIA_TYPE = "application/jose+json"
EVIDENCE_JWKS_MEDIA_TYPE = "application/jwk-set+json"
EVIDENCE_JWS_HEADER = {
    "alg": "ES256",
    "typ": "evidence+jws",
    "cty": "application/evidence+json",
}
EVIDENCE_AUDIENCE = "https://id.registrystack.org/solmara/audience/demo-client"
MAX_JWKS_BYTES = 64 * 1024
MAX_JWKS_KEYS = 8
JWKS_CACHE_SECONDS = 60
ASSERTION_CLOCK_SKEW_SECONDS = 30
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
_JWKS_LOCK = threading.Lock()
_JWKS_CACHE: dict[str, tuple[float, tuple[dict[str, str], ...]]] = {}
_B64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_KID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


@dataclass
class StepHttpResult:
    status: int | None
    body: Any
    headers: dict[str, str]
    error: str = ""
    request: Any | None = None


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
    parsed_url = urllib.parse.urlsplit(url)
    source: dict[str, Any] = {
        "method": method,
        "url": parsed_url._replace(query="", fragment="").geturl(),
        "headers": redact_headers(headers),
    }
    return source


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered == "authorization":
            redacted[key] = "Bearer [runtime token hidden]"
        elif lowered == "x-api-key":
            redacted[key] = "[runtime token hidden]"
        elif lowered in {"accept", "content-type"}:
            redacted[key] = value
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
                request=body,
            )
    except urllib.error.HTTPError as error:
        return StepHttpResult(
            error.code,
            parse_body(error.read()),
            {key.lower(): value for key, value in error.headers.items()},
            request=body,
        )
    except Exception as error:  # the guided UI reports a value-free class only
        return StepHttpResult(None, {}, {}, error.__class__.__name__, body)


def parse_body(raw: bytes) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_closed_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return raw.decode("utf-8", errors="replace")


def _closed_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise ValueError("duplicate JSON member")
        value[key] = member
    return value


def source_response(result: StepHttpResult) -> dict[str, Any]:
    if result.status is None:
        code = "transport_unavailable"
    elif 200 <= result.status < 300:
        code = "ok"
    elif result.status == 502 and isinstance(result.body, dict) and result.body.get("code") == "evidence.invalid_response":
        code = "assertion_verification_failed"
    elif 400 <= result.status < 500:
        code = "request_refused"
    else:
        code = "service_unavailable"
    return {"status": result.status, "code": code}


def _client_assertion(client_id: str, key_path: str, audience: str) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    jwk = json.loads(Path(key_path).read_text(), object_pairs_hook=_closed_json_object)
    if (
        not isinstance(jwk, dict)
        or jwk.get("kty") != "EC"
        or jwk.get("crv") != "P-256"
        or jwk.get("alg") != "ES256"
        or not isinstance(jwk.get("kid"), str)
        or not _KID_PATTERN.fullmatch(jwk["kid"])
    ):
        raise ValueError("invalid client assertion key")
    scalar = b64url_decode(jwk.get("d", ""))
    if len(scalar) != 32:
        raise ValueError("invalid client assertion key")
    private_key = ec.derive_private_key(int.from_bytes(scalar, "big"), ec.SECP256R1())
    numbers = private_key.public_key().public_numbers()
    if (
        b64url_nopad(numbers.x.to_bytes(32, "big")) != jwk.get("x")
        or b64url_nopad(numbers.y.to_bytes(32, "big")) != jwk.get("y")
    ):
        raise ValueError("invalid client assertion key")
    now = int(time.time())
    header = {"alg": "ES256", "typ": "JWT", "kid": jwk["kid"]}
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
    der_signature = private_key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
    r_value, s_value = utils.decode_dss_signature(der_signature)
    signature = r_value.to_bytes(32, "big") + s_value.to_bytes(32, "big")
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
        try:
            assertion = _client_assertion(
                client_id, key_path, assertion_audience or token_url
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return ""
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


def _invalid_evidence_result() -> StepHttpResult:
    return StepHttpResult(
        502,
        {
            "code": "evidence.invalid_response",
            "detail": "The Evidence assertion could not be verified.",
        },
        {},
    )


def _decode_segment(value: Any) -> bytes:
    if not isinstance(value, str) or not value or not _B64URL_PATTERN.fullmatch(value):
        raise ValueError("invalid JWS segment")
    decoded = b64url_decode(value)
    if b64url_nopad(decoded) != value:
        raise ValueError("noncanonical JWS segment")
    return decoded


def _json_segment(value: Any) -> dict[str, Any]:
    decoded = _decode_segment(value)
    parsed = json.loads(decoded, object_pairs_hook=_closed_json_object)
    if not isinstance(parsed, dict):
        raise ValueError("JWS segment is not an object")
    return parsed


def _jwk_thumbprint(jwk: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"], "y": jwk["y"]},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return b64url_nopad(hashlib.sha256(canonical).digest())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch_jwks(url: str) -> tuple[dict[str, str], ...]:
    request = urllib.request.Request(
        url,
        headers={"Accept": EVIDENCE_JWKS_MEDIA_TYPE},
        method="GET",
    )
    handlers: list[Any] = [_NoRedirect()]
    context = tls_context()
    if context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=context))
    opener = urllib.request.build_opener(*handlers)
    with opener.open(request, timeout=5) as response:
        if response.status != 200 or response.headers.get_content_type() != EVIDENCE_JWKS_MEDIA_TYPE:
            raise ValueError("invalid JWKS response")
        raw = response.read(MAX_JWKS_BYTES + 1)
    if len(raw) > MAX_JWKS_BYTES:
        raise ValueError("JWKS response is too large")
    document = json.loads(raw, object_pairs_hook=_closed_json_object)
    if not isinstance(document, dict) or set(document) != {"keys"}:
        raise ValueError("invalid JWKS document")
    keys = document["keys"]
    if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_JWKS_KEYS:
        raise ValueError("invalid JWKS key count")
    validated: list[dict[str, str]] = []
    seen: set[str] = set()
    expected_members = {"kty", "kid", "alg", "crv", "x", "y"}
    for key in keys:
        if not isinstance(key, dict) or set(key) != expected_members:
            raise ValueError("invalid JWK")
        if key.get("kty") != "EC" or key.get("crv") != "P-256" or key.get("alg") != "ES256":
            raise ValueError("invalid JWK type")
        if not all(isinstance(key.get(member), str) for member in expected_members):
            raise ValueError("invalid JWK member")
        if len(_decode_segment(key["x"])) != 32 or len(_decode_segment(key["y"])) != 32:
            raise ValueError("invalid JWK coordinate")
        if not _KID_PATTERN.fullmatch(key["kid"]) or _jwk_thumbprint(key) != key["kid"]:
            raise ValueError("invalid JWK kid")
        if key["kid"] in seen:
            raise ValueError("duplicate JWK kid")
        seen.add(key["kid"])
        validated.append(key)
    return tuple(validated)


def _authority_jwks(service_id: str) -> tuple[dict[str, str], ...]:
    from .service_config import service_url

    url = service_url(service_id, "/.well-known/evidence/jwks.json")
    now = time.monotonic()
    with _JWKS_LOCK:
        cached = _JWKS_CACHE.get(url)
        if cached and cached[0] > now:
            return cached[1]
    keys = _fetch_jwks(url)
    with _JWKS_LOCK:
        _JWKS_CACHE[url] = (time.monotonic() + JWKS_CACHE_SECONDS, keys)
    return keys


def _verify_es256(protected: str, payload: str, signature: str, jwk: dict[str, str]) -> None:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    raw_signature = _decode_segment(signature)
    if len(raw_signature) != 64:
        raise ValueError("invalid ES256 signature")
    x = int.from_bytes(_decode_segment(jwk["x"]), "big")
    y = int.from_bytes(_decode_segment(jwk["y"]), "big")
    public_key = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
    der_signature = encode_dss_signature(
        int.from_bytes(raw_signature[:32], "big"),
        int.from_bytes(raw_signature[32:], "big"),
    )
    public_key.verify(
        der_signature,
        f"{protected}.{payload}".encode("ascii"),
        ec.ECDSA(hashes.SHA256()),
    )


def _parse_evidence_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("invalid Evidence time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Evidence time has no timezone")
    return parsed.astimezone(timezone.utc)


def _valid_uri(value: Any) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 512 and bool(urllib.parse.urlsplit(value).scheme)


def _validate_evidence_payload(payload: dict[str, Any], request: dict[str, Any], config: dict[str, Any]) -> None:
    required = {
        "schema", "assuranceProfile", "subjectBinding", "requestNonce", "id", "type",
        "supportsRequirement", "isConformantTo", "issuedBy", "providedBy", "issuedAt",
        "observedAt", "validUntil", "purpose", "audience", "configurationRevision",
        "subjects", "supportedValues",
    }
    if set(payload) != required:
        raise ValueError("invalid Evidence members")
    expected_audience = os.environ.get("SOLMARA_EVIDENCE_AUDIENCE", EVIDENCE_AUDIENCE)
    if (
        payload.get("schema") != "registry.assertion-evidence/v1"
        or payload.get("assuranceProfile") != "production"
        or payload.get("subjectBinding") != "audience-scoped"
        or payload.get("type") != "Evidence"
        or payload.get("supportsRequirement") != request.get("requirement")
        or payload.get("isConformantTo") != config["evidence_type"]
        or payload.get("purpose") != request.get("purpose")
        or payload.get("requestNonce") != request.get("requestNonce")
        or payload.get("issuedBy") != config["issuer"]
        or payload.get("providedBy") != config["provider"]
        or payload.get("audience") != expected_audience
    ):
        raise ValueError("Evidence policy mismatch")
    for member in ("id", "supportsRequirement", "isConformantTo", "issuedBy", "providedBy", "audience"):
        if not _valid_uri(payload.get(member)):
            raise ValueError("invalid Evidence URI")
    revision = payload.get("configurationRevision")
    if not isinstance(revision, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", revision):
        raise ValueError("invalid configuration revision")
    purpose = payload.get("purpose")
    if not isinstance(purpose, str) or not re.fullmatch(r"[a-z][a-z0-9._:-]{0,127}", purpose):
        raise ValueError("invalid Evidence purpose")
    nonce = payload.get("requestNonce")
    if not isinstance(nonce, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", nonce):
        raise ValueError("invalid Evidence nonce")
    subjects = payload.get("subjects")
    if not isinstance(subjects, list) or len(subjects) != 1:
        raise ValueError("invalid Evidence subjects")
    subject_pairs: set[tuple[str, str]] = set()
    for subject in subjects:
        if not isinstance(subject, dict) or set(subject) != {"role", "binding"}:
            raise ValueError("invalid Evidence subject")
        role, binding = subject.get("role"), subject.get("binding")
        if not isinstance(role, str) or not re.fullmatch(r"[a-z][a-z0-9._-]{0,63}", role):
            raise ValueError("invalid Evidence subject role")
        if role != "subject":
            raise ValueError("unexpected Evidence subject role")
        if not isinstance(binding, str) or not re.fullmatch(r"urn:evidence:subject:v[1-9][0-9]*_[A-Za-z0-9_-]{43}", binding):
            raise ValueError("invalid Evidence subject binding")
        if (role, binding) in subject_pairs:
            raise ValueError("duplicate Evidence subject")
        subject_pairs.add((role, binding))
    supported = payload.get("supportedValues")
    if not isinstance(supported, list) or not 1 <= len(supported) <= 16:
        raise ValueError("invalid supported values")
    concepts: list[str] = []
    for entry in supported:
        if not isinstance(entry, dict) or set(entry) != {"providesValueFor", "value"}:
            raise ValueError("invalid supported value")
        concept = entry.get("providesValueFor")
        if not _valid_uri(concept) or not isinstance(entry.get("value"), bool):
            raise ValueError("invalid supported value")
        concepts.append(str(concept))
    expected_concepts = tuple(
        f"https://id.registrystack.org/solmara/concept/{concept}"
        for concept in config["concepts"]
    )
    if tuple(concepts) != expected_concepts or len(concepts) != len(set(concepts)):
        raise ValueError("Evidence output mismatch")
    issued = _parse_evidence_time(payload.get("issuedAt"))
    observed = _parse_evidence_time(payload.get("observedAt"))
    valid_until = _parse_evidence_time(payload.get("validUntil"))
    now = datetime.now(timezone.utc)
    skew = timedelta(seconds=ASSERTION_CLOCK_SKEW_SECONDS)
    if (
        issued < observed
        or valid_until <= observed
        or valid_until <= issued
        or valid_until - issued > timedelta(seconds=config["maximum_validity_seconds"])
        or issued > now + skew
        or observed > now + skew
        or now >= valid_until + skew
    ):
        raise ValueError("invalid Evidence validity")


def decoded_evidence_payload(body: Any) -> dict[str, Any] | None:
    if not isinstance(body, dict) or set(body) != {"protected", "payload", "signature"}:
        return None
    try:
        return _json_segment(body["payload"])
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def normalized_evidence_result(
    result: StepHttpResult,
    *,
    request: dict[str, Any] | None = None,
    service_id: str | None = None,
) -> StepHttpResult:
    """Verify a signed assertion, then add the UI's small predicate summary."""
    if result.status is None or not 200 <= result.status < 300:
        return result
    retained_request = request if request is not None else result.request
    if not isinstance(retained_request, dict):
        return _invalid_evidence_result()
    try:
        from .service_config import config_for_requirement, requirement_config

        config = requirement_config(service_id) if service_id else config_for_requirement(str(retained_request.get("requirement", "")))
        if retained_request.get("requirement") != config["requirement"]:
            raise ValueError("request requirement mismatch")
        content_type = result.headers.get("content-type", "").strip().lower()
        if content_type != EVIDENCE_JWS_MEDIA_TYPE:
            raise ValueError("invalid Evidence media type")
        body = result.body
        if not isinstance(body, dict) or set(body) != {"protected", "payload", "signature"}:
            raise ValueError("invalid flattened JWS")
        protected = _json_segment(body["protected"])
        if set(protected) != {"alg", "kid", "typ", "cty"}:
            raise ValueError("invalid protected header")
        if {key: protected.get(key) for key in EVIDENCE_JWS_HEADER} != EVIDENCE_JWS_HEADER:
            raise ValueError("invalid Evidence protected header")
        kid = protected.get("kid")
        if not isinstance(kid, str) or not _KID_PATTERN.fullmatch(kid):
            raise ValueError("invalid Evidence kid")
        key = next((candidate for candidate in _authority_jwks(config["service_id"]) if candidate["kid"] == kid), None)
        if key is None:
            raise ValueError("untrusted Evidence kid")
        _verify_es256(body["protected"], body["payload"], body["signature"], key)
        payload = _json_segment(body["payload"])
        _validate_evidence_payload(payload, retained_request, config)
    except Exception:
        return _invalid_evidence_result()
    results = []
    for entry in payload["supportedValues"]:
        concept = entry["providesValueFor"]
        value = entry["value"]
        results.append(
            {
                "claim_id": concept.rsplit("/", 1)[-1],
                "concept_id": concept,
                "satisfied": value if isinstance(value, bool) else None,
                "value": value,
            }
        )
    presentation = {
        "authority": config["name"],
        "issuer": config["issuer"],
        "provider": config["provider"],
        "source": config["source"],
    }
    return StepHttpResult(
        result.status,
        {"results": results, "assertion": payload, "signed_evidence": result.body, "presentation": presentation},
        result.headers,
        result.error,
    )


def safe_evidence_projection(result: StepHttpResult) -> dict[str, Any]:
    """Return only verified concepts and public authority attribution for a UI."""
    if result.status is None or not 200 <= result.status < 300:
        return {"results": [], "presentations": []}
    body = result.body if isinstance(result.body, dict) else {}
    presentation = body.get("presentation")
    presentations = body.get("presentations")
    if not isinstance(presentations, list):
        presentations = [presentation] if isinstance(presentation, dict) else []
    safe_presentations = [
        {
            "authority": item.get("authority"),
            "issuer": item.get("issuer"),
            "provider": item.get("provider"),
            "source": item.get("source"),
        }
        for item in presentations
        if isinstance(item, dict)
        and set(item) == {"authority", "issuer", "provider", "source"}
    ]
    safe_results: list[dict[str, Any]] = []
    for item in body.get("results", []):
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if not isinstance(value, bool):
            continue
        safe = {
            "claim_id": item.get("claim_id"),
            "concept_id": item.get("concept_id"),
            "satisfied": value,
            "value": value,
        }
        item_presentation = item.get("presentation")
        if item_presentation is None and len(safe_presentations) == 1:
            item_presentation = safe_presentations[0]
        if (
            isinstance(item_presentation, dict)
            and set(item_presentation)
            == {"authority", "issuer", "provider", "source"}
        ):
            safe["presentation"] = {
                key: item_presentation[key]
                for key in ("authority", "issuer", "provider", "source")
            }
        safe_results.append(safe)
    return {"results": safe_results, "presentations": safe_presentations}


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
    if 400 <= result.status < 500 and "refused" in copy.get(step_id, {}):
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
        "message": "Evidence could not complete the request.",
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
        "response_source": {"status": None, "code": "not_configured"},
    }


def standard_error_result(step_id: str) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "friendly": {"title": "Unknown step.", "message": "This scenario step is not configured.", "status": "needs_attention", "facts": []},
        "request_source": {},
        "response_source": {},
    }
